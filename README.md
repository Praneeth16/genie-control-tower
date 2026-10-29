# Genie Control Tower

**A collections worklist for an Indian retail bank: 589 delinquent accounts (INR 44.1 crore outstanding) ranked with stated reasons, and 40 accounts held from contact because the borrower's grievance is still open. The worklist is rebuilt from the source systems' raw files every time a new month lands.**

All data in this repository is synthetic. The bank, its customers, staff, agencies and branches are invented. No real customer data is used, read or reproduced.

## Who it is for

[YOUR WORDS] The customer is a fictional Indian private-sector retail bank with about 6,000 loans across vehicle finance, microfinance, personal loans, cards, home loans and business loans. Two people buy this.

- The Chief Risk Officer is the executive sponsor. The CRO is measured on gross NPA, credit cost, and conduct breaches and the penalties that follow them.
- The Head of Collections and Recovery is the domain owner. This person is measured on roll-forward rate, cure rate, cost to collect, and contacts outside the hours the RBI permits.

## The problem and why now

[YOUR WORDS]

- Microfinance loans in Solapur and commercial vehicle loans in Indore are both getting worse. The collections team works harder in both places and collects less.
- There is no single list of which accounts to work first and why. Each manager builds one by hand from several systems.
- Some of the pressure breaks the RBI rules on recovery agents. Agents call outside 08:00 to 19:00, uncertified agents make contacts, and borrowers with an open complaint keep being contacted. The RBI's August 2022 circular on recovery agents makes the lender responsible for its agencies' conduct.
- Under the RBI Integrated Ombudsman Scheme, 2021, those borrowers can take an unresolved complaint to the Ombudsman. A complaint about recovery agents is a named ground.
- The data arrives late or short, and nobody notices. In June the dialer vendor's file arrived 37 rows short.

More detail is in [USE_CASE.md](USE_CASE.md).

## What it delivers

| Outcome for the bank | How it shows up | Evidence |
|---|---|---|
| One ranked worklist with the reasons on every row | 589 accounts, each with score components in words | [03](evidence/03_business_results.md), [07](evidence/07_lakebase.md) |
| Conduct rules applied before an account is worked | 40 accounts held for an open grievance, and 113 moved to a certified agency | [03](evidence/03_business_results.md) |
| Every source file checked against what the sender declared | 176 of 177 files reconciled. The short June dialer file is shown as a break. | [02](evidence/02_data_quality.md) |
| Bad rows caught and kept, never dropped | 1,045 rows caught, each with its reason | [02](evidence/02_data_quality.md) |
| Customer letters read as they arrive | 713 letters triaged in the pipeline. 248 allege agent misconduct. | [04](evidence/04_ai_output.md), [05](evidence/05_ai_evaluation.md) |
| Each person sees only what they are entitled to | Same queries, four identities, four different answers | [06](evidence/06_governance.md) |
| Plain-language questions for both leaders | Three governed Genie agents, checked against ground truth | [08](evidence/08_genie.md) |
| Officers' work survives every refresh | An edit made in the app survived the next sync, and the history cannot be rewritten | [07](evidence/07_lakebase.md) |

The headline figures are kept in [evidence/HEADLINES.md](evidence/HEADLINES.md). The README, the deck and the evidence all use those numbers.

## Value

[YOUR WORDS] These figures are illustrative. Each one names its assumption so the bank can replace it with its own number.

| Value driver | From the data | Assumption | Illustrative value |
|---|---|---|---|
| Better recovery on the worked book | INR 44.1 crore outstanding on the worklist | Working the list in score order lifts cure on it by 1 percentage point | INR 44 lakh a year |
| Fewer conduct breaches | 2,499 contacts outside 08:00 to 19:00, which is 4.0% of all contacts | The worklist's reassignment rule removes half of them | About 1,250 fewer breaches |
| No contact while a grievance is open | 40 accounts held today | Each one avoided is one less likely Ombudsman escalation | 40 fewer at-risk cases each month |
| Analyst time | 18 source feeds reconciled by hand each month | 2 analysts for 3 days a month | 6 analyst days a month |

## How it works

