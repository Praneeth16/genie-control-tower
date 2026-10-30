<!-- Generated 2026-10-30 11:07 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 06 — Governance per persona

_Generated 2026-10-30 11:07 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** The same queries return different rows and different values for each persona, enforced by Unity Catalog row filters and column masks declared on the gold tables. Each column is a real identity: a job ran eval/persona_probe.py with run_as set to that persona's service principal.

## Same queries, four identities

| probe | Chief Risk Officer | Head of Collections | Grievance officer | Internal auditor |
|---|---|---|---|---|
| identity (current_user) | dc838e27-417a-46c3-8f91-15cf58d6c6ff | 73bf8d86-1fc2-4f1f-b056-45d5b4efe648 | e9b28811-1884-4ba5-8b50-d8fd342622d1 | 144ffd2d-3e63-4f0a-8f18-bdaa03166c2d |
| probe job run id | 786465942279137 | 96692678152469 | 755561201590495 | 226765858957585 |
| loan_accounts rows visible | 6000 | 3059 | 6000 | 6000 |
| worklist regions visible | Central, East, North, South, West | Central, West | Central, East, North, South, West | Central, East, North, South, West |
| customer_id of LN000011 | CU-4c38082a3a | CU-4c38082a3a | CU-4c38082a3a | CU004839 |
| customer_id of LN000001 (North) | CU-2e7b694513 | row not visible | CU-2e7b694513 | CU005438 |
| agent name AG001 | V. Verma | V. Verma | V. Verma | Vivaan Verma |
| complaint text (REC) | [redacted - free text may contain personal data] | [redacted - free text may contain personal data] | Recovery agent called late at night and used abusive language. | Recovery agent called late at night and used abusive language. |
| letter text | [redacted - free text may contain personal data] | [redacted - free text may contain personal data] | *** SYNTHETIC DOCUMENT — generated for a Databri | *** SYNTHETIC DOCUMENT — generated for a Databri |
| reference documents visible | 5 | 5 | 5 | 5 |
| guardrail_visibility() | Row(recovery_agents=60, complaints=9660, delinquency_monthly=108000, collections_activity=63230) | Row(recovery_agents=30, complaints=4599, delinquency_monthly=55062, collections_activity=33448) | Row(recovery_agents=60, complaints=9660, delinquency_monthly=108000, collections_activity=63230) | Row(recovery_agents=60, complaints=9660, delinquency_monthly=108000, collections_activity=63230) |
| entitlement rows it can read (my_entitlements) | 1 rows, 1 principal | 2 rows, 1 principal | 1 rows, 1 principal | 1 rows, 1 principal |
| read bronze_complaints (raw) | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: |
| read quarantine (raw records) | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: | [INSUFFICIENT_PERMISSIONS] Insufficient privileges: |

## What each persona is entitled to (the entitlements table: access is data)

```sql
SELECT persona, region, can_see_pii, can_see_complaint_text FROM serverless_lakebase_praneeth_catalog.control_tower_banking.entitlements ORDER BY persona, region
```

| persona | region | can_see_pii | can_see_complaint_text |
|---|---|---|---|
| AI CoE administrator | ALL | true | true |
| App guardrail identity | ALL | false | false |
| Chief Risk Officer | ALL | false | false |
| Grievance officer | ALL | false | true |
| Head of Collections | Central | false | false |
| Head of Collections | West | false | false |
| Internal auditor | ALL | true | true |

## Policies attached in Unity Catalog

```sql
SELECT table_name, 'row filter' AS policy, filter_name AS function FROM serverless_lakebase_praneeth_catalog.information_schema.row_filters
WHERE table_schema = 'control_tower_banking'
UNION ALL SELECT table_name, concat('mask on ', column_name), mask_name FROM serverless_lakebase_praneeth_catalog.information_schema.column_masks
WHERE table_schema = 'control_tower_banking' ORDER BY 1, 2
```

| table_name | policy | function |
|---|---|---|
| chargebacks | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| collections_activity | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| collections_case_brief | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| collections_case_status | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| collections_priority | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| collections_priority | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| complaint_ai_triage | mask on summary | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_complaint_text |
| complaint_ai_triage | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| complaint_documents | mask on document_text | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_complaint_text |
| complaint_documents | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.document_visible |
| complaints | mask on complaint_text | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_complaint_text |
| complaints | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| complaints | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| customer_portfolio | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| customer_portfolio | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| delinquency_monthly | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| loan_accounts | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| loan_accounts | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| product_holdings | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| recovery_agents | mask on agent_name | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_person_name |
| recovery_agents | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| relationship_managers | mask on rm_name | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_person_name |
| relationship_managers | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| repayment_schedule | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| rm_achievement | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| rm_targets | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| sla_tracker | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
| upi_disputes | mask on customer_id | serverless_lakebase_praneeth_catalog.control_tower_banking.mask_customer_id |
| upi_disputes | row filter | serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible |
