# Genie Control Tower

**A collections worklist for an Indian retail bank: 589 delinquent accounts (INR 44.1 crore outstanding) ranked with stated reasons, and 40 accounts held from contact because the borrower's grievance is still open. The worklist is rebuilt from the source systems' raw files every time a new month lands.**

All data in this repository is synthetic. The bank, its customers, staff, agencies and branches are invented. No real customer data is used, read or reproduced.

## Proof that it ran

The build ran on a live workspace. The output below is pasted verbatim from the executed notebook, [run_output/verify_run.ipynb](run_output/verify_run.ipynb), whose full text is also in [RUN_EVIDENCE.md](RUN_EVIDENCE.md). Raw job logs fetched from the Jobs API are in [run_output/task_logs/](run_output/task_logs/) and quoted in [BUILD_LOG.md](BUILD_LOG.md). The evidence pack with one file per stage is in [evidence/](evidence/README.md). Nothing in any of them was typed by hand. The builder's email and the workspace hostname are replaced with placeholders.

<!-- run-output:start -->
_Output below was produced on 2026-11-02 19:50 UTC by `tools/verify_run.py` against the deployed bundle and pasted here by that script. Every cell, including the ones not shown here, is in [RUN_EVIDENCE.md](RUN_EVIDENCE.md)._

**Every file reconciled against its sender's manifest**

```
| status | files |
|---|---|
| BREAK | 1 |
| RECONCILED | 176 |
| period | path | feed | declared_rows | landed_rows | loaded_rows | quarantined_rows | declared_amount | landed_amount | status | break_reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06 | dialer/contacts/contacts_2026-06.csv | dialer_contacts | 3492 | 3455 | 3454 | 1 | 1.742543213E7 | 1.7289699E7 | BREAK | landed 3455 of 3492 declared rows (37 missing) |
```

**What the quality rules caught**

```
| entity | check_type | reason | row_count |
|---|---|---|---|
| chargebacks | quarantined | raised before transaction | 20 |
| collections_activity | de-duplicated | re-sent copy of a contact already received | 589 |
| collections_activity | late | contact uploaded in a later month's file | 236 |
| collections_activity | orphaned | unknown loan account | 40 |
| collections_activity | quarantined | unparseable contact timestamp | 30 |
| collections_activity | quarantined | missing loan account | 25 |
| complaints | de-duplicated | re-sent copy of a complaint already received | 15 |
| complaints | orphaned | unknown complaint category | 18 |
| delinquency_monthly | quarantined | negative days past due | 25 |
| loan_accounts | orphaned | unknown product code | 12 |
| upi_disputes | quarantined | non-positive amount | 35 |
| table_name | row_count |
|---|---|
| branch_master | 18 |
| chargebacks | 4200 |
| collections_activity | 63230 |
| complaint_categories | 10 |
| complaints | 9660 |
| customer_portfolio | 9000 |
| delinquency_monthly | 108000 |
| incentive_slabs | 24 |
| loan_accounts | 6000 |
| product_holdings | 26916 |
| product_master | 8 |
| recovery_agents | 60 |
| relationship_managers | 180 |
| repayment_schedule | 5633 |
| rm_achievement | 3240 |
| rm_targets | 3240 |
| upi_disputes | 26316 |
```

**The evaluation, every cycle**

