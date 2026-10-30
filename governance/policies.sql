-- Governance policy: who may see which rows and which values. Runs BEFORE the pipeline, because the
-- governed gold tables declare these functions in their definitions (pipeline/04_gold.sql).
--
-- Every control here is a real technical control, not a prompt asking a model to behave:
--   1. Row filters and column masks live ON the table, so one definition is enforced on every path —
--      Genie, SQL, notebooks, the dashboard and the app — for whoever is asking.
--   2. The app forwards the signed-in user's token and Genie runs as the viewer, so each person sees
--      their own entitlement from one shared agent.
--   3. ENTITLEMENTS ARE DATA. Who sees what is a row in a table, not a branch in a function, so an access
--      change is an auditable row change a data steward can make without touching code, and "who can
--      see the West region" is a query rather than a code review.
--
-- Placeholders: ${CATALOG}, ${SCHEMA}, ${ADMIN_PRINCIPAL}, ${PSEUDONYM_SALT}.

-- ===========================================================================
-- 1. Entitlements
-- ===========================================================================
-- principal is a user email, a service principal application id, or an account group name. One row per
-- region the principal may see ('ALL' for every region). The flags clear the principal to read raw
-- identifiers and free text; they are TRUE on a row only for principals who need them.
CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.entitlements (
  principal              STRING    COMMENT 'User email, service principal application id, or account group name.',
  persona                STRING    COMMENT 'The business role this entitlement represents, e.g. Head of Collections.',
  region                 STRING    COMMENT 'Region the principal may see: North, South, East, West, Central, or ALL.',
  can_see_pii            BOOLEAN   COMMENT 'TRUE when cleared to see raw customer identifiers and staff names.',
  can_see_complaint_text BOOLEAN   COMMENT 'TRUE when cleared to read complaint free text and customer letters.',
  granted_by             STRING    COMMENT 'Who granted this entitlement.',
  granted_at             TIMESTAMP COMMENT 'When it was granted.'
) COMMENT 'Data entitlements, one row per principal and region. Read by every row filter and column mask in this schema, so access is changed by changing rows. Audit this table to answer "who can see what".';

-- The deploying administrator (the AI CoE) sees everything; the pipeline also runs as this identity.
MERGE INTO ${CATALOG}.${SCHEMA}.entitlements t
USING (SELECT '${ADMIN_PRINCIPAL}' AS principal, 'AI CoE administrator' AS persona, 'ALL' AS region,
              TRUE AS can_see_pii, TRUE AS can_see_complaint_text, 'setup' AS granted_by,
              current_timestamp() AS granted_at) s
ON t.principal = s.principal AND t.region = s.region
WHEN NOT MATCHED THEN INSERT *;

-- Each caller may see their OWN entitlement rows, and no one else's: who can see what is itself
-- sensitive. The view runs the filter as the caller, so it is the only entitlement object personas get.
CREATE OR REPLACE VIEW ${CATALOG}.${SCHEMA}.my_entitlements
COMMENT 'The calling identity\'s own entitlement rows, directly or through an account group.'
AS SELECT * FROM ${CATALOG}.${SCHEMA}.entitlements e
WHERE e.principal = current_user() OR is_account_group_member(e.principal);

