<!-- Generated 2026-10-29 12:21 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 01 — Lakeflow pipeline run

_Generated 2026-10-29 12:21 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** The serverless Spark Declarative Pipeline ran from raw files to governed gold, every layer holds rows, and each data-quality expectation reports how many rows passed and failed. Expectation totals are summed across every update since the tables were created, read from the pipeline's own event log.

Pipeline `9fa6adcc-8175-487f-ad73-3f260e63a359`. Most recent updates:

| update_id | state | cause | started (UTC) | refresh |
|---|---|---|---|---|
| 84611eaa-8954-404b-a1ff-87e248ddf28a | COMPLETED | JOB_TASK | 2026-10-29 10:28 |  |
| 0fa48c1b-e9d9-4ab1-874f-ccd92711f507 | COMPLETED | JOB_TASK | 2026-10-29 09:54 |  |
| 5dcfd5a8-2987-45f6-b178-a17b81be485a | COMPLETED | API_CALL | 2026-10-29 09:50 | core_letter_triage |
| a90c36b1-6f88-4398-b78b-d7e1e2354f82 | COMPLETED | API_CALL | 2026-10-29 09:07 |  |
| 8777fb74-06ef-45cc-a38e-cfce5333f985 | FAILED | API_CALL | 2026-10-29 09:06 |  |

Latest update: `84611eaa-8954-404b-a1ff-87e248ddf28a`.

## Rows per table, by layer

```sql
SELECT 'bronze' AS layer, 'bronze_dialer_contacts' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_dialer_contacts UNION ALL SELECT 'bronze' AS layer, 'bronze_field_visits' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_field_visits UNION ALL SELECT 'bronze' AS layer, 'bronze_dpd_snapshot' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_dpd_snapshot UNION ALL SELECT 'bronze' AS layer, 'bronze_complaints' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_complaints UNION ALL SELECT 'bronze' AS layer, 'bronze_upi_disputes' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_upi_disputes UNION ALL SELECT 'bronze' AS layer, 'bronze_chargebacks' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_chargebacks UNION ALL SELECT 'bronze' AS layer, 'bronze_loan_accounts' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_loan_accounts UNION ALL SELECT 'bronze' AS layer, 'bronze_correspondence' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_correspondence UNION ALL SELECT 'bronze' AS layer, 'bronze_manifests' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.bronze_manifests UNION ALL SELECT 'silver' AS layer, 'silver_collections_activity' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.silver_collections_activity UNION ALL SELECT 'silver' AS layer, 'silver_delinquency' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.silver_delinquency UNION ALL SELECT 'silver' AS layer, 'silver_complaints' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.silver_complaints UNION ALL SELECT 'silver' AS layer, 'silver_upi_disputes' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.silver_upi_disputes UNION ALL SELECT 'silver' AS layer, 'silver_chargebacks' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.silver_chargebacks UNION ALL SELECT 'quarantine' AS layer, 'quarantine_collections_activity' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_collections_activity UNION ALL SELECT 'quarantine' AS layer, 'quarantine_delinquency' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_delinquency UNION ALL SELECT 'quarantine' AS layer, 'quarantine_complaints' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_complaints UNION ALL SELECT 'quarantine' AS layer, 'quarantine_upi_disputes' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_upi_disputes UNION ALL SELECT 'quarantine' AS layer, 'quarantine_chargebacks' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_chargebacks UNION ALL SELECT 'quarantine' AS layer, 'quarantine_orphans' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_orphans UNION ALL SELECT 'gold' AS layer, 'loan_accounts' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.loan_accounts UNION ALL SELECT 'gold' AS layer, 'delinquency_monthly' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.delinquency_monthly UNION ALL SELECT 'gold' AS layer, 'collections_activity' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_activity UNION ALL SELECT 'gold' AS layer, 'complaints' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaints UNION ALL SELECT 'gold' AS layer, 'upi_disputes' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.upi_disputes UNION ALL SELECT 'gold' AS layer, 'chargebacks' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.chargebacks UNION ALL SELECT 'gold' AS layer, 'sla_tracker' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.sla_tracker UNION ALL SELECT 'gold' AS layer, 'rm_achievement' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.rm_achievement UNION ALL SELECT 'gold' AS layer, 'collections_priority' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_priority UNION ALL SELECT 'gold' AS layer, 'complaint_ai_triage' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaint_ai_triage UNION ALL SELECT 'gold' AS layer, 'complaint_documents' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaint_documents UNION ALL SELECT 'gold' AS layer, 'recon_completeness' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.recon_completeness UNION ALL SELECT 'gold' AS layer, 'data_quality_summary' AS table_name, count(*) AS row_count FROM serverless_lakebase_praneeth_catalog.control_tower_banking.data_quality_summary
```