```
| evaluated_at | component | prompt_version | judge_version | metric | value |
|---|---|---|---|---|---|
| 2026-10-29T09:21:00.000Z | case_brief | v1 | j1 | grounded_pass_rate | 0.0 |
| 2026-10-29T09:21:00.000Z | case_brief | v1 | j1 | plain_language_pass_rate | 0.875 |
| 2026-10-29T09:21:00.000Z | case_brief | v1 | j1 | rule_agreement_pass_rate | 0.14 |
| 2026-10-29T09:21:00.000Z | letter_triage | v1 | j1 | conduct_recall | 1.0 |
| 2026-10-29T09:21:00.000Z | letter_triage | v1 | j1 | ground_accuracy | 0.871 |
| 2026-10-29T09:34:00.000Z | case_brief | v1 | j2 | grounded_pass_rate | 0.38 |
| 2026-10-29T09:34:00.000Z | case_brief | v1 | j2 | plain_language_pass_rate | 0.875 |
| 2026-10-29T09:34:00.000Z | case_brief | v1 | j2 | rule_agreement_pass_rate | 0.14 |
| 2026-10-29T09:34:00.000Z | letter_triage | v1 | j2 | conduct_recall | 1.0 |
| 2026-10-29T09:34:00.000Z | letter_triage | v1 | j2 | ground_accuracy | 0.871 |
| 2026-10-29T10:01:00.000Z | case_brief | v2 | j2 | grounded_pass_rate | 0.21 |
| 2026-10-29T10:01:00.000Z | case_brief | v2 | j2 | plain_language_pass_rate | 0.51 |
| 2026-10-29T10:01:00.000Z | case_brief | v2 | j2 | rule_agreement_pass_rate | 1.0 |
| 2026-10-29T10:01:00.000Z | letter_triage | v2 | j2 | conduct_recall | 1.0 |
| 2026-10-29T10:01:00.000Z | letter_triage | v2 | j2 | ground_accuracy | 0.97 |
| 2026-10-29T10:19:00.000Z | case_brief | v3 | j2 | grounded_pass_rate | 0.645 |
| 2026-10-29T10:19:00.000Z | case_brief | v3 | j2 | plain_language_pass_rate | 0.24 |
| 2026-10-29T10:19:00.000Z | case_brief | v3 | j2 | rule_agreement_pass_rate | 1.0 |
| 2026-10-29T10:19:00.000Z | letter_triage | v2 | j2 | conduct_recall | 1.0 |
| 2026-10-29T10:19:00.000Z | letter_triage | v2 | j2 | ground_accuracy | 0.97 |
| 2026-10-29T10:36:00.000Z | case_brief | v3 | j2 | grounded_pass_rate | 0.601 |
| 2026-10-29T10:36:00.000Z | case_brief | v3 | j2 | plain_language_pass_rate | 0.271 |
| 2026-10-29T10:36:00.000Z | case_brief | v3 | j2 | rule_agreement_pass_rate | 0.94 |
| 2026-10-29T10:36:00.000Z | letter_triage | v2 | j2 | conduct_recall | 1.0 |
| 2026-10-29T10:36:00.000Z | letter_triage | v2 | j2 | ground_accuracy | 0.971 |
| 2026-10-29T12:23:00.000Z | case_brief | v4 | j2 | grounded_pass_rate | 0.9 |
| 2026-10-29T12:23:00.000Z | case_brief | v4 | j2 | plain_language_pass_rate | 0.86 |
| 2026-10-29T12:23:00.000Z | case_brief | v4 | j2 | rule_agreement_pass_rate | 1.0 |
| 2026-10-29T12:23:00.000Z | letter_triage | v2 | j2 | conduct_recall | 1.0 |
| 2026-10-29T12:23:00.000Z | letter_triage | v2 | j2 | ground_accuracy | 0.971 |
| 2026-10-29T13:31:00.000Z | case_brief | v4 | j2 | grounded_pass_rate | 0.88 |
| 2026-10-29T13:31:00.000Z | case_brief | v4 | j2 | plain_language_pass_rate | 0.86 |
| 2026-10-29T13:31:00.000Z | case_brief | v4 | j2 | rule_agreement_pass_rate | 1.0 |
| 2026-10-29T13:31:00.000Z | letter_triage | v2 | j2 | conduct_recall | 1.0 |
| 2026-10-29T13:31:00.000Z | letter_triage | v2 | j2 | ground_accuracy | 0.971 |
```

**The cycle job's runs, one started by file arrival**

