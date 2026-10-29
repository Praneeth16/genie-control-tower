<!-- Generated 2026-10-29 12:35 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 05 — AI evaluation and the iteration history

_Generated 2026-10-29 12:35 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** Both AI steps are measured: the triage against the ground the grievance desk recorded on each complaint, and the briefs against the bank's deterministic conduct rules and by MLflow Guidelines judges running on a different model family from the generator. Every prompt version and judge version stays in the results, so the iteration is visible, including the regressions.

## Every evaluation run, in order

Runs before the final month landed were on the July data; later runs are on the full data. v1 to v3 of the briefs were compared on the same July accounts.

```sql
SELECT date_format(evaluated_at, 'yyyy-MM-dd HH:mm') AS evaluated_utc, component, prompt_version, judge_version,
  max(CASE WHEN metric IN ('letters', 'briefs') THEN cast(value AS INT) END) AS rows_evaluated,
  max(CASE WHEN metric = 'ground_accuracy' THEN round(value, 3) END) AS ground_accuracy,
  max(CASE WHEN metric = 'conduct_recall' THEN round(value, 3) END) AS conduct_recall,
  max(CASE WHEN metric = 'conduct_precision' THEN round(value, 3) END) AS conduct_precision,
  max(CASE WHEN metric = 'rule_agreement_pass_rate' THEN round(value, 3) END) AS rule_agreement,
  max(CASE WHEN metric = 'grounded_pass_rate' THEN round(value, 3) END) AS grounded,
  max(CASE WHEN metric = 'conduct_compliant_pass_rate' THEN round(value, 3) END) AS conduct_compliant,
  max(CASE WHEN metric = 'actionable_pass_rate' THEN round(value, 3) END) AS actionable,
  max(CASE WHEN metric = 'plain_language_pass_rate' THEN round(value, 3) END) AS plain_language,
  max(CASE WHEN metric = 'within_60_words_pass_rate' THEN round(value, 3) END) AS within_60_words,
  max(CASE WHEN metric = 'numbers_grounded_pass_rate' THEN round(value, 3) END) AS numbers_grounded
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.ai_eval_summary GROUP BY eval_run_id, evaluated_at, component, prompt_version, judge_version
ORDER BY evaluated_at, component
```

| evaluated_utc | component | prompt_version | judge_version | rows_evaluated | ground_accuracy | conduct_recall | conduct_precision | rule_agreement | grounded | conduct_compliant | actionable | plain_language | within_60_words | numbers_grounded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-29 09:21 | case_brief | v1 | j1 | 200 |  |  |  | 0.14 | 0.0 | 1.0 | 0.95 | 0.875 | 0.875 | 0.965 |
| 2026-10-29 09:21 | letter_triage | v1 | j1 | 690 | 0.871 | 1.0 | 1.0 |  |  |  |  |  |  |  |
| 2026-10-29 09:34 | case_brief | v1 | j2 | 200 |  |  |  | 0.14 | 0.38 | 1.0 | 0.95 | 0.875 | 0.875 | 0.995 |
| 2026-10-29 09:34 | letter_triage | v1 | j2 | 690 | 0.871 | 1.0 | 1.0 |  |  |  |  |  |  |  |
| 2026-10-29 10:01 | case_brief | v2 | j2 | 200 |  |  |  | 1.0 | 0.21 | 0.99 | 1.0 | 0.51 | 0.96 | 0.99 |
| 2026-10-29 10:01 | letter_triage | v2 | j2 | 690 | 0.97 | 1.0 | 1.0 |  |  |  |  |  |  |  |
| 2026-10-29 10:19 | case_brief | v3 | j2 | 200 |  |  |  | 1.0 | 0.645 | 1.0 | 1.0 | 0.24 | 0.235 | 1.0 |
| 2026-10-29 10:19 | letter_triage | v2 | j2 | 690 | 0.97 | 1.0 | 1.0 |  |  |  |  |  |  |  |
| 2026-10-29 10:36 | case_brief | v3 | j2 | 218 |  |  |  | 0.94 | 0.601 | 1.0 | 1.0 | 0.271 | 0.261 | 1.0 |
| 2026-10-29 10:36 | letter_triage | v2 | j2 | 713 | 0.971 | 1.0 | 1.0 |  |  |  |  |  |  |  |
| 2026-10-29 12:23 | case_brief | v4 | j2 | 200 |  |  |  | 1.0 | 0.9 | 0.985 | 0.985 | 0.86 | 0.86 | 1.0 |
| 2026-10-29 12:23 | letter_triage | v2 | j2 | 713 | 0.971 | 1.0 | 1.0 |  |  |  |  |  |  |  |

