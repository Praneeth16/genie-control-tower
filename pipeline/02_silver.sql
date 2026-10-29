-- SILVER: typed, trimmed, conformed — and nothing disappears silently.
--
-- Pattern, repeated per feed:
--   v_<feed>            typed temporary view over the bronze stream. It computes ONE column, dq_reason,
--                       naming the first hard rule the row breaks (NULL when it breaks none).
--   silver_<entity>     the rows with no reason. Each hard rule is its own DROP ROW expectation, keyed
--                       on that same reason string, so the event log reports a count per rule while the
--                       rule itself is written exactly once.
--   quarantine_<entity> the rows WITH a reason, the reason, and the raw record as it arrived.
--
-- Because both targets read the same view and split on the same column, every bronze row lands in
-- exactly one of them. recon_completeness (05_recon.sql) checks that invariant per file, so a rule
-- edited in one place and not the other shows up as a BREAK rather than as lost rows.
--
-- Referential checks (does this loan account exist?) need a join, which an expectation cannot do;
-- they run in core (03_core.sql) and quarantine to quarantine_orphans.

-- ============================================================ month-end DPD snapshot
CREATE TEMPORARY VIEW v_dpd AS
SELECT
  try_cast(trim(snapshot_month) AS DATE)            AS snapshot_month,
  upper(trim(loan_account_id))                      AS loan_account_id,
  try_cast(trim(dpd_days) AS INT)                   AS dpd_days,
  try_cast(trim(outstanding_principal) AS DOUBLE)   AS outstanding_principal,
  try_cast(trim(overdue_amount) AS DOUBLE)          AS overdue_amount,
  CASE
    WHEN try_cast(trim(snapshot_month) AS DATE) IS NULL THEN 'unreadable snapshot month'
    WHEN coalesce(trim(loan_account_id), '') = ''       THEN 'missing loan account'
    WHEN try_cast(trim(dpd_days) AS INT) IS NULL        THEN 'unreadable days past due'
    WHEN try_cast(trim(dpd_days) AS INT) < 0            THEN 'negative days past due'
  END                                               AS dq_reason,
  to_json(struct(snapshot_month, loan_account_id, dpd_days, outstanding_principal, overdue_amount)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_dpd_snapshot);

CREATE OR REFRESH STREAMING TABLE silver_delinquency (
  CONSTRAINT snapshot_month_readable EXPECT (dq_reason IS DISTINCT FROM 'unreadable snapshot month') ON VIOLATION DROP ROW,
  CONSTRAINT has_loan_account        EXPECT (dq_reason IS DISTINCT FROM 'missing loan account')      ON VIOLATION DROP ROW,
  CONSTRAINT dpd_readable            EXPECT (dq_reason IS DISTINCT FROM 'unreadable days past due')  ON VIOLATION DROP ROW,
  CONSTRAINT dpd_not_negative        EXPECT (dq_reason IS DISTINCT FROM 'negative days past due')    ON VIOLATION DROP ROW
)
COMMENT 'Typed month-end DPD snapshot rows that passed every hard rule. Not yet de-duplicated or joined.'
AS SELECT * EXCEPT (raw_record) FROM STREAM(v_dpd);

CREATE OR REFRESH STREAMING TABLE quarantine_delinquency
COMMENT 'DPD snapshot rows rejected by a hard rule, with the reason and the raw record. Nothing is dropped without landing here.'
AS SELECT dq_reason AS reason, raw_record, _source_path, _ingested_at, snapshot_month, loan_account_id
FROM STREAM(v_dpd) WHERE dq_reason IS NOT NULL;

-- ============================================================ contact attempts: two sources, one table
-- The dialer vendor and the field-collection app describe the same thing differently: different field
-- names, one sends IST wall-clock text, the other UTC epoch seconds. Both are conformed to the same
-- columns, and to contact_epoch in UTC so the RBI-hours rule can use the same UC function as the
-- action guardrail (ist_hour), rather than a second, subtly different, interpretation of time.
-- The pipeline session time zone is pinned to UTC in the pipeline configuration, which is what makes
-- unix_timestamp() of an IST wall-clock string minus 19,800 seconds the correct UTC epoch.

