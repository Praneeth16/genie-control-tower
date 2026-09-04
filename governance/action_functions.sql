-- The bank's conduct controls, as Unity Catalog functions.
--
-- Why these are UC functions and not Python inside the app:
--   * ONE definition. The app, a notebook, a DLT pipeline, a Genie example query and the CMS batch
--     job all call the same object. Nobody can fork "their own" version of the RBI contact window.
--   * The control is a CATALOG OBJECT: it has an owner, EXECUTE grants, a COMMENT that states the
--     regulation it implements, and lineage showing every consumer.
--   * The app service principal needs EXECUTE on these and SELECT on the tables they read — it does
--     NOT need write access anywhere to enforce a control.
--
-- WHO RUNS THEM MATTERS. Unity Catalog SQL functions execute with the INVOKER's permissions, so the
-- row filters in policies.sql apply to the caller. That is exactly right for a business query and
-- exactly wrong for a control: a recovery agent's certification must not become invisible because
-- the person asking is scoped to another region. So the guardrail identity (the app service
-- principal) is deliberately entitled to the whole book via region_entitlement, and the app asserts
-- that at startup and refuses to serve if the assertion fails. A silently blinded control is worse
-- than no control, because it reports "passed".

-- ===========================================================================
-- 1. The RBI contact window
-- ===========================================================================
-- The single most quoted conduct rule in Indian retail collections: recovery agents must not contact
-- a borrower before 08:00 or after 19:00 local time.
--
-- Input is EPOCH SECONDS, not a TIMESTAMP, on purpose. Spark's from_utc_timestamp interprets its
-- input through the session time zone, so the same TIMESTAMP value yields a different hour depending
-- on how the caller's warehouse is configured — an unacceptable property for a compliance control.
-- India has never observed daylight saving and IST is a fixed UTC+05:30, so integer arithmetic on
-- the epoch is exact, session-independent, and auditable by hand.
--
-- 19:00 is treated as the first minute OUTSIDE the window (hour must be < 19), which is the
-- conservative reading. Confirm the boundary with the bank's compliance function before production.
CREATE OR REPLACE FUNCTION ist_hour(epoch_seconds BIGINT)
RETURNS INT
COMMENT 'Hour of day (0-23) in Indian Standard Time for a given epoch-seconds instant. Fixed UTC+05:30 with no daylight saving, computed by integer arithmetic so the result never depends on the caller session time zone.'
RETURN CAST(MOD(FLOOR((epoch_seconds + 19800) / 3600), 24) AS INT);

CREATE OR REPLACE FUNCTION is_within_rbi_conduct_hours(epoch_seconds BIGINT)
RETURNS BOOLEAN
COMMENT 'TRUE when an instant falls inside the permitted borrower-contact window of 08:00 to 19:00 IST. Implements the RBI Fair Practices Code restriction on recovery-agent contact hours. Callers must treat FALSE as a refusal, not a warning.'
RETURN ist_hour(epoch_seconds) >= 8 AND ist_hour(epoch_seconds) < 19;

-- ===========================================================================
-- 2. Recovery agent conduct standing
-- ===========================================================================
-- Returns a REASON, not a boolean, so a blocked action can tell the officer what to fix. 'OK' is the
-- only passing value; anything else is a refusal string fit to show a human.
CREATE OR REPLACE FUNCTION agent_conduct_status(agent_id STRING)
RETURNS STRING
COMMENT 'Conduct standing of a recovery agent: returns OK, or a human-readable reason the agent may not be deployed (unknown, inactive, not conduct-certified, certification expired). Implements the requirement that only trained and certified agents may contact borrowers.'
RETURN COALESCE(
  (SELECT CASE
            WHEN NOT r.active_flag              THEN 'agent is not active'
            WHEN NOT r.rbi_conduct_certified   THEN 'agent is not RBI conduct certified'
            WHEN r.certification_expiry < current_date()
                 THEN CONCAT('conduct certification expired on ', CAST(r.certification_expiry AS STRING))
            ELSE 'OK'
          END
   FROM recovery_agents r
   WHERE r.agent_id = agent_conduct_status.agent_id
   LIMIT 1),
  'agent id not found in the recovery agent register');