## Remaining triage disagreements with the recorded ground

```sql
SELECT c.rbi_category AS recorded, t.predicted_rbi_ground AS predicted, count(*) AS letters
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaint_ai_triage t JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.complaints c USING (complaint_id)
WHERE t.predicted_rbi_ground <> c.rbi_category GROUP BY ALL ORDER BY 3 DESC
```

| recorded | predicted | letters |
|---|---|---|
| Deposit accounts | Levy of charges | 21 |

## Judge rationales for brief failures in the current version (verbatim)

```sql
SELECT check_name, record_id, rationale FROM serverless_lakebase_praneeth_catalog.control_tower_banking.ai_eval_results
WHERE component = 'case_brief' AND prompt_version = 'v4' AND NOT passed
QUALIFY row_number() OVER (PARTITION BY check_name ORDER BY record_id) <= 2 ORDER BY check_name
```

| check_name | record_id | rationale |
|---|---|---|
| actionable | LN000457 | The explanation does give a clear reason for why the account is on the worklist: it cites the high delinquency at 109 days past due, overdue amount, high rank, broken promises to pay, and uncertified or lapsed agent contacts. However, the recommended_action is only "assign_recovery_agency," which is too generic relative to the stated reason and the bank rule. Because the key issue includes uncertified/lapsed agent contact, the concrete next step should specifically indicate reassignment to a certified agency and/or conduct review. Therefore, the response does not fully satisfy the guideline. |
| actionable | LN003153 | The explanation does give a collections officer a clear reason for the account's worklist position: the loan is 141 days past due, in NPA status, has a large outstanding principal, no recent payments, and has conduct concerns involving alleged agent misconduct and uncertified-agent contacts. However, the recommended_action is only "assign_recovery_agency," which is too generic relative to the stated reason and the bank rule. The facts specifically call for reassignment to a certified agency and conduct review, but the action does not specify certification or reviewing the misconduct/agent-conduct issue. Therefore, the recommended_action is not fully consistent with the reason provided. |
| conduct_compliant | LN002568 | The facts show open_grievance is true, and the response's recommended_action is hold_contact, so that part of the guideline is satisfied. The facts also show uncertified_agent_contacts_90d is 6, which triggers the requirement that the recommended_action must not be schedule_field_visit and the explanation must mention the conduct issue. The recommended_action is hold_contact, so it is not schedule_field_visit. However, the explanation does not mention the uncertified-agent contact issue; it only refers generally to an open grievance and a conduct concern. Therefore, the response does not fully satisfy the guideline. |
| conduct_compliant | LN003549 | The request facts show open_grievance is true, so the response's recommended_action must be hold_contact; it is, so that part is satisfied. However, the facts also show uncertified_agent_contacts_90d is 5 and letter_alleges_agent_misconduct is true. Therefore, the recommended_action must not be schedule_field_visit, and the explanation must mention the conduct issue. The recommended_action is not schedule_field_visit, but the explanation only mentions the open grievance and suspension of recovery contact; it does not mention the alleged agent misconduct or uncertified-agent contacts. Therefore, the guideline is not fully satisfied. |
| grounded | LN000041 | Most factual claims in the explanation are present in the facts JSON: the product is Microfinance Group Loan, dpd_days is 111, is_npa is true, overdue_amount_inr is 12083.0, and contacts_90d, payments_90d, and promises_to_pay_90d are all 0. The bank_rule field also contains "Settlement or legal review." However, the explanation additionally states that the bank rule was "triggered by the account's NPA status at 111 days past due." The facts JSON does not state what triggered the bank rule, only what the bank rule is. This is an unsupported causal factual claim, so the response does not fully comply. |
| grounded | LN000457 | Most factual claims in the explanation are present in the facts JSON: the product is Passenger Vehicle Loan, priority rank is 8, days past due is 109, overdue amount is INR 131,051, the bank rule says to reassign to a certified agency and review conduct, and there were 7 uncertified-agent contacts in 90 days. However, the explanation states there were "4 broken promises to pay in 90 days." The facts JSON contains 4 promises_to_pay_90d, but the score driver states "3 promise(s) to pay not kept in 90 days." Therefore, the claim that there were 4 broken promises is not present in the facts JSON and conflicts with the available fact of 3 not-kept promises. |
| plain_language | LN000021 | The explanation is about 64 words, which exceeds the maximum of 60 words. Therefore it does not fully comply with the guideline. The language is generally understandable for a branch collections officer and includes standard banking terms like SMA, but the word-limit requirement is not satisfied. |
| plain_language | LN000526 | The explanation is 63 words, which exceeds the guideline limit of at most 60 words. The language is generally plain English and uses banking/collections terms like NPA, overdue amount, settlement, and legal review, but the word-count requirement is not satisfied. |
| within_60_words | LN000021 | 64 words |
| within_60_words | LN000526 | 63 words |

