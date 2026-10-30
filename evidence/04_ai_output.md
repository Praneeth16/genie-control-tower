<!-- Generated 2026-10-29 13:53 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 04 — AI output, verbatim

_Generated 2026-10-29 13:53 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** The two AI steps produce structured output that the next stages consume: the letter triage feeds the worklist's conduct flags and the grievance agent; the briefs feed the Lakebase case queue. Samples are verbatim, with exactly what the model was given.

## Letter triage (ai_query inside the pipeline), one letter per recorded ground

```sql
SELECT complaint_id, rbi_category AS recorded_ground, predicted_rbi_ground, alleges_conduct_breach,
       breach_types, urgency, summary, prompt_version, model FROM (
  SELECT t.*, c.rbi_category, row_number() OVER (PARTITION BY c.rbi_category ORDER BY t.complaint_id) AS n
  FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaint_ai_triage t JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.complaints c USING (complaint_id)) WHERE n = 1
```

| complaint_id | recorded_ground | predicted_rbi_ground | alleges_conduct_breach | breach_types | urgency | summary | prompt_version | model |
|---|---|---|---|---|---|---|---|---|
| CM0000004 | Cards | Cards | false | [] | high | Customer's card was charged twice for a single restaurant transaction and the duplicate charge has not been reversed. | v2 | databricks-claude-sonnet-4-6 |
| CM0000005 | Deposit accounts | Deposit accounts | false | [] | medium | Customer's fixed deposit was closed prematurely without their instruction and interest was recalculated at a reduced rate. | v2 | databricks-claude-sonnet-4-6 |
| CM0000082 | Levy of charges | Levy of charges | false | [] | medium | Customer complains that a processing charge was deducted on a loan despite not being disclosed at sanction and having been promised a waiver. | v2 | databricks-claude-sonnet-4-6 |
| CM0000002 | Loans and advances | Loans and advances | false | [] | high | An EMI was debited after the loan was closed and the excess amount has not been refunded. | v2 | databricks-claude-sonnet-4-6 |
| CM0000009 | Mis-selling | Mis-selling | false | [] | medium | Customer was incorrectly told that an insurance policy bundled with their loan was compulsory and is requesting cancellation and a refund of the premium paid. | v2 | databricks-claude-sonnet-4-6 |
| CM0000012 | Other | Other | false | [] | medium | Customer submitted re-KYC documents at the branch five weeks ago but the account remains restricted with no resolution or explanation provided. | v2 | databricks-claude-sonnet-4-6 |
| CM0000001 | Payment systems | Payment systems | false | [] | high | Customer's account was debited in an ATM transaction where cash was not dispensed, and a branch complaint raised the same day has received no acknowledgement. | v2 | databricks-claude-sonnet-4-6 |
| CM0000003 | Recovery agents | Recovery agents | true | ["no_identification"] | medium | A recovery agent visited the customer regarding a two-wheeler loan account, refused to show identity proof, and remained on the premises past 19:00 until a family member returned. | v2 | databricks-claude-sonnet-4-6 |

## Case briefs (current prompt version), with the facts the model was given

```sql
SELECT b.loan_account_id, b.priority_rank, b.facts, b.explanation, b.recommended_action, b.prompt_version
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_case_brief b WHERE b.prompt_version = 'v4' ORDER BY b.priority_rank LIMIT 4
```