```
| run_id | trigger | result | started | minutes |
|---|---|---|---|---|
| 922278263548078 | ONE_TIME | SUCCESS | 2026-10-30 11:02 UTC | 1.1 |
| 442065786032196 | ONE_TIME | SUCCESS | 2026-10-30 10:14 UTC | 1.1 |
| 176820566676320 | ONE_TIME | SUCCESS | 2026-10-29 13:27 UTC | 14.3 |
| 199261380563882 | ONE_TIME | SUCCESS | 2026-10-29 12:36 UTC | 0.6 |
| 77252095941105 | ONE_TIME | SUCCESS | 2026-10-29 12:20 UTC | 13.8 |
| 366295467750773 | FILE_ARRIVAL | SUCCESS | 2026-10-29 10:28 UTC | 18.9 |
| 593073173997565 | ONE_TIME | SUCCESS | 2026-10-29 10:15 UTC | 12.7 |
| 476287392178085 | ONE_TIME | SUCCESS | 2026-10-29 09:54 UTC | 17.9 |
| 224454188013264 | ONE_TIME | SUCCESS | 2026-10-29 09:34 UTC | 11.6 |
| 1067591713200279 | ONE_TIME | SUCCESS | 2026-10-29 09:17 UTC | 14.2 |
| 770130929147238 | FILE_ARRIVAL | FAILED | 2026-10-29 09:06 UTC | 0.0 |

run 366295467750773 tasks:
| task | result | seconds |
|---|---|---|
| govern | SUCCESS | 71 |
| case_briefs | SUCCESS | 150 |
| evaluate_ai | SUCCESS | 639 |
| refresh_pipeline | SUCCESS | 274 |
| sync_cases | SUCCESS | 47 |
```

**Genie through the Conversation API, against ground truth**

```
question: What was the microfinance delinquency percentage in Solapur in May 2026?
conversation 01f1d6f69e0f1d52a15308f74557c0f1 message 01f1d6f69e3c18f3b2592e8ae18290f6 status COMPLETED

Genie SQL:
SELECT COUNT(*) AS `accounts`, SUM(CASE WHEN `d`.`dpd_days` > 0 THEN 1 ELSE 0 END) AS `delinquent_accounts`, ROUND(try_divide(100.0 * SUM(CASE WHEN `d`.`dpd_days` > 0 THEN 1 ELSE 0 END),COUNT(*)), 1) AS `delinquency_pct` FROM `serverless_lakebase_praneeth_catalog`.`control_tower_banking`.`delinquency_monthly` AS `d` JOIN `serverless_lakebase_praneeth_catalog`.`control_tower_banking`.`branch_master` AS `b` ON `d`.`branch_id` = `b`.`branch_id` WHERE `d`.`product_code` = 'MFI' AND `b`.`city` = 'Solapur' AND `d`.`snapshot_month` = DATE'2026-05-01'

Genie result:
| accounts | delinquent_accounts | delinquency_pct |
|---|---|---|
| 511 | 223 | 43.6 |

Genie said: **43.6%** was the microfinance delinquency percentage in **Solapur** for **May 2026**. In that scope, **223** out of **511** accounts were delinquent, so just under half of the microfinance accounts in Solapur were past due.

ground-truth SQL:
SELECT ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.delinquency_monthly d
JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.branch_master b ON d.branch_id = b.branch_id
WHERE d.product_code = 'MFI' AND b.city = 'Solapur' AND d.snapshot_month = DATE'2026-05-01'

ground-truth result:
| delinquency_pct |
|---|
| 43.6 |
```

**Lakebase, and the refused rewrite of history**

```
| on_worklist | cases |
|---|---|
| False | 589 |
| True | 589 |
| history_rows | cases_with_history |
|---|---|
| 1990 | 1178 |
| case_id | loan_account_id | status | owner | notes | updated_at |
|---|---|---|---|---|---|
| 1312 | LN000666 | promise_to_pay | Collections officer (West) | Evidence test 2026-10-30 10:14: borrower asked for calls aft | 2026-10-30 10:14:45.252003+00:00 |

UPDATE case_history refused: case_history is append-only: UPDATE refused
```