CREATE TEMPORARY VIEW v_dialer_contacts AS
SELECT
  trim(call_id)                                                       AS activity_id,
  upper(trim(acct_no))                                                AS loan_account_id,
  try_to_timestamp(trim(call_ts_ist), 'yyyy-MM-dd HH:mm:ss')          AS contact_ts_ist,
  unix_timestamp(try_to_timestamp(trim(call_ts_ist), 'yyyy-MM-dd HH:mm:ss')) - 19800 AS contact_epoch,
  upper(trim(agent_code))                                             AS agent_id,
  trim(channel)                                                       AS channel,
  trim(disposition)                                                   AS outcome,
  try_cast(trim(ptp_amount) AS DOUBLE)                                AS promise_to_pay_amount,
  try_cast(trim(collected_amount) AS DOUBLE)                          AS amount_collected,
  'dialer'                                                            AS source_system,
  CASE
    WHEN coalesce(trim(acct_no), '') = ''                                           THEN 'missing loan account'
    WHEN try_to_timestamp(trim(call_ts_ist), 'yyyy-MM-dd HH:mm:ss') IS NULL         THEN 'unparseable contact timestamp'
    WHEN coalesce(try_cast(trim(collected_amount) AS DOUBLE), 0) < 0
      OR coalesce(try_cast(trim(ptp_amount) AS DOUBLE), 0) < 0                      THEN 'negative amount'
  END                                                                 AS dq_reason,
  to_json(struct(call_id, acct_no, call_ts_ist, agent_code, channel, disposition, ptp_amount, collected_amount)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_dialer_contacts);

CREATE TEMPORARY VIEW v_field_visits AS
SELECT
  trim(visitId)                                                       AS activity_id,
  upper(trim(loanAccount))                                            AS loan_account_id,
  from_utc_timestamp(timestamp_seconds(try_cast(visitEpoch AS BIGINT)), 'Asia/Kolkata') AS contact_ts_ist,
  try_cast(visitEpoch AS BIGINT)                                      AS contact_epoch,
  upper(trim(agentId))                                                AS agent_id,
  'Field Visit'                                                       AS channel,
  trim(outcome)                                                       AS outcome,
  try_cast(promisedAmount AS DOUBLE)                                  AS promise_to_pay_amount,
  try_cast(collectedAmount AS DOUBLE)                                 AS amount_collected,
  'field_app'                                                         AS source_system,
  CASE
    WHEN coalesce(trim(loanAccount), '') = ''                         THEN 'missing loan account'
    WHEN try_cast(visitEpoch AS BIGINT) IS NULL                       THEN 'unparseable contact timestamp'
    WHEN coalesce(try_cast(collectedAmount AS DOUBLE), 0) < 0
      OR coalesce(try_cast(promisedAmount AS DOUBLE), 0) < 0          THEN 'negative amount'
  END                                                                 AS dq_reason,
  to_json(struct(visitId, loanAccount, visitEpoch, agentId, outcome, promisedAmount, collectedAmount)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_field_visits);

CREATE OR REFRESH STREAMING TABLE silver_collections_activity (
  CONSTRAINT has_loan_account       EXPECT (dq_reason IS DISTINCT FROM 'missing loan account')           ON VIOLATION DROP ROW,
  CONSTRAINT contact_time_readable  EXPECT (dq_reason IS DISTINCT FROM 'unparseable contact timestamp')  ON VIOLATION DROP ROW,
  CONSTRAINT amounts_not_negative   EXPECT (dq_reason IS DISTINCT FROM 'negative amount')                ON VIOLATION DROP ROW,
  -- Warn, not drop: a call uploaded in the following month's file is a genuine call. Counting it shows
  -- how often the vendor batches late, which is the first question when a month's effort looks low.
  CONSTRAINT arrived_in_period      EXPECT (date_format(contact_ts_ist, 'yyyy-MM') = regexp_extract(_source_path, '(\\d{4}-\\d{2})', 1))
)
COMMENT 'Every collections contact attempt from both source systems, conformed to one shape, that passed the hard rules. Fed by one flow per source rather than a UNION, so each source is checkpointed and can be replayed on its own.';