-- ===========================================================================
-- 2. Row filters
-- ===========================================================================
CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.region_visible(region STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: TRUE when the caller holds an entitlement for this region (or ALL), directly or through an account group.'
RETURN EXISTS (
  SELECT 1 FROM ${CATALOG}.${SCHEMA}.entitlements e
  WHERE (e.region = region_visible.region OR e.region = 'ALL')
    AND (e.principal = current_user() OR is_account_group_member(e.principal)));

-- Documents with no region are the bank's own reference documents (the conduct note, agency agreements),
-- which every reader may see. Letters carry their complaint's region and follow region_visible.
CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.document_visible(region STRING)
RETURNS BOOLEAN
COMMENT 'Row filter for documents: reference documents (no region) are visible to all; customer letters follow region_visible.'
RETURN region IS NULL OR ${CATALOG}.${SCHEMA}.region_visible(region);

-- ===========================================================================
-- 3. Column masks
-- ===========================================================================
-- PSEUDONYMISATION, not redaction — and the difference is load-bearing.
--
-- The first version of this mask returned a constant, so every customer became 'CUXXXXXX'. It hid the
-- identifier correctly and broke the data silently: all 9,660 complaints collapsed onto ONE key, so any
-- join on customer_id became a cross join, and a guardrail asking "does this borrower have an open
-- grievance?" matched every borrower. A salted hash keeps the mapping one-to-one, so joins, counts and
-- DISTINCTs stay correct while the real identifier never leaves the table.
--
-- The salt must be identical everywhere and stable forever, or joins across tables masked with different
-- salts silently return nothing. In production it belongs in a secret scope.
CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.mask_customer_id(customer_id STRING)
RETURNS STRING
COMMENT 'Column mask: the raw customer id for callers cleared for PII, otherwise a stable salted pseudonym (CU-xxxxxxxxxx) that still joins.'
RETURN CASE
  WHEN EXISTS (SELECT 1 FROM ${CATALOG}.${SCHEMA}.entitlements e
               WHERE e.can_see_pii AND (e.principal = current_user() OR is_account_group_member(e.principal)))
  THEN customer_id
  ELSE concat('CU-', substr(sha2(concat('${PSEUDONYM_SALT}:', customer_id), 256), 1, 10))
END;

CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.mask_person_name(name STRING)
RETURNS STRING
COMMENT 'Column mask: full name for callers cleared for PII, otherwise initial and surname only.'
RETURN CASE
  WHEN EXISTS (SELECT 1 FROM ${CATALOG}.${SCHEMA}.entitlements e
               WHERE e.can_see_pii AND (e.principal = current_user() OR is_account_group_member(e.principal)))
  THEN name
  -- Initial and surname: enough to tell people apart in a list, not enough to identify them.
  ELSE concat(substr(name, 1, 1), '. ', split(name, ' ')[size(split(name, ' ')) - 1])
END;

CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.mask_complaint_text(txt STRING)
RETURNS STRING
COMMENT 'Column mask: complaint free text, customer letters and their AI summaries for callers cleared to read them; otherwise redacted.'
RETURN CASE
  WHEN txt IS NULL THEN NULL
  WHEN EXISTS (SELECT 1 FROM ${CATALOG}.${SCHEMA}.entitlements e
               WHERE e.can_see_complaint_text AND (e.principal = current_user() OR is_account_group_member(e.principal)))
  THEN txt
  ELSE '[redacted - free text may contain personal data]'
END;

-- ===========================================================================
-- 4. The RBI contact window (used by the pipeline AND by the action guardrail)
-- ===========================================================================
-- Input is EPOCH SECONDS, not a TIMESTAMP, on purpose: from_utc_timestamp interprets its input through the
-- session time zone, so the same TIMESTAMP yields a different hour depending on the caller's warehouse.
-- IST is a fixed UTC+05:30 with no daylight saving, so integer arithmetic on the epoch is exact,
-- session-independent and auditable by hand. One definition means the pipeline flagging a past call and
-- the guardrail refusing a new one can never disagree about what 19:00 means.
--
-- 19:00 is treated as the first minute OUTSIDE the window (hour must be < 19), the conservative reading.
CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.ist_hour(epoch_seconds BIGINT)
RETURNS INT
COMMENT 'Hour of day (0-23) in Indian Standard Time for an epoch-seconds instant. Fixed UTC+05:30, computed by integer arithmetic so the result never depends on the caller session time zone.'
RETURN CAST(mod(floor((epoch_seconds + 19800) / 3600), 24) AS INT);

CREATE OR REPLACE FUNCTION ${CATALOG}.${SCHEMA}.is_within_rbi_conduct_hours(epoch_seconds BIGINT)
RETURNS BOOLEAN
COMMENT 'TRUE when an instant falls inside the permitted borrower-contact window of 08:00 to 19:00 IST. Implements the RBI Fair Practices Code restriction on recovery-agent contact hours. Callers must treat FALSE as a refusal, not a warning.'
RETURN ${CATALOG}.${SCHEMA}.ist_hour(epoch_seconds) >= 8 AND ${CATALOG}.${SCHEMA}.ist_hour(epoch_seconds) < 19;
