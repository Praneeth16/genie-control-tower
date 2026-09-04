-- Governance policy for the Control Tower Genie Agent workshop.
--
-- This is the module that matters most to a bank's AI CoE, so every control here is a real
-- technical control, not a prompt asking the model to behave.
--
-- Design decisions, each traceable to the Production-Grade Genie Field Guide:
--   1. Row filters and COLUMN MASKS applied to the TABLE, not dynamic views. The policy then
--      lives on the object and is enforced on every compute path — Genie, DBSQL, notebooks,
--      the App — from one definition.
--   2. Genie Agents run in VIEWER mode, the only run-as mode that gives true per-user row and
--      column security. The App forwards the caller's token (x-forwarded-access-token) so the
--      user's own grants apply.
--   3. ABAC via governed tags, so one policy covers tables that do not exist yet.
--   4. The run-as identity holds SELECT only. Genie generates SQL from untrusted natural
--      language, so the execution identity is treated as an attack surface. All writes happen
--      through approved UC functions, never through generated SQL.
--
-- IMPORTANT ordering note (this bit us once already): these policies MUST be applied BEFORE any
-- benchmark baseline is recorded. Row filters change row counts and column masks change values,
-- so a baseline captured before them is invalid for the governed context.

-- ===========================================================================
-- 1. Groups this policy keys on
-- ===========================================================================
-- Created in the account console / SCIM, referenced here. The demo works with whatever subset
-- exists; IS_ACCOUNT_GROUP_MEMBER returns false for a group the caller is not in, which is the
-- safe default.
--
--   ${GROUP_PREFIX}_collections_ops   collections team, sees only their own region
--   ${GROUP_PREFIX}_grievance_ops     grievance team, sees only their own region
--   ${GROUP_PREFIX}_rm_managers       RM line managers, see their own region's RMs
--   ${GROUP_PREFIX}_pii_readers       cleared to see unmasked customer identifiers
--   ${GROUP_PREFIX}_auditors          read everything unfiltered, for regulatory review
--   ${GROUP_PREFIX}_ai_coe            the AI CoE, full read for building and benchmarking

-- ===========================================================================
-- 2. Region entitlement mapping
-- ===========================================================================
-- Rather than hardcode a region per group, keep an entitlement table. It is the thing a data
-- steward can maintain without touching a function definition, and it makes the policy auditable
-- by querying data instead of reading code.

CREATE TABLE IF NOT EXISTS region_entitlement (
  principal   STRING  COMMENT 'Account group name or user email the entitlement is granted to.',
  region      STRING  COMMENT 'Region the principal may see: North, South, East, West, Central, or ALL for unrestricted.',
  granted_by  STRING  COMMENT 'Who granted this entitlement.',
  granted_at  TIMESTAMP COMMENT 'When the entitlement was granted.'
) COMMENT 'Region-level data entitlements. Read by the row-filter functions below, so a steward can change access without altering a function definition. Audit this table to answer "who can see what".';

-- Seed: the AI CoE and auditors see everything; ops groups are region-scoped.
-- MERGE so re-running is idempotent.
MERGE INTO region_entitlement AS t
USING (
  SELECT * FROM VALUES
    ('${GROUP_PREFIX}_ai_coe',          'ALL',     'workshop-setup', current_timestamp()),
    ('${GROUP_PREFIX}_auditors',        'ALL',     'workshop-setup', current_timestamp()),
    ('${GROUP_PREFIX}_collections_ops', 'West',    'workshop-setup', current_timestamp()),
    ('${GROUP_PREFIX}_collections_ops', 'Central', 'workshop-setup', current_timestamp()),
    ('${GROUP_PREFIX}_grievance_ops',   'ALL',     'workshop-setup', current_timestamp()),
    ('${GROUP_PREFIX}_rm_managers',     'North',   'workshop-setup', current_timestamp())
  AS s(principal, region, granted_by, granted_at)
) AS s
ON t.principal = s.principal AND t.region = s.region
WHEN NOT MATCHED THEN INSERT *;

-- ===========================================================================
-- 3. Row filter functions
-- ===========================================================================
-- A row filter returns a boolean per row. It is evaluated with the querying user's identity, so
-- in Genie VIEWER mode each user sees exactly their entitled rows from the same agent.

CREATE OR REPLACE FUNCTION region_visible(region STRING)
RETURN
  -- Unrestricted principals: the AI CoE, auditors, and workspace admins.
  IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_ai_coe')
  OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_auditors')
  -- Otherwise the row's region must appear in an entitlement granted to a group the caller is in.
  OR EXISTS (
       SELECT 1 FROM region_entitlement e
       WHERE (e.region = region_visible.region OR e.region = 'ALL')
         AND (IS_ACCOUNT_GROUP_MEMBER(e.principal) OR e.principal = CURRENT_USER())
     );