CREATE FLOW silver_contacts_from_dialer
AS INSERT INTO silver_collections_activity BY NAME
SELECT * EXCEPT (raw_record) FROM STREAM(v_dialer_contacts);

CREATE FLOW silver_contacts_from_field_app
AS INSERT INTO silver_collections_activity BY NAME
SELECT * EXCEPT (raw_record) FROM STREAM(v_field_visits);

CREATE OR REFRESH STREAMING TABLE quarantine_collections_activity
COMMENT 'Contact attempts rejected by a hard rule, from either source, with the reason and the raw record.';

CREATE FLOW quarantine_contacts_from_dialer
AS INSERT INTO quarantine_collections_activity BY NAME
SELECT dq_reason AS reason, raw_record, source_system, _source_path, _ingested_at, activity_id, loan_account_id
FROM STREAM(v_dialer_contacts) WHERE dq_reason IS NOT NULL;

CREATE FLOW quarantine_contacts_from_field_app
AS INSERT INTO quarantine_collections_activity BY NAME
SELECT dq_reason AS reason, raw_record, source_system, _source_path, _ingested_at, activity_id, loan_account_id
FROM STREAM(v_field_visits) WHERE dq_reason IS NOT NULL;

-- ============================================================ complaints
CREATE TEMPORARY VIEW v_complaints AS
SELECT
  trim(complaint_id)                               AS complaint_id,
  try_cast(trim(received_date) AS DATE)            AS received_date,
  trim(channel)                                    AS channel,
  upper(trim(category_code))                       AS category_code,
  upper(trim(customer_id))                         AS customer_id,
  upper(trim(branch_id))                           AS branch_id,
  upper(trim(product_code))                        AS product_code,
  trim(severity)                                   AS severity,
  trim(status)                                     AS status,
  try_cast(nullif(trim(resolved_date), '') AS DATE) AS resolved_date,
  try_cast(trim(escalated_to_ombudsman) AS BOOLEAN) AS escalated_to_ombudsman,
  try_cast(trim(repeat_complainant) AS BOOLEAN)    AS repeat_complainant,
  complaint_text,
  CASE
    WHEN coalesce(trim(complaint_id), '') = ''                       THEN 'missing complaint id'
    WHEN try_cast(trim(received_date) AS DATE) IS NULL               THEN 'unreadable received date'
    WHEN try_cast(nullif(trim(resolved_date), '') AS DATE) < try_cast(trim(received_date) AS DATE)
                                                                     THEN 'resolved before received'
  END                                              AS dq_reason,
  to_json(struct(complaint_id, received_date, category_code, customer_id, branch_id, status, resolved_date)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_complaints);

CREATE OR REFRESH STREAMING TABLE silver_complaints (
  CONSTRAINT has_complaint_id         EXPECT (dq_reason IS DISTINCT FROM 'missing complaint id')     ON VIOLATION DROP ROW,
  CONSTRAINT received_date_readable   EXPECT (dq_reason IS DISTINCT FROM 'unreadable received date') ON VIOLATION DROP ROW,
  CONSTRAINT resolved_after_received  EXPECT (dq_reason IS DISTINCT FROM 'resolved before received') ON VIOLATION DROP ROW
)
COMMENT 'Typed complaints that passed the hard rules. Category codes trimmed and upper-cased. Not yet de-duplicated.'
AS SELECT * EXCEPT (raw_record) FROM STREAM(v_complaints);

CREATE OR REFRESH STREAMING TABLE quarantine_complaints
COMMENT 'Complaints rejected by a hard rule, with the reason and the raw record.'
AS SELECT dq_reason AS reason, raw_record, _source_path, _ingested_at, complaint_id
FROM STREAM(v_complaints) WHERE dq_reason IS NOT NULL;