| loan_account_id | priority_rank | facts | explanation | recommended_action | prompt_version |
|---|---|---|---|---|---|
| LN000770 | 1 | {"product":"Commercial Vehicle Loan","region":"Central","snapshot_month":"2026-08-01","dpd_days":121,"dpd_bucket":"4-NPA (90+)","is_npa":true,"outstanding_principal_inr":3297017.0,"overdue_amount_inr":997348.0,"forward_rolls_last_3_months":2,"contacts_90d":0,"promises_to_pay_90d":0,"payments_90d":0,"out_of_hours_contacts_90d":0,"uncertified_agent_contacts_90d":0,"open_grievance":false,"letter_alleges_agent_misconduct":false,"priority_score":85,"priority_rank":1,"score_drivers":["Days past due 121 (4-NPA (90+)): +50","Rolled to a worse bucket in 2 of the last 3 months: +20","Outstanding INR 3,297,017: +15"],"conduct_flags":[],"bank_rule":"Settlement or legal review"} | This Commercial Vehicle Loan is ranked first on the worklist at 121 days past due in the 4-NPA (90+) bucket, with an outstanding principal of INR 3,297,017 and two forward rolls in the last three months. The officer should pursue settlement or legal review, as the account is NPA with an overdue amount of INR 9,97,348. | offer_settlement | v4 |
| LN000666 | 2 | {"product":"Commercial Vehicle Loan","region":"Central","snapshot_month":"2026-08-01","dpd_days":108,"dpd_bucket":"4-NPA (90+)","is_npa":true,"outstanding_principal_inr":2592106.0,"overdue_amount_inr":699869.0,"forward_rolls_last_3_months":2,"contacts_90d":0,"promises_to_pay_90d":0,"payments_90d":0,"out_of_hours_contacts_90d":0,"uncertified_agent_contacts_90d":0,"open_grievance":false,"letter_alleges_agent_misconduct":false,"priority_score":85,"priority_rank":2,"score_drivers":["Days past due 108 (4-NPA (90+)): +50","Rolled to a worse bucket in 2 of the last 3 months: +20","Outstanding INR 2,592,106: +15"],"conduct_flags":[],"bank_rule":"Settlement or legal review"} | This Commercial Vehicle Loan is ranked 2nd on the worklist, driven by 108 days past due in the 4-NPA (90+) bucket, two forward rolls in the last three months, and an outstanding principal of INR 2,592,106. The officer should pursue settlement or legal review, as the account is NPA with an overdue amount of INR 699,869 and zero contacts, promises, or payments in the last 90 days. | offer_settlement | v4 |
| LN005321 | 3 | {"product":"Commercial Vehicle Loan","region":"Central","snapshot_month":"2026-08-01","dpd_days":110,"dpd_bucket":"4-NPA (90+)","is_npa":true,"outstanding_principal_inr":2335862.0,"overdue_amount_inr":642362.0,"forward_rolls_last_3_months":2,"contacts_90d":13,"promises_to_pay_90d":3,"payments_90d":4,"out_of_hours_contacts_90d":1,"uncertified_agent_contacts_90d":9,"last_contact_date":"2026-08-27","open_grievance":false,"letter_alleges_agent_misconduct":false,"priority_score":85,"priority_rank":3,"score_drivers":["Days past due 110 (4-NPA (90+)): +50","Rolled to a worse bucket in 2 of the last 3 months: +20","Outstanding INR 2,335,862: +15"],"conduct_flags":["1 contact(s) outside 08:00-19:00 IST in 90 days","9 contact(s) by an uncertified or lapsed agent in 90 days"],"bank_rule":"Reassign to a certified agency and review conduct"} | This Commercial Vehicle Loan is ranked 3rd on the worklist due to 110 days past due (NPA), an outstanding principal of INR 2,335,862, and two forward rolls in the last three months. Reassign to a certified agency and review conduct, as 9 contacts were made by an uncertified or lapsed agent in the last 90 days. | assign_recovery_agency | v4 |
| LN005880 | 4 | {"product":"Commercial Vehicle Loan","region":"Central","snapshot_month":"2026-08-01","dpd_days":149,"dpd_bucket":"4-NPA (90+)","is_npa":true,"outstanding_principal_inr":2303082.0,"overdue_amount_inr":806079.0,"forward_rolls_last_3_months":2,"contacts_90d":0,"promises_to_pay_90d":0,"payments_90d":0,"out_of_hours_contacts_90d":0,"uncertified_agent_contacts_90d":0,"open_grievance":false,"letter_alleges_agent_misconduct":false,"priority_score":85,"priority_rank":4,"score_drivers":["Days past due 149 (4-NPA (90+)): +50","Rolled to a worse bucket in 2 of the last 3 months: +20","Outstanding INR 2,303,082: +15"],"conduct_flags":[],"bank_rule":"Settlement or legal review"} | This Commercial Vehicle Loan is ranked 4th on the worklist at 149 days past due in the 4-NPA (90+) bucket, with an outstanding principal of INR 2,303,082 and two forward rolls in the last three months. The officer should pursue settlement or legal review, as the account is NPA with zero contacts, payments, or promises to pay in the last 90 days. | offer_settlement | v4 |

## Coverage

```sql
SELECT 'letter_triage' AS step, count(*) AS rows, count(error) AS errors FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaint_ai_triage
UNION ALL SELECT 'case_brief', count(*), count(error) FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_case_brief WHERE prompt_version = 'v4'
```

| step | rows | errors |
|---|---|---|
| letter_triage | 713 | 0 |
| case_brief | 200 | 0 |