-- ===========================================================================
-- 3. Grievance hold
-- ===========================================================================
-- Recovery pressure must not continue while the customer's own complaint is unresolved. Note this
-- depends on customer_id joining correctly across loan_accounts and complaints, which is why
-- mask_customer_id pseudonymises rather than redacting — a constant mask would collapse every
-- customer onto one key and make this return TRUE for everybody.
CREATE OR REPLACE FUNCTION has_open_grievance(customer_id STRING)
RETURNS BOOLEAN
COMMENT 'TRUE when the customer has at least one complaint still open, or any complaint escalated to the Banking Ombudsman. Used to suspend recovery action while the customer grievance is live.'
RETURN EXISTS (
  SELECT 1 FROM complaints c
  WHERE c.customer_id = has_open_grievance.customer_id
    AND (c.status = 'Open' OR c.escalated_to_ombudsman = TRUE));

CREATE OR REPLACE FUNCTION loan_customer_id(loan_account_id STRING)
RETURNS STRING
COMMENT 'The customer identifier owning a loan account, as visible to the caller. Returns the pseudonymised token when the caller is not cleared to read raw identifiers.'
RETURN (SELECT l.customer_id FROM loan_accounts l
        WHERE l.loan_account_id = loan_customer_id.loan_account_id LIMIT 1);

-- ===========================================================================
-- 4. Anti-harassment contact cap
-- ===========================================================================
CREATE OR REPLACE FUNCTION contacts_on_date(loan_account_id STRING, on_date DATE)
RETURNS INT
COMMENT 'Number of collection contact attempts already recorded against a loan account on a given date. Enforces the per-day contact cap that keeps legitimate follow-up from becoming harassment.'
RETURN COALESCE(
  (SELECT CAST(COUNT(*) AS INT) FROM collections_activity a
   WHERE a.loan_account_id = contacts_on_date.loan_account_id
     AND a.activity_date = contacts_on_date.on_date), 0);

-- ===========================================================================
-- 5. Delinquency floor
-- ===========================================================================
-- A field visit to a borrower who is 5 days late is disproportionate. The floor is expressed in days
-- past due from the latest monthly snapshot.
CREATE OR REPLACE FUNCTION account_dpd_days(loan_account_id STRING)
RETURNS INT
COMMENT 'Days past due for a loan account from the most recent delinquency snapshot, or 0 when the account is current or absent. Used to enforce the minimum delinquency before intrusive recovery action is permitted.'
RETURN COALESCE(
  (SELECT d.dpd_days FROM delinquency_monthly d
   WHERE d.loan_account_id = account_dpd_days.loan_account_id
   ORDER BY d.snapshot_month DESC LIMIT 1), 0);

-- ===========================================================================
-- 6. The self-check the app runs at startup
-- ===========================================================================
-- Returns the number of rows the CALLING identity can see in the tables the controls depend on. The
-- app compares this against the known full counts and refuses to serve if it is being row-filtered,
-- because a blinded control reports "passed".
CREATE OR REPLACE FUNCTION guardrail_visibility()
RETURNS STRUCT<recovery_agents: BIGINT, complaints: BIGINT, delinquency_monthly: BIGINT, collections_activity: BIGINT>
COMMENT 'Row counts visible to the calling identity in the four tables the conduct guardrails read. The app asserts these are unfiltered at startup: a guardrail that cannot see the book it protects will report every action compliant.'
RETURN STRUCT(
  (SELECT COUNT(*) FROM recovery_agents),
  (SELECT COUNT(*) FROM complaints),
  (SELECT COUNT(*) FROM delinquency_monthly),
  (SELECT COUNT(*) FROM collections_activity));