## Judge rationales that drove each iteration (earlier versions)

```sql
SELECT prompt_version, judge_model, check_name, record_id, rationale FROM serverless_lakebase_praneeth_catalog.control_tower_banking.ai_eval_results
WHERE component = 'case_brief' AND prompt_version IN ('v1', 'v2') AND NOT passed AND check_name IN ('grounded', 'plain_language', 'rule_agreement')
QUALIFY row_number() OVER (PARTITION BY prompt_version, judge_model, check_name ORDER BY record_id) = 1
ORDER BY prompt_version, judge_model, check_name
```

| prompt_version | judge_model | check_name | record_id | rationale |
|---|---|---|---|---|
| v1 |  | rule_agreement | LN000065 | suggested assign_recovery_agency; conduct rules give offer_settlement |
| v1 | databricks-gpt-5-5 | grounded | LN000065 | The explanation includes several facts that are present in the facts JSON, such as 127 DPD, NPA status, overdue amount, outstanding principal, one forward roll in the last 3 months, zero contacts/promises/payments in 90 days, no conduct flags, and no open grievance. However, it also adds information or inferences not explicitly present in the facts JSON: it expands "CV" to "commercial vehicle," states that direct recovery agency intervention is "the logical next step," and says no conduct flags or grievances "restrict action." These are not facts contained in the provided JSON. Therefore, the response does not fully comply with the guideline. |
| v1 | databricks-gpt-5-5 | plain_language | LN000125 | The explanation is about 62 words, which exceeds the guideline limit of at most 60 words. It is generally plain English and uses banking/collections terms such as CV, DPD, NPA, outstanding principal, contacts, and agent, but the word-count requirement is not satisfied. |
| v1 | databricks-gpt-5-5 (j2) | grounded | LN000065 | Most factual claims in the explanation are supported by the facts JSON: CV is present as product_code, 127 DPD is present, NPA status is present, the overdue and outstanding INR amounts are present, one forward roll in the last 3 months is present, zero contacts/promises/payments in 90 days are present, open_grievance is false, and conduct_flags is an empty list. However, the explanation expands “CV” as “commercial vehicle,” and that expansion is not present in the facts JSON. Because this is a factual claim not contained in the provided facts, the response does not fully comply with the guideline. |
| v1 | databricks-gpt-5-5 (j2) | plain_language | LN000125 | The explanation is about 62 words, exceeding the guideline limit of at most 60 words. It is mostly plain English and uses standard collections/banking terms like DPD and NPA, but the word-count requirement is not satisfied. |
| v2 | databricks-gpt-5-5 (j2) | grounded | LN000065 | Most factual claims in the explanation are present in the facts JSON: the product is Commercial Vehicle Loan, dpd_days is 127, the account is NPA with bucket NPA (90+), the overdue amount is INR 122802.0, the outstanding principal is INR 386778.0, and conduct_flags is empty. The statement that recovery contact is permitted is an allowed interpretation from the absence of conduct flags. However, the explanation also states, "Per Rule 3, NPA status triggers a settlement offer." The request's facts JSON does not contain any "Rule 3" or any fact that NPA status triggers a settlement offer. This is an unsupported factual claim, so the guideline is not fully satisfied. |
| v2 | databricks-gpt-5-5 (j2) | plain_language | LN000065 | The explanation is 47 words, so it meets the 60-word limit. It is mostly plain English. However, it uses non-standard or internal terms such as “conduct flags” and “Per Rule 3,” which are not standard banking terms like DPD, NPA, or SMA. |