**The approver-role refusal**

```
| action_type | requires_approval | approver_role |
|---|---|---|
| assign_recovery_agency | True | Collections Head |
| dispatch_customer_letter | True | Service Manager |
| escalate_to_ombudsman | True | Principal Nodal Officer |
| hold_incentive_payout | True | HR Compensation |
| issue_provisional_credit | True | Disputes Manager |
| offer_settlement | True | Credit Committee |
| open_coaching_case | False |  |
| record_ptp | False |  |
| schedule_field_visit | True | Collections Manager |
| waive_fee | True | Branch Manager |
| role | principals |
|---|---|
| Branch Manager | 2 |
| Collections Head | 1 |
| Collections Manager | 2 |
| Control Tower Administrator | 1 |
| Credit Committee | 1 |
| Disputes Manager | 1 |
| HR Compensation | 1 |
| Principal Nodal Officer | 1 |
| Service Manager | 1 |
| principal | approval_roles_held |
|---|---|
| 73bf8d86-1fc2-4f1f-b056-45d5b4efe648 | 0 |
| id | action_type | status | requested_by | approved_by | rejected_by |
|---|---|---|---|---|---|
| 7 | assign_recovery_agency | proposed | builder@example.com |  |  |
| 6 | assign_recovery_agency | proposed | builder@example.com |  |  |
| 5 | assign_recovery_agency | proposed | builder@example.com |  |  |
| 4 | assign_recovery_agency | proposed | builder@example.com |  |  |
| 3 | assign_recovery_agency | proposed | builder@example.com |  |  |

holds_required_role(hold_incentive_payout, head of collections persona) -> False | 73bf8d86-1fc2-4f1f-b056-45d5b4efe648 does not hold the 'HR Compensation' role required to approve hold_incentive_payout (holds no approval roles)
authorise_approver(own action) -> False | separation of duties: you cannot approve an action you requested
holds_required_role(assign_recovery_agency, administrator) -> True | builder@example.com holds the Collections Head role
```
<!-- run-output:end -->

The same query run as four persona service principals, with four different answers, is in [evidence/06](evidence/06_governance.md). The two executive cost figures, credit cost and cost to collect, are computed by the gold table `executive_kpis` and shown in RUN_EVIDENCE.md.

## Who it is for

The customer is a fictional Indian private-sector retail bank. It holds about 6,000 loans across vehicle finance, microfinance, personal loans, cards, home loans and business loans. Two people decide whether to buy this.

- The Chief Risk Officer is the executive sponsor. The CRO is measured on gross NPA, credit cost, and conduct breaches and the penalties that follow them.
- The Head of Collections and Recovery is the domain owner. This person is measured on roll-forward rate, cure rate, cost to collect, and contacts outside the hours the RBI permits.

## The problem and why now

Two parts of the loan book came under stress this year, and the collections team has no single view of what to do about it. The RBI now holds the lender responsible for how its recovery agents behave, so a breach by an agency is the bank's breach.

- Microfinance delinquency in Solapur rose from 11.7% in February 2026 to 43.6% in May. Commercial vehicle delinquency in Indore rose to 26.0% in the same month. The rest of the book stayed near 9%. Both have since eased, to 17.8% and 16.1% in August, but they are still about twice the rest of the book.
- Collections effort followed the stress. In Solapur microfinance, contact attempts rose from 318 in February 2026 to 1,062 in May, more than three times as many, while each attempt collected about the same, INR 575 to 746.
- There is no single list of which accounts to work first and why. Each manager builds one by hand from several systems.
- Some of the pressure breaks the RBI rules on recovery agents. Agents call outside 08:00 to 19:00, uncertified agents make contacts, and borrowers with an open complaint keep being contacted. The RBI's August 2022 circular on recovery agents makes the lender responsible for its agencies' conduct.
- Under the RBI Integrated Ombudsman Scheme, 2021, those borrowers can take an unresolved complaint to the Ombudsman. A complaint about recovery agents is a named ground.
- The data arrives late or short, and nobody notices. In June the dialer vendor's file arrived 37 rows short.

