<!-- Generated 2026-10-29 13:53 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 02 — Data quality and completeness

_Generated 2026-10-29 13:53 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** Every planted defect in the answer key was caught, in the expected place, with the expected count; the governed gold tables hold exactly the rows the clean book should; and every source file is reconciled against its sender's manifest, with the one planted truncated transfer shown as a BREAK.

## Planted findings: answer key against what the pipeline caught

| finding | entity | reason | answer key | pipeline | result |
|---|---|---|---|---|---|
| F01 | collections_activity | re-sent copy of a contact already received | 589 | 589 | MATCH |
| F02 | collections_activity | unparseable contact timestamp | 30 | 30 | MATCH |
| F03 | collections_activity | unknown loan account | 40 | 40 | MATCH |
| F04 | collections_activity | missing loan account | 25 | 25 | MATCH |
| F05 | delinquency_monthly | negative days past due | 25 | 25 | MATCH |
| F06 | complaints | unknown complaint category | 18 | 18 | MATCH |
| F07 | complaints | re-sent copy of a complaint already received | 15 | 15 | MATCH |
| F08 | upi_disputes | non-positive amount | 35 | 35 | MATCH |
| F09 | chargebacks | raised before transaction | 20 | 20 | MATCH |
| F10 | loan_accounts | unknown product code | 12 | 12 | MATCH |
| F12 | collections_activity | contact uploaded in a later month's file | 236 | 236 | MATCH |

## Gold row counts against the answer key

| table | answer key | gold (unfiltered) | result |
|---|---|---|---|
| branch_master | 18 | 18 | MATCH |
| chargebacks | 4200 | 4200 | MATCH |
| collections_activity | 63230 | 63230 | MATCH |
| complaint_categories | 10 | 10 | MATCH |
| complaints | 9660 | 9660 | MATCH |
| customer_portfolio | 9000 | 9000 | MATCH |
| delinquency_monthly | 108000 | 108000 | MATCH |
| incentive_slabs | 24 | 24 | MATCH |
| loan_accounts | 6000 | 6000 | MATCH |
| product_holdings | 26916 | 26916 | MATCH |
| product_master | 8 | 8 | MATCH |
| recovery_agents | 60 | 60 | MATCH |
| relationship_managers | 180 | 180 | MATCH |
| repayment_schedule | 5633 | 5633 | MATCH |
| rm_achievement | 3240 | 3240 | MATCH |
| rm_targets | 3240 | 3240 | MATCH |
| upi_disputes | 26316 | 26316 | MATCH |

## Completeness against the senders' manifests

```sql
SELECT status, count(*) AS files, sum(declared_rows) AS declared_rows, sum(landed_rows) AS landed_rows, sum(loaded_rows) AS loaded_rows, sum(quarantined_rows) AS quarantined_rows FROM serverless_lakebase_praneeth_catalog.control_tower_banking.recon_completeness GROUP BY status
```

| status | files | declared_rows | landed_rows | loaded_rows | quarantined_rows |
|---|---|---|---|---|---|
| RECONCILED | 176 | 263807 | 263807 | 263673 | 134 |
| BREAK | 1 | 3492 | 3455 | 3454 | 1 |

```sql
SELECT period, path, declared_rows, landed_rows, declared_amount, landed_amount, break_reason FROM serverless_lakebase_praneeth_catalog.control_tower_banking.recon_completeness WHERE status = 'BREAK'
```

| period | path | declared_rows | landed_rows | declared_amount | landed_amount | break_reason |
|---|---|---|---|---|---|---|
| 2026-06 | dialer/contacts/contacts_2026-06.csv | 3492 | 3455 | 1.742543213E7 | 1.7289699E7 | landed 3455 of 3492 declared rows (37 missing) |

## Quarantined rows keep the reason and the raw record (two per reason)

```sql
SELECT reason, _source_path, raw_record FROM (
  SELECT reason, _source_path, raw_record, row_number() OVER (PARTITION BY reason ORDER BY _source_path, raw_record) AS n
  FROM serverless_lakebase_praneeth_catalog.control_tower_banking.quarantine_collections_activity) WHERE n <= 2 ORDER BY reason
```

| reason | _source_path | raw_record |
|---|---|---|
| missing loan account | field_app/visits/visits_2025-03.json | {"visitId":"ACV202503000","visitEpoch":"1741931380","agentId":"AG050","outcome":"Not Reachable","promisedAmount":"0.0","collectedAmount":"0.0"} |
| missing loan account | field_app/visits/visits_2025-03.json | {"visitId":"ACV202503001","visitEpoch":"1741340902","agentId":"AG017","outcome":"Contacted - PTP","promisedAmount":"34666.44","collectedAmount":"0.0"} |
| unparseable contact timestamp | dialer/contacts/contacts_2025-03.csv | {"call_id":"ACX202503000","acct_no":"LN000218","call_ts_ist":"2026-13-45 25:00:00","agent_code":"AG044","channel":"SMS","disposition":"Contacted - Disputed","ptp_amount":"0.0","collected_amount":"0.0"} |
| unparseable contact timestamp | dialer/contacts/contacts_2025-03.csv | {"call_id":"ACX202503001","acct_no":"LN002922","agent_code":"AG059","channel":"Email","disposition":"Not Reachable","ptp_amount":"0.0","collected_amount":"0.0"} |
