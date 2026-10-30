<!-- Generated 2026-10-30 11:08 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 10 — The Databricks App

_Generated 2026-10-30 11:08 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** The deployed app serves every screen's route as the signed-in user (on-behalf-of token active). The bank's conduct control refuses an allocation to an uncertified agent and passes one to a certified agent. The action's region comes from the governed record, not the request, and the person who raised an action cannot approve it.

App `genie-control-tower` at https://genie-control-tower-7474654904882204.aws.databricksapps.com. On-behalf-of user token active: **True**; require OBO: **True**; Genie agents configured: {'COLLECTIONS': True, 'GRIEVANCE': True, 'RM': True}.

| route | HTTP | response (start) |
|---|---|---|
| GET /api/health | 200 | {"status":"ok","service_identity":"f1c1fa6f-93ac-411a-a662-80f64388c21d","caller":"builder@example.com","obo_active":true,"catalog":"serverless_lake |
| GET /api/overview | 200 | {"kpis":{"as_of_month":"2026-08-01","gnpa_pct":"2.95","gnpa_pct_prev":"3.51","roll_forward_pct":"9.1","delinquent_outstanding_inr":"4.40958259E8","delinquent_ac |
| GET /api/cases?limit=5 | 200 | {"regions":["Central","East","North","South","West"],"cases":[{"case_id":136,"loan_account_id":"LN000770","region":"Central","branch_id":"BR007","product_code": |
| GET /api/governance/scope | 200 | {"identity":"builder@example.com","personas":["AI CoE administrator"],"can_see_pii":true,"can_see_complaint_text":true,"entitlements":[{"principal": |
| GET /api/governance/policies | 200 | {"row_filters":[{"table_name":"collections_activity","filter_name":"serverless_lakebase_praneeth_catalog.control_tower_banking.region_visible","on_columns":"reg |
| GET /api/actions | 200 | {"actions":[{"id":5,"agent":"control-tower-supervisor","action_type":"assign_recovery_agency","subject":"LN000770","payload":{"reason":"evidence route check","a |
| POST /api/act, assign_recovery_agency with agent AG024 | 200 | guardrail passed=False; breaches=['recovery agent AG024 may not be deployed: agent is not RBI conduct certified']; region resolved server-side: Central; requested_by=builder@example.com |
| POST /api/act, assign_recovery_agency with agent AG007 | 200 | guardrail passed=True; breaches=none; region resolved server-side: Central; requested_by=builder@example.com |
| POST /api/actions/{id}/approve (by the person who raised it) | 403 | {"detail":"separation of duties: you cannot approve an action you requested"} |
| POST /api/ask | 200 | {"session_id":4,"session_uuid":"b90d1f8d-7a11-4a8c-b6bc-891be568ca8c","question":"How many accounts are on the collections worklist in each region?","latency_ms |