More detail is in [USE_CASE.md](USE_CASE.md).

## What it delivers

| Outcome for the bank | How it shows up | Evidence |
|---|---|---|
| One ranked worklist with the reasons on every row | 589 accounts, each with score components in words | [03](evidence/03_business_results.md), [07](evidence/07_lakebase.md) |
| Conduct rules applied before an account is worked | 40 accounts held for an open grievance, and 113 recommended for reassignment to a certified agency | [03](evidence/03_business_results.md) |
| Every source file checked against what the sender declared | 176 of 177 files reconciled. The short June dialer file is shown as a break. | [02](evidence/02_data_quality.md) |
| Bad rows caught and kept, never dropped | 1,045 rows caught, each with its reason | [02](evidence/02_data_quality.md) |
| Customer letters read as they arrive | 713 letters triaged in the pipeline. 248 allege agent misconduct. | [04](evidence/04_ai_output.md), [05](evidence/05_ai_evaluation.md) |
| Each person sees only what they are entitled to | Same queries, four identities, four different answers | [06](evidence/06_governance.md) |
| Plain-language questions for both leaders | Three governed Genie agents, checked against ground truth | [08](evidence/08_genie.md) |
| Officers' work survives every refresh | An edit made in the app survived the next sync, and the history cannot be rewritten | [07](evidence/07_lakebase.md) |

The headline figures are kept in [evidence/HEADLINES.md](evidence/HEADLINES.md). The README, the deck and the evidence all use those numbers.

## Value

These figures are illustrative. Each row states the assumption behind it, so the bank can put in its own number and see what changes.

| Value driver | From the data | Assumption | Illustrative value |
|---|---|---|---|
| Better recovery on the worked book | INR 44.1 crore outstanding on the worklist | Working the list in score order lifts cure on it by 1 percentage point | INR 44 lakh a year |
| Fewer conduct breaches | 2,499 contacts outside 08:00 to 19:00, which is 4.0% of all contacts | The worklist's reassignment rule removes half of them | About 1,250 fewer breaches |
| No contact while a grievance is open | 40 accounts held today | Each one avoided is one less likely Ombudsman escalation | 40 fewer at-risk cases each month |
| Analyst time | 18 source feeds reconciled by hand each month | 2 analysts for 3 days a month | 6 analyst days a month |

## How it works

One Lakeflow job runs every stage in order. It starts when a source system's month-end files land in a Unity Catalog volume. A pipeline turns the files into governed tables. Inside that pipeline, an AI step reads the customer letters and a points score ranks the delinquent accounts. A second AI step writes a short brief for each ranked account. The cases are then written to Lakebase, where collections officers work them in the app. Genie agents answer questions from either leader, and each answer is scoped to what the signed-in user may see.

