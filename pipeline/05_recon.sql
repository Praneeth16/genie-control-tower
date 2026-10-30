-- COMPLETENESS AND QUALITY: prove the data is complete before anyone uses it.
--
-- Every source sends a manifest per period saying what it sent. For every file, this compares
--   declared   rows and amount total in the sender's manifest
--   landed     rows that reached bronze
--   loaded     rows that passed the hard rules into silver
--   quarantined rows rejected, each with a reason
-- and gives ONE verdict: RECONCILED, or BREAK with the reason. A truncated transfer, a file declared but
-- never received, a file nobody declared, or a rule that drops rows without quarantining them all show up
-- here, on the file that caused them, instead of as a quietly lower number on a dashboard.

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW manifest_files AS
SELECT period, f.path AS path, CAST(f.rows AS BIGINT) AS declared_rows, f.amount_field,
       CAST(f.amount_total AS DOUBLE) AS declared_amount, _ingested_at AS manifest_received_at
FROM (SELECT period, explode(files) AS f, _ingested_at FROM bronze_manifests)
QUALIFY row_number() OVER (PARTITION BY f.path ORDER BY _ingested_at DESC) = 1;

-- What actually landed, per file, with the same amount field the sender totalled.
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW landed_files AS
SELECT _source_path AS path, 'dialer_contacts' AS feed, count(*) AS landed_rows,
       sum(try_cast(collected_amount AS DOUBLE)) AS landed_amount FROM bronze_dialer_contacts GROUP BY 1
UNION ALL SELECT _source_path, 'field_visits', count(*), sum(try_cast(collectedAmount AS DOUBLE)) FROM bronze_field_visits GROUP BY 1
UNION ALL SELECT _source_path, 'dpd_snapshot', count(*), sum(try_cast(outstanding_principal AS DOUBLE)) FROM bronze_dpd_snapshot GROUP BY 1
UNION ALL SELECT _source_path, 'complaints', count(*), CAST(NULL AS DOUBLE) FROM bronze_complaints GROUP BY 1
UNION ALL SELECT _source_path, 'upi_disputes', count(*), sum(try_cast(amount AS DOUBLE)) FROM bronze_upi_disputes GROUP BY 1
UNION ALL SELECT _source_path, 'chargebacks', count(*), sum(try_cast(txn_amount AS DOUBLE)) FROM bronze_chargebacks GROUP BY 1
UNION ALL SELECT _source_path, 'rm_targets', count(*), CAST(NULL AS DOUBLE) FROM bronze_rm_targets GROUP BY 1
UNION ALL SELECT _source_path, 'rm_achievement', count(*), CAST(NULL AS DOUBLE) FROM bronze_rm_achievement GROUP BY 1
UNION ALL SELECT _source_path, 'loan_accounts', count(*), sum(try_cast(outstanding_principal AS DOUBLE)) FROM bronze_loan_accounts GROUP BY 1
UNION ALL SELECT _source_path, 'repayment_schedule', count(*), CAST(NULL AS DOUBLE) FROM bronze_repayment_schedule GROUP BY 1
UNION ALL SELECT _source_path, 'branch_master', count(*), CAST(NULL AS DOUBLE) FROM bronze_branch_master GROUP BY 1
UNION ALL SELECT _source_path, 'product_master', count(*), CAST(NULL AS DOUBLE) FROM bronze_product_master GROUP BY 1
UNION ALL SELECT _source_path, 'complaint_categories', count(*), CAST(NULL AS DOUBLE) FROM bronze_complaint_categories GROUP BY 1
UNION ALL SELECT _source_path, 'incentive_slabs', count(*), CAST(NULL AS DOUBLE) FROM bronze_incentive_slabs GROUP BY 1
UNION ALL SELECT _source_path, 'recovery_agents', count(*), CAST(NULL AS DOUBLE) FROM bronze_recovery_agents GROUP BY 1
UNION ALL SELECT _source_path, 'relationship_managers', count(*), CAST(NULL AS DOUBLE) FROM bronze_relationship_managers GROUP BY 1
UNION ALL SELECT _source_path, 'customer_portfolio', count(*), CAST(NULL AS DOUBLE) FROM bronze_customer_portfolio GROUP BY 1
UNION ALL SELECT _source_path, 'product_holdings', count(*), CAST(NULL AS DOUBLE) FROM bronze_product_holdings GROUP BY 1
UNION ALL SELECT _source_path, 'reference_docs', count(*), CAST(NULL AS DOUBLE) FROM bronze_reference_docs GROUP BY 1
-- Letters arrive one file each; the manifest counts them per month folder.
UNION ALL SELECT regexp_extract(_source_path, '^(correspondence/[^/]+/)', 1), 'correspondence', count(*), CAST(NULL AS DOUBLE)
          FROM bronze_correspondence GROUP BY 1;

-- Rows that reached silver, and rows quarantined, per file. Only the feeds with hard rules have a silver
-- layer; for the others every landed row is loaded.
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW split_files AS
WITH loaded AS (
  SELECT _source_path AS path, count(*) AS n FROM silver_collections_activity GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM silver_delinquency GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM silver_complaints GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM silver_upi_disputes GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM silver_chargebacks GROUP BY 1
),
quarantined AS (
  SELECT _source_path AS path, count(*) AS n FROM quarantine_collections_activity GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM quarantine_delinquency GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM quarantine_complaints GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM quarantine_upi_disputes GROUP BY 1
  UNION ALL SELECT _source_path, count(*) FROM quarantine_chargebacks GROUP BY 1
)
SELECT coalesce(l.path, q.path) AS path, l.n AS loaded_rows, coalesce(q.n, 0) AS quarantined_rows
FROM loaded l FULL OUTER JOIN quarantined q ON q.path = l.path;

CREATE OR REFRESH MATERIALIZED VIEW recon_completeness (
  period            STRING COMMENT 'Reporting period the file belongs to (yyyy-MM), or reference for master data.',
  path              STRING COMMENT 'File path relative to the landing volume.',
  feed              STRING COMMENT 'Source feed.',
  declared_rows     BIGINT COMMENT 'Rows the sender declared in its manifest.',
  landed_rows       BIGINT COMMENT 'Rows that reached bronze.',
  loaded_rows       BIGINT COMMENT 'Rows that passed the hard rules into silver (equals landed for feeds without hard rules).',
  quarantined_rows  BIGINT COMMENT 'Rows rejected by a hard rule, each with a reason in a quarantine table.',
  declared_amount   DOUBLE COMMENT 'Amount total the sender declared, in INR, for feeds that send one.',
  landed_amount     DOUBLE COMMENT 'Amount total of the rows that landed, in INR.',
  status            STRING COMMENT 'RECONCILED, or BREAK.',
  break_reason      STRING COMMENT 'Why the file did not reconcile. NULL when RECONCILED.',
  CONSTRAINT file_reconciled EXPECT (status = 'RECONCILED')
)
COMMENT 'One completeness verdict per landed or declared file: what the sender declared, what landed, what loaded and what was quarantined. A BREAK names the file and the reason. The amount tolerance is INR 1, to absorb floating-point summation order.'
AS
WITH j AS (
  SELECT coalesce(m.period, CASE WHEN l.path RLIKE '\\d{4}-\\d{2}' THEN regexp_extract(l.path, '(\\d{4}-\\d{2})', 1) ELSE 'reference' END) AS period,
         coalesce(m.path, l.path) AS path, l.feed, m.declared_rows, l.landed_rows,
         -- Feeds with a silver layer must show their rows in silver or quarantine; a file with none in
         -- either has lost every row, and must not be assumed loaded.
         CASE WHEN l.feed IN ('dialer_contacts', 'field_visits', 'dpd_snapshot', 'complaints', 'upi_disputes', 'chargebacks')
              THEN coalesce(s.loaded_rows, 0) ELSE l.landed_rows END AS loaded_rows,
         coalesce(s.quarantined_rows, 0) AS quarantined_rows,
         m.declared_amount, l.landed_amount, m.amount_field
  FROM manifest_files m
  FULL OUTER JOIN landed_files l ON l.path = m.path
  LEFT JOIN split_files s ON s.path = coalesce(m.path, l.path)
)
SELECT period, path, feed, declared_rows, landed_rows, loaded_rows, quarantined_rows,
       declared_amount, round(landed_amount, 2) AS landed_amount,
       CASE WHEN break_reason IS NULL THEN 'RECONCILED' ELSE 'BREAK' END AS status, break_reason