-- Branch-level filter for tables that carry branch_id but not region, resolved through
-- branch_master so there is one source of truth for which region a branch sits in.
CREATE OR REPLACE FUNCTION branch_region_visible(branch_id STRING)
RETURN
  IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_ai_coe')
  OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_auditors')
  OR EXISTS (
       SELECT 1
       FROM branch_master b
       JOIN region_entitlement e
         ON (e.region = b.region OR e.region = 'ALL')
       WHERE b.branch_id = branch_region_visible.branch_id
         AND (IS_ACCOUNT_GROUP_MEMBER(e.principal) OR e.principal = CURRENT_USER())
     );


-- ===========================================================================
-- 4. Column mask functions
-- ===========================================================================
-- A column mask rewrites the value per caller. Note this protects the NARRATIVE too, not just
-- the result grid: Genie only ever receives the masked value, so it cannot summarise what it
-- was never shown. That is the point the PII-leakage audit test proves.

-- PSEUDONYMISATION, not redaction — and the difference is load-bearing.
--
-- The first version of this mask returned a constant, CONCAT(SUBSTR(customer_id,1,2),'XXXXXX'), so
-- every customer became 'CUXXXXXX'. It hid the identifier correctly and broke the data silently:
-- all 9,660 complaint rows collapsed onto ONE key, so any join on customer_id became a cross join.
-- A guardrail asking "does this borrower have an open grievance?" would have matched every borrower
-- and blocked every action, for reasons no one would have found quickly.
--
-- A salted hash keeps the mapping one-to-one, so joins, counts and DISTINCTs stay correct while the
-- real identifier never leaves the table. Verified after the change: 8,657 distinct tokens across
-- 9,660 complaints, and loan-to-complaint joins return 1-2 loans per customer instead of 9,660.
--
-- The salt is a literal here because this is a synthetic-data workshop. In production it belongs in
-- a secret scope, rotated, and the same salt must be used everywhere or joins across two tables
-- masked with different salts will silently return nothing.
CREATE OR REPLACE FUNCTION mask_customer_id(customer_id STRING)
RETURN CASE
  WHEN IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_pii_readers')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_auditors')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_ai_coe')
  THEN customer_id
  ELSE CONCAT('CU-', SUBSTR(SHA2(CONCAT('${PSEUDONYM_SALT}:', customer_id), 256), 1, 10))
END;

CREATE OR REPLACE FUNCTION mask_person_name(name STRING)
RETURN CASE
  WHEN IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_pii_readers')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_auditors')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_ai_coe')
  THEN name
  -- Initials only: enough to distinguish individuals in a list, not enough to identify them.
  ELSE CONCAT(SUBSTR(name, 1, 1), '. ', SPLIT(name, ' ')[SIZE(SPLIT(name, ' ')) - 1])
END;


CREATE OR REPLACE FUNCTION mask_complaint_text(txt STRING)
RETURN CASE
  WHEN IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_pii_readers')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_auditors')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_grievance_ops')
    OR IS_ACCOUNT_GROUP_MEMBER('${GROUP_PREFIX}_ai_coe')
  THEN txt
  ELSE '[redacted - free text may contain personal data]'
END;


-- ===========================================================================
-- 5. Apply row filters
-- ===========================================================================

ALTER TABLE delinquency_monthly  SET ROW FILTER branch_region_visible ON (branch_id);
ALTER TABLE loan_accounts        SET ROW FILTER branch_region_visible ON (branch_id);
ALTER TABLE collections_activity SET ROW FILTER branch_region_visible ON (branch_id);
ALTER TABLE repayment_schedule   SET ROW FILTER branch_region_visible ON (branch_id);
ALTER TABLE recovery_agents      SET ROW FILTER region_visible ON (region);

ALTER TABLE complaints           SET ROW FILTER branch_region_visible ON (branch_id);
ALTER TABLE sla_tracker          SET ROW FILTER region_visible ON (region);
ALTER TABLE upi_disputes         SET ROW FILTER branch_region_visible ON (branch_id);

ALTER TABLE rm_achievement       SET ROW FILTER region_visible ON (region);
ALTER TABLE rm_targets           SET ROW FILTER region_visible ON (region);
ALTER TABLE relationship_managers SET ROW FILTER region_visible ON (region);
ALTER TABLE customer_portfolio   SET ROW FILTER region_visible ON (region);

-- ===========================================================================
-- 6. Apply column masks
-- ===========================================================================