-- ============================================================ UPI disputes
CREATE TEMPORARY VIEW v_upi_disputes AS
SELECT
  trim(disputeId)                          AS dispute_id,
  try_cast(txnDate AS DATE)                AS txn_date,
  try_cast(raisedDate AS DATE)             AS raised_date,
  upper(trim(customerRef))                 AS customer_id,
  upper(trim(branchCode))                  AS branch_id,
  try_cast(amount AS DOUBLE)               AS txn_amount,
  trim(failureReason)                      AS failure_reason,
  trim(resolutionPath)                     AS resolution_path,
  try_cast(autoRefunded AS BOOLEAN)        AS auto_refunded,
  try_cast(resolutionSecs AS INT)          AS resolution_seconds,
  trim(status)                             AS status,
  trim(pspHandle)                          AS psp_handle,
  CASE
    WHEN try_cast(txnDate AS DATE) IS NULL           THEN 'unreadable transaction date'
    WHEN coalesce(try_cast(amount AS DOUBLE), 0) <= 0 THEN 'non-positive amount'
  END                                      AS dq_reason,
  to_json(struct(disputeId, txnDate, raisedDate, customerRef, branchCode, amount, status)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_upi_disputes);

CREATE OR REFRESH STREAMING TABLE silver_upi_disputes (
  CONSTRAINT txn_date_readable EXPECT (dq_reason IS DISTINCT FROM 'unreadable transaction date') ON VIOLATION DROP ROW,
  CONSTRAINT amount_positive   EXPECT (dq_reason IS DISTINCT FROM 'non-positive amount')         ON VIOLATION DROP ROW
)
COMMENT 'Typed UPI disputes, conformed from the switch\'s field names, that passed the hard rules.'
AS SELECT * EXCEPT (raw_record) FROM STREAM(v_upi_disputes);

CREATE OR REFRESH STREAMING TABLE quarantine_upi_disputes
COMMENT 'UPI disputes rejected by a hard rule, with the reason and the raw record.'
AS SELECT dq_reason AS reason, raw_record, _source_path, _ingested_at, dispute_id
FROM STREAM(v_upi_disputes) WHERE dq_reason IS NOT NULL;

-- ============================================================ card chargebacks
CREATE TEMPORARY VIEW v_chargebacks AS
SELECT
  trim(chargeback_id)                         AS chargeback_id,
  try_cast(txn_date AS DATE)                  AS txn_date,
  try_cast(raised_date AS DATE)               AS raised_date,
  upper(trim(customer_id))                    AS customer_id,
  trim(card_type)                             AS card_type,
  trim(merchant_category)                     AS merchant_category,
  try_cast(txn_amount AS DOUBLE)              AS txn_amount,
  trim(reason_code)                           AS reason_code,
  trim(liability)                             AS liability,
  trim(status)                                AS status,
  try_cast(days_open AS INT)                  AS days_open,
  try_cast(recovered_amount AS DOUBLE)        AS recovered_amount,
  CASE
    WHEN try_cast(txn_date AS DATE) IS NULL OR try_cast(raised_date AS DATE) IS NULL THEN 'unreadable date'
    WHEN try_cast(raised_date AS DATE) < try_cast(txn_date AS DATE)                  THEN 'raised before transaction'
    WHEN coalesce(try_cast(txn_amount AS DOUBLE), 0) <= 0                            THEN 'non-positive amount'
  END                                         AS dq_reason,
  to_json(struct(chargeback_id, txn_date, raised_date, customer_id, txn_amount, status)) AS raw_record,
  _source_path, _ingested_at
FROM STREAM(bronze_chargebacks);

CREATE OR REFRESH STREAMING TABLE silver_chargebacks (
  CONSTRAINT dates_readable           EXPECT (dq_reason IS DISTINCT FROM 'unreadable date')           ON VIOLATION DROP ROW,
  CONSTRAINT raised_after_transaction EXPECT (dq_reason IS DISTINCT FROM 'raised before transaction') ON VIOLATION DROP ROW,
  CONSTRAINT amount_positive          EXPECT (dq_reason IS DISTINCT FROM 'non-positive amount')       ON VIOLATION DROP ROW
)
COMMENT 'Typed card chargebacks that passed the hard rules.'
AS SELECT * EXCEPT (raw_record) FROM STREAM(v_chargebacks);

CREATE OR REFRESH STREAMING TABLE quarantine_chargebacks
COMMENT 'Chargebacks rejected by a hard rule, with the reason and the raw record.'
AS SELECT dq_reason AS reason, raw_record, _source_path, _ingested_at, chargeback_id
FROM STREAM(v_chargebacks) WHERE dq_reason IS NOT NULL;