| layer | table_name | row_count |
|---|---|---|
| gold | loan_accounts | 6000 |
| gold | delinquency_monthly | 108000 |
| gold | collections_activity | 63230 |
| gold | complaints | 9660 |
| gold | upi_disputes | 26316 |
| gold | sla_tracker | 2247 |
| gold | rm_achievement | 3240 |
| gold | collections_priority | 589 |
| gold | complaint_ai_triage | 713 |
| gold | complaint_documents | 718 |
| bronze | bronze_dialer_contacts | 53284 |
| bronze | bronze_field_visits | 10630 |
| bronze | bronze_dpd_snapshot | 108025 |
| bronze | bronze_complaints | 9693 |
| bronze | bronze_upi_disputes | 26351 |
| bronze | bronze_chargebacks | 4220 |
| bronze | bronze_loan_accounts | 6012 |
| bronze | bronze_correspondence | 713 |
| bronze | bronze_manifests | 19 |
| silver | silver_collections_activity | 63859 |
| silver | silver_delinquency | 108000 |
| silver | silver_complaints | 9693 |
| silver | silver_upi_disputes | 26316 |
| silver | silver_chargebacks | 4200 |
| quarantine | quarantine_collections_activity | 55 |
| quarantine | quarantine_delinquency | 25 |
| quarantine | quarantine_complaints | 0 |
| quarantine | quarantine_upi_disputes | 35 |
| quarantine | quarantine_chargebacks | 20 |
| quarantine | quarantine_orphans | 70 |
| gold | chargebacks | 4200 |
| gold | recon_completeness | 177 |
| gold | data_quality_summary | 11 |

## Expectations (from the event log)

```sql
SELECT e.dataset, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM (SELECT explode(from_json(details:flow_progress:data_quality:expectations,
        'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
      FROM event_log('9fa6adcc-8175-487f-ad73-3f260e63a359') WHERE event_type = 'flow_progress'
        AND details:flow_progress:data_quality:expectations IS NOT NULL) x
GROUP BY ALL ORDER BY 1, 2
```

| dataset | expectation | passed | failed |
|---|---|---|---|
| serverless_lakebase_praneeth_catalog.control_tower_banking.recon_completeness | file_reconciled | 510 | 3 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_chargebacks | amount_positive | 4220 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_chargebacks | dates_readable | 4220 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_chargebacks | raised_after_transaction | 4200 | 20 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_complaints | has_complaint_id | 9693 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_complaints | received_date_readable | 9693 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_complaints | resolved_after_received | 9693 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_dialer | amounts_not_negative | 53284 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_dialer | arrived_in_period | 53016 | 268 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_dialer | contact_time_readable | 53254 | 30 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_dialer | has_loan_account | 53284 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_field_app | amounts_not_negative | 10630 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_field_app | arrived_in_period | 10630 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_field_app | contact_time_readable | 10630 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_contacts_from_field_app | has_loan_account | 10605 | 25 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_delinquency | dpd_not_negative | 108000 | 25 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_delinquency | dpd_readable | 108025 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_delinquency | has_loan_account | 108025 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_delinquency | snapshot_month_readable | 108025 | 0 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_upi_disputes | amount_positive | 26316 | 35 |
| serverless_lakebase_praneeth_catalog.control_tower_banking.silver_upi_disputes | txn_date_readable | 26351 | 0 |