ALTER TABLE loan_accounts      ALTER COLUMN customer_id     SET MASK mask_customer_id;
ALTER TABLE complaints         ALTER COLUMN customer_id     SET MASK mask_customer_id;
ALTER TABLE complaints         ALTER COLUMN complaint_text  SET MASK mask_complaint_text;
ALTER TABLE upi_disputes       ALTER COLUMN customer_id     SET MASK mask_customer_id;
ALTER TABLE chargebacks        ALTER COLUMN customer_id     SET MASK mask_customer_id;
ALTER TABLE customer_portfolio ALTER COLUMN customer_id     SET MASK mask_customer_id;
ALTER TABLE product_holdings   ALTER COLUMN customer_id     SET MASK mask_customer_id;

ALTER TABLE recovery_agents       ALTER COLUMN agent_name SET MASK mask_person_name;
ALTER TABLE relationship_managers ALTER COLUMN rm_name    SET MASK mask_person_name;

-- ===========================================================================
-- 7. ABAC — governed tags
-- ===========================================================================
-- Tags are the attribute layer: tagging a column documents its classification and lets a single
-- tag-driven policy cover tables nobody has created yet.
--
-- Worth showing the room: this metastore ENFORCES a tag policy, so tag values are not free text.
-- Probing it returned the permitted vocabulary:
--     domain              -> finance | sales | supply_chain | quality | hr | operations
--     data_classification -> u-nnpi | cui | pii
--     pii                 -> ssn | address
-- An attempt to write `domain = 'collections'` is REJECTED by Unity Catalog. That is ABAC working
-- as intended: the taxonomy is governed centrally, so a team cannot invent its own classification
-- and quietly fall outside the policies that key on it. We therefore map our domains onto the
-- approved vocabulary rather than inventing values.
--
-- Field-guide gotcha to state on the slide: UC tags are NOT inherited down the hierarchy. A tag on
-- the schema does not reach its tables. Tag at the level you actually query and certify, and audit
-- for drift — a table that silently loses its classification tag also loses any policy keyed on it.

-- PII columns: classified `pii` under the governed taxonomy. These are the same columns the masks
-- in section 6 protect, so the tag documents the intent and the mask enforces it.
ALTER TABLE loan_accounts         ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE complaints            ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE complaints            ALTER COLUMN complaint_text SET TAGS ('data_classification' = 'pii');
ALTER TABLE upi_disputes          ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE chargebacks           ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE customer_portfolio    ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE product_holdings      ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER TABLE recovery_agents       ALTER COLUMN agent_name     SET TAGS ('data_classification' = 'pii');
ALTER TABLE relationship_managers ALTER COLUMN rm_name        SET TAGS ('data_classification' = 'pii');

-- Non-PII business columns, classified as unclassified-non-NPI so the absence of a tag never has
-- to be read as "nobody looked at this yet".
ALTER TABLE delinquency_monthly ALTER COLUMN outstanding_principal SET TAGS ('data_classification' = 'u-nnpi');
ALTER TABLE rm_achievement      ALTER COLUMN incentive_earned      SET TAGS ('data_classification' = 'cui');

-- Domain tags at table level, mapped onto the governed vocabulary:
--   collections + grievance -> operations
--   RM performance          -> sales
ALTER TABLE delinquency_monthly   SET TAGS ('domain' = 'operations');
ALTER TABLE loan_accounts         SET TAGS ('domain' = 'operations');
ALTER TABLE collections_activity  SET TAGS ('domain' = 'operations');
ALTER TABLE recovery_agents       SET TAGS ('domain' = 'operations');
ALTER TABLE repayment_schedule    SET TAGS ('domain' = 'operations');
ALTER TABLE complaints            SET TAGS ('domain' = 'operations');
ALTER TABLE sla_tracker           SET TAGS ('domain' = 'operations');
ALTER TABLE complaint_categories  SET TAGS ('domain' = 'operations');
ALTER TABLE upi_disputes          SET TAGS ('domain' = 'operations');
ALTER TABLE chargebacks           SET TAGS ('domain' = 'operations');
ALTER TABLE rm_achievement        SET TAGS ('domain' = 'sales');
ALTER TABLE rm_targets            SET TAGS ('domain' = 'sales');
ALTER TABLE relationship_managers SET TAGS ('domain' = 'sales');
ALTER TABLE incentive_slabs       SET TAGS ('domain' = 'sales');
ALTER TABLE customer_portfolio    SET TAGS ('domain' = 'sales');
ALTER TABLE product_holdings      SET TAGS ('domain' = 'sales');
ALTER TABLE branch_master         SET TAGS ('domain' = 'operations');
ALTER TABLE product_master        SET TAGS ('domain' = 'operations');