| Stage | What it does | Files |
|---|---|---|
| Synthetic data | A seeded generator builds the book of record in memory, then writes the files each source system would send, split by month, in that system's field names, with twelve defects planted and an answer key. The pipeline reads only those files. The stress curves, conduct patterns and letter content are shown in [docs/DATA_GENERATION.md](docs/DATA_GENERATION.md). | [data/](data/), [docs/DATA_GENERATION.md](docs/DATA_GENERATION.md) |
| Lakeflow | Auto Loader reads 18 structured feeds, the scanned letters and the reference documents as they land. The dialer and field app feeds are conformed into one table by two flows. Quality rules quarantine bad rows with a reason. Every file is reconciled against its sender's manifest. Gold tables hold the business rules (DPD bucket, NPA, roll direction, RBI hours, SLA breach, incentive). | [pipeline/](pipeline/), [resources/pipeline.yml](resources/pipeline.yml) |
| Unity Catalog | Row filters and column masks are declared in each gold table. Entitlements are rows in a table. Personas get SELECT on the governed tables only. Tags classify personal data. The conduct controls are UC functions. | [governance/](governance/), [pipeline/04_gold.sql](pipeline/04_gold.sql) |
| ML and GenAI | `ai_query` triages each letter inside the pipeline. A points score ranks the worklist. `ai_query` writes a brief for the top 200 accounts. The triage is graded against the ground the grievance desk recorded. The briefs are graded against the bank's conduct rules and by MLflow judges from a different model family. | [pipeline/06_intelligence.sql](pipeline/06_intelligence.sql), [ai/](ai/) |
| Lakebase | The case queue, refreshed from gold every cycle. Officers own status, owner, notes and next date. A trigger writes the history, which refuses changes. Each case's status is published back to a governed table that Genie reads. The action plane needs a named approver for every action. | [lakebase/](lakebase/), [serve/sync_cases.py](serve/sync_cases.py) |
| Genie | Three governed agents, deployed from one spec, with business definitions, joins, example SQL and benchmarks. | [genie/](genie/), [resources/genie.yml](resources/genie.yml) |
| Databricks App | The Overview for the CRO and the Worklist and Case for the Head of Collections, plus Ask, Approvals and Governance. Reads run as the signed-in user. | [app/](app/), [resources/app.yml](resources/app.yml) |
| Orchestration | One job, triggered by file arrival on the manifests folder. | [resources/jobs.yml](resources/jobs.yml) |

## Decisions and trade-offs

These are the choices that shaped the build. The full list, with the options we considered for each, is in [DECISIONS.md](DECISIONS.md).

1. We started from the files each source system sends, not from clean tables, because the pipeline then has to conform, check and compute everything, and the answer key can confirm that it did.
2. We declared row filters and masks in the gold table definitions, not with ALTER, because an ALTER on a pipeline table is lost on a full refresh.
3. We computed everything from private core tables and governed only the published tables, so a policy never changes an answer.
4. We stored entitlements as rows, so an access change is a data change a steward can audit.
5. We proved governance with four real service principals, so the evidence is what Unity Catalog returned, not a simulation.
6. We ranked with an explainable points score and let the AI explain it, not decide it.
7. We put the letter triage inside the pipeline, so each letter is read once and the output feeds the next stages.
8. We judged the AI with a different model family from the generator.
9. We split Lakebase columns into machine-owned and human-owned, so a refresh never undoes a person's decision.
10. We applied the Unity Catalog region rule to Lakebase rows in the app, with Unity Catalog as the source of truth.
11. We triggered the cycle on file arrival, so a run starts only when a drop is complete.
12. We kept the planted truncated file as a visible break, because it answers "what happens with a late or corrupted file?"
13. We published the officers' case status from Lakebase back to a governed table, so Genie and the CRO see the work, not only the worklist.
14. We granted the personas SELECT on the governed tables only, because the schema also holds raw layers with no policy.

## How AI tools were used

I built this with Claude Code as a pair engineer, with the Databricks agent skills loaded for pipelines, MLflow evaluation and Lakebase. I chose the use case, the two personas, the file-arrival trigger and the workspace. The AI wrote most of the code and ran the commands. I reviewed each step and sent the result through two rounds of review by a second AI tool, Codex, before merging. [BUILD_LOG.md](BUILD_LOG.md) records every attempt, failure and fix, including both review rounds.

These practices kept the AI honest.

- Every claim had to be shown with a query, an API response or a job run. The evidence files are generated from the live workspace by [tools/generate_evidence.py](tools/generate_evidence.py), not typed.
- The planted defects have an answer key, so "the pipeline caught the bad rows" is a count that either matches or does not.
- When a judge was wrong, we rewrote the judge's definition and kept both versions in the results. We did not soften judges to raise a pass rate.

