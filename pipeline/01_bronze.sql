-- BRONZE: every source file exactly as it landed, read incrementally by Auto Loader.
--
-- Nothing is cleaned here. Every column is read as STRING (inferColumnTypes => false) so a value that
-- will not parse survives to silver, where it can be quarantined WITH the reason, instead of being turned
-- into a NULL by a type inference nobody chose. Every row carries the file it came from and when it was
-- ingested; reconciliation against the senders' manifests counts by that path.
--
-- Pipeline configuration: ${landing_path} = /Volumes/<catalog>/<schema>/landing

-- ---------------------------------------------------------------- reference data and masters (snapshots)
CREATE OR REFRESH STREAMING TABLE bronze_branch_master
COMMENT 'Raw branch master snapshots from the reference-data feed, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/reference/branch_master/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_product_master
COMMENT 'Raw product master snapshots, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/reference/product_master/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_complaint_categories
COMMENT 'Raw complaint category and SLA reference data, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/reference/complaint_categories/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_incentive_slabs
COMMENT 'Raw RM incentive slab grid, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/reference/incentive_slabs/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_recovery_agents
COMMENT 'Raw recovery agent register from the collections core system, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/collections/recovery_agents/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_relationship_managers
COMMENT 'Raw relationship manager roster from HRMS, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/hrms/relationship_managers/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_customer_portfolio
COMMENT 'Raw customer master from CRM, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/crm/customer_portfolio/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_product_holdings
COMMENT 'Raw product holdings from CRM, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/crm/product_holdings/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_loan_accounts
COMMENT 'Raw loan account master from the loan origination system (LOS), as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/los/loan_accounts/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_repayment_schedule
COMMENT 'Raw repayment position per loan from LOS, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/los/repayment_schedule/', format => 'csv', header => true,
                       inferColumnTypes => false);

-- ---------------------------------------------------------------- periodic feeds (one file per month)
CREATE OR REFRESH STREAMING TABLE bronze_dpd_snapshot
COMMENT 'Raw month-end days-past-due snapshots from the collections core system, as landed. No bucket, NPA or roll fields: those are derived by the pipeline.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/collections/dpd_snapshot/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_dialer_contacts
COMMENT 'Raw call, SMS, WhatsApp, email and legal-notice attempts from the dialer vendor, in the vendor\'s field names (call_id, acct_no, call_ts_ist in IST wall-clock).'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/dialer/contacts/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_field_visits
COMMENT 'Raw field visits from the field-collection mobile app, JSON, in the app\'s field names (visitId, loanAccount, visitEpoch in UTC epoch seconds).'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/field_app/visits/', format => 'json', inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_complaints
COMMENT 'Raw complaints from CRM, as landed. No SLA or resolution-time fields: those are derived by the pipeline.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/crm/complaints/', format => 'csv', header => true,
                       inferColumnTypes => false, multiLine => true);

CREATE OR REFRESH STREAMING TABLE bronze_upi_disputes
COMMENT 'Raw UPI disputes from the payment switch, JSON, in the switch\'s field names.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/upi_switch/disputes/', format => 'json', inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_chargebacks
COMMENT 'Raw card chargeback cases from the cards system, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/cards/chargebacks/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_rm_targets
COMMENT 'Raw monthly RM targets from the sales system, as landed.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/sales/rm_targets/', format => 'csv', header => true,
                       inferColumnTypes => false);

CREATE OR REFRESH STREAMING TABLE bronze_rm_achievement
COMMENT 'Raw monthly RM actuals from the sales system, as landed. Attainment, incentive, quality gate and clawback are derived by the pipeline.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/sales/rm_achievement/', format => 'csv', header => true,
                       inferColumnTypes => false);

-- ---------------------------------------------------------------- unstructured and control files
CREATE OR REFRESH STREAMING TABLE bronze_correspondence
COMMENT 'Scanned customer complaint letters, one row per letter, full text as landed.'
AS SELECT value AS letter_text,
          regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          _metadata.file_name AS _file_name,
          _metadata.file_size AS _file_size_bytes,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/correspondence/', format => 'text', wholeText => true);

CREATE OR REFRESH STREAMING TABLE bronze_reference_docs
COMMENT 'The bank\'s reference documents (conduct compliance note, recovery agency agreements), full text.'
AS SELECT value AS document_text,
          regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          _metadata.file_name AS _file_name,
          _metadata.file_size AS _file_size_bytes,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/reference_docs/', format => 'text', wholeText => true);

CREATE OR REFRESH STREAMING TABLE bronze_manifests
COMMENT 'Senders'' control manifests, one row per period: what each source system claims it sent (row counts and amount totals per file). Written last in every drop.'
AS SELECT *, regexp_extract(_metadata.file_path, 'landing/(.*)$', 1) AS _source_path,
          current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing_path}/_manifests/', format => 'json', multiLine => true);