[YOUR WORDS] One Lakeflow job runs every stage, in order, when a source system's month-end drop lands. The source files land in a Unity Catalog volume. A pipeline turns them into governed tables. An AI step reads the letters, and a score ranks the delinquent accounts. A second AI step explains each ranking. The cases go to Lakebase, where officers work them in the app. Genie agents answer questions as the signed-in user.

| Stage | What it does | Files |
|---|---|---|
| Lakeflow | Auto Loader reads 18 structured feeds, the scanned letters and the reference documents as they land. The dialer and field app feeds are conformed into one table by two flows. Quality rules quarantine bad rows with a reason. Every file is reconciled against its sender's manifest. Gold tables hold the business rules (DPD bucket, NPA, roll direction, RBI hours, SLA breach, incentive). | [pipeline/](pipeline/), [resources/pipeline.yml](resources/pipeline.yml) |
| Unity Catalog | Row filters and column masks are declared in each gold table. Entitlements are rows in a table. Tags classify personal data. The conduct controls are UC functions. | [governance/](governance/), [pipeline/04_gold.sql](pipeline/04_gold.sql) |
| ML and GenAI | `ai_query` triages each letter inside the pipeline. A points score ranks the worklist. `ai_query` writes a brief for the top 200 accounts. MLflow judges from a different model family evaluate both steps. | [pipeline/06_intelligence.sql](pipeline/06_intelligence.sql), [ai/](ai/) |
| Lakebase | The case queue, refreshed from gold every cycle. Officers own status, owner, notes and next date. A trigger writes the history, which refuses changes. The action plane needs a named approver for every action. | [lakebase/](lakebase/), [serve/sync_cases.py](serve/sync_cases.py) |
| Genie | Three governed agents, deployed from one spec, with business definitions, joins, example SQL and benchmarks. | [genie/](genie/), [resources/genie.yml](resources/genie.yml) |
| Databricks App | The Overview for the CRO and the Worklist and Case for the Head of Collections, plus Ask, Approvals and Governance. Reads run as the signed-in user. | [app/](app/), [resources/app.yml](resources/app.yml) |
| Orchestration | One job, triggered by file arrival on the manifests folder. | [resources/jobs.yml](resources/jobs.yml) |

## Decisions and trade-offs

[YOUR WORDS] The full list, with the options considered, is in [DECISIONS.md](DECISIONS.md).

1. We started from the files each source system sends, not from clean tables, because the pipeline has to do the real work and the answer key can check it.
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

## How AI tools were used

[YOUR WORDS] I built this with Claude Code as a pair engineer, with the Databricks agent skills loaded for pipelines, MLflow evaluation and Lakebase. I made the decisions on the use case, the personas, the trigger and the workspace. The AI wrote most of the code and ran the commands, and I reviewed each step. [BUILD_LOG.md](BUILD_LOG.md) records every attempt, failure and fix.

These practices kept the AI honest.

- Every claim had to be shown with a query, an API response or a job run. The evidence files are generated from the live workspace by [tools/generate_evidence.py](tools/generate_evidence.py), not typed.
- The planted defects have an answer key, so "the pipeline caught the bad rows" is a count that either matches or does not.
- When a judge was wrong, we rewrote the judge's definition and kept both versions in the results. We did not soften judges to raise a pass rate.

One iteration story, with numbers from [evidence/05](evidence/05_ai_evaluation.md):

- The first brief prompt agreed with the bank's conduct rules on 14% of 200 briefs.
- Putting the rules in the prompt raised agreement to 100%. But the grounded judge's pass rate fell from 38% to 21%, and plain language fell from 88% to 51%, because the briefs now cited "Rule 3".
- Giving the model the bank's decision as a fact, and asking it only to explain, raised grounded to 65% with agreement still at 100%. But only 26% of the briefs stayed within 60 words.
- The final prompt asks for two short sentences and forbids adding any step the rule does not state. On the 200 August briefs it scored 90% grounded, 100% rule agreement and 86% plain language.
- The letter triage went from 87.1% to 97.0% agreement with the recorded ground when the prompt defined each ground in the bank's terms.

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