One iteration story, with numbers from [evidence/05](evidence/05_ai_evaluation.md):

- The first brief prompt agreed with the bank's conduct rules on 14% of 200 briefs.
- Putting the rules in the prompt raised agreement to 100%. But the grounded judge's pass rate fell from 38% to 21%, and plain language fell from 88% to 51%, because the briefs now cited "Rule 3".
- Giving the model the bank's decision as a fact, and asking it only to explain, raised grounded to 64.5% with agreement still at 100%, on the same July accounts. But only 23.5% of the briefs stayed within 60 words.
- The final prompt asks for two short sentences and forbids adding any step the rule does not state. On the 200 August briefs it scored 90% grounded, 100% rule agreement and 86% plain language.
- The letter triage went from 87.1% to 97.0% agreement with the recorded ground, on the same 690 July letters, when the prompt defined each ground in the bank's terms.

## Repository layout

```
data/            the synthetic book of record and the source-system exports with planted defects
pipeline/        the Lakeflow pipeline: bronze, silver and quarantine, core, gold, completeness, AI and score
governance/      entitlements, policy functions, the conduct controls, tags and persona access
ai/              the case brief step and the evaluation
serve/           the Lakebase case sync
lakebase/        Postgres migrations: action plane, case queue, history triggers
genie/           the three Genie agents as code, and the generated space files
dashboards/      the AI/BI dashboard as code
app/             the Databricks App (FastAPI and React)
eval/            Genie benchmarks, held-out set, grader, persona probe
tools/           SQL runner for job tasks, the held-back month, the evidence generator
resources/       bundle resources: pipeline, jobs, personas, Genie, dashboard, app
evidence/        text evidence from the final run
deck/            the deck (HTML and PDF), its outline, and the role-play script
```

## How to run it

You need a workspace with Unity Catalog, serverless compute, a serverless SQL warehouse, foundation model endpoints and Lakebase. You also need the Databricks CLI 1.22 or later.

1. Create the Lakebase project.

   ```bash
   databricks postgres create-project genie-control-tower --profile <profile>
   ```

2. Create four service principals for the personas, and give yourself the Service Principal User role on each.

3. Set the variables in `.databricks/bundle/dev/variable-overrides.json`: `warehouse_id`, `uc_catalog`, and the four `persona_*` application ids.

4. Write the Genie space files and the dashboard file for your catalog, and build the frontend. The committed files are written for the catalog this was built in.

   ```bash
   export CT_CATALOG=<catalog> DATABRICKS_WAREHOUSE_ID=<id> LAKEBASE_ENDPOINT=x
   python3 genie/create_genie_agents.py --write
   python3 dashboards/build_dashboard.py --write
   npm --prefix app/frontend install && npm --prefix app/frontend run build
   ```

5. Deploy, then set up storage, the source files, the policies and the Lakebase schema.

   ```bash
   databricks bundle deploy --profile <profile>
   databricks bundle run ct_setup --profile <profile>
   ```

   The setup job writes the files. Their manifests start the cycle job on their own.

6. Start the app and grant its service principal.

   ```bash
   databricks bundle run ct_app --profile <profile>
   python3 scripts/grant_app_sp.py --app genie-control-tower
   ```

7. Land the held-back month. Its manifest starts the cycle again.

   ```bash
   databricks bundle run ct_land_period --profile <profile>
   ```

8. Generate the evidence.

   ```bash
   python3 tools/generate_evidence.py --profile <profile>
   ```

## Known issues

[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) lists what was fixed and what is still open. [docs/DESIGN.md](docs/DESIGN.md) explains the earlier design decisions in the agent and the action plane.

## Licence

Apache 2.0. See [LICENSE](LICENSE). This is not an official Databricks product. The regulatory rules in the controls are paraphrased for the demo and are not legal advice.