FROM (
  SELECT *,
    CASE
      WHEN landed_rows IS NULL THEN 'declared in the manifest but never received'
      WHEN declared_rows IS NULL THEN 'received but not declared in any manifest'
      WHEN landed_rows <> declared_rows
        THEN concat('landed ', landed_rows, ' of ', declared_rows, ' declared rows (', declared_rows - landed_rows, ' missing)')
      WHEN amount_field IS NOT NULL AND abs(coalesce(landed_amount, 0) - coalesce(declared_amount, 0)) > 1
        THEN concat('amount total ', round(landed_amount, 2), ' differs from declared ', declared_amount)
      WHEN landed_rows <> loaded_rows + quarantined_rows
        THEN concat(landed_rows - loaded_rows - quarantined_rows, ' rows neither loaded nor quarantined')
    END AS break_reason
  FROM j
);

-- Everything the pipeline caught, in one place, by entity and reason.
CREATE OR REFRESH MATERIALIZED VIEW data_quality_summary (
  entity     STRING COMMENT 'Business entity the rows belong to.',
  check_type STRING COMMENT 'quarantined (failed a format rule), orphaned (references something that does not exist), de-duplicated (re-sent copy removed), or late (arrived in a later period\'s file, kept).',
  reason     STRING COMMENT 'The specific rule or condition.',
  row_count  BIGINT COMMENT 'Rows affected.'
)
COMMENT 'Every data-quality finding the pipeline caught, by entity and reason. Quarantined and orphaned rows are kept with their raw record in the quarantine tables; nothing is dropped silently.'
AS
SELECT 'collections_activity' AS entity, 'quarantined' AS check_type, reason, count(*) AS row_count FROM quarantine_collections_activity GROUP BY ALL
UNION ALL SELECT 'delinquency_monthly', 'quarantined', reason, count(*) FROM quarantine_delinquency GROUP BY ALL
UNION ALL SELECT 'complaints', 'quarantined', reason, count(*) FROM quarantine_complaints GROUP BY ALL
UNION ALL SELECT 'upi_disputes', 'quarantined', reason, count(*) FROM quarantine_upi_disputes GROUP BY ALL
UNION ALL SELECT 'chargebacks', 'quarantined', reason, count(*) FROM quarantine_chargebacks GROUP BY ALL
UNION ALL SELECT entity, 'orphaned', reason, count(*) FROM quarantine_orphans GROUP BY ALL
UNION ALL SELECT 'collections_activity', 'de-duplicated', 're-sent copy of a contact already received',
                 count(*) - count(DISTINCT activity_id) FROM silver_collections_activity
UNION ALL SELECT 'complaints', 'de-duplicated', 're-sent copy of a complaint already received',
                 count(*) - count(DISTINCT complaint_id) FROM silver_complaints
-- Distinct contacts, not rows: a late call the vendor also re-sent would otherwise be counted twice.
UNION ALL SELECT 'collections_activity', 'late', 'contact uploaded in a later month\'s file',
                 count(DISTINCT CASE WHEN date_format(contact_ts_ist, 'yyyy-MM') <> regexp_extract(_source_path, '(\\d{4}-\\d{2})', 1)
                                     THEN activity_id END)
          FROM silver_collections_activity;
