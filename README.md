# Genie Control Tower

**A governed multi-agent reference for retail banking on Databricks** — collections and recovery,
service and grievance, relationship-manager performance, with RBI conduct rules enforced as Unity
Catalog objects.

A working reference for the question banks actually get stuck on: **not "can Genie answer this?" but "can I
trust the answer, can I let it act, and what does it cost?"**

Three governed [Genie Agents](https://docs.databricks.com/aws/en/genie/) under one supervisor, an action
plane where every write needs a named human approver, guardrails implemented as Unity Catalog objects
rather than prompt text, semantic search over a document corpus, a live-call assist lane, and an evaluation
suite that reports its own held-out score.

**Everything here is synthetic.** 268,019 rows of a fictional Indian retail bank, generated from a seed by
`data/generate_banking_data.py`. No real customer data is used, read or reproduced anywhere.

---

## Why this exists

The common failure with Genie is not accuracy. It is that spaces get built and then not used — because
nobody could answer three questions about them. This project answers each one with a mechanism you can
inspect:

| Question | Mechanism |
|---|---|
| **Can I trust the number?** | Reads run *on behalf of the signed-in user*, so Unity Catalog row filters and column masks apply per person from one shared agent. A benchmark grades answers against ground-truth SQL executed at run time, checking the result grid and the narrative prose, and reports a **held-out** score rather than only the tuned one. |
| **Can I let it act?** | Nothing writes from generated SQL. Actions are *proposed*, checked against controls that are UC functions, approved by a named human, re-checked at execution, and recorded in append-only lineage. A kill switch fails closed. |
| **What does it cost?** | Per-question cost and latency attribution in the Governance tab, and an explicit Genie message budget — the API allows roughly 5 messages/minute *for the whole workspace*, which is the constraint nobody warns you about. |

---

## What it does

Analysis, the live call and the letter corpus share **one chat thread** — one line of enquiry, so the
account number carries between them instead of being retyped on another screen. The composer routes each
message deterministically and every turn states which lane took it and why.

**Analysis** — one question, routed across three domain agents in parallel under a shared deadline, then fused
into one causal answer with a proposed next action. Routing is scored separately from answering, because a
router miss and a Genie miss have different fixes.

**Live call** — live agent assist for a collections call. Speech-to-text runs **in the browser**, so no
customer audio leaves the device or reaches a model. The server resolves spoken account numbers (English,
Hindi, Marathi — Devanagari script, Devanagari digit glyphs and Roman transliteration) and runs the RBI
conduct controls *while the call is happening*: the 08:00–19:00 IST contact window, a grievance hold, NPA
classification. Agent-assist by design, not a customer-facing voice bot — see [why](docs/DESIGN.md#voice).

**Dashboard** — an AI/BI dashboard built as code and published **without embedded credentials**, so every
tile runs as the viewer under the same filters and masks that govern the agents. The dashboard and the
agents cannot disagree with each other.

**Documents** — semantic search over 713 complaint letters in a Unity Catalog Volume, then parse one and
draft a grounded reply as an **unsigned** draft. The index is queried as the app's service principal and
the records it finds are re-read *as the caller*: retrieval locates, governance still decides.

**Approvals** — the action plane. Propose → guardrail → named approval → execute, with the guardrail
verdicts and their provenance shown for each step.

**Governance** — six evidence panels: what you are entitled to see, what is enforced in Unity Catalog, the
conduct policies, guardrail integrity, the kill switch, and usage and cost.

---

## Architecture

```
                    ┌──────────────────────────── Databricks App (FastAPI + React) ───┐
  signed-in user ──▶│  /api/ask ─▶ router ─▶ 3 parallel Genie legs ─▶ fuser           │
   (OBO token)      │  /api/voice/assist ─▶ entity extraction ─▶ governed prefetch    │
                    │  /api/documents/search ─▶ Vector Search ─▶ governed read-back   │
                    │  /api/act ─▶ guardrails ─▶ approval ─▶ execute                  │
                    └───────┬──────────────────────┬─────────────────┬────────────────┘
                            │ AS THE USER          │ AS THE APP SP   │
                            ▼                      ▼                 ▼
                 Unity Catalog (18 tables)   UC control functions   Lakebase (Postgres)
                 row filters + column masks  conduct / hours / hold  actions, approvals,
                 Volumes (713 documents)     guardrail_visibility()  append-only lineage
                 Vector Search index
```

**Two identities, deliberately.** Business reads run as the **user**. Guardrail verification runs as the
**app service principal** — because a control that the caller's own row filters can blind is not a control.
That single distinction is the reason most of this design looks the way it does.

Full rationale, including the defects that shaped it, is in [`docs/DESIGN.md`](docs/DESIGN.md).

---

## Prerequisites

| Need | Notes |
|---|---|
| Databricks workspace on AWS or Azure | Unity Catalog enabled. Serverless SQL and Databricks Apps must be available. |
| [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/) ≥ 0.230 | `databricks auth login --host <your-host> --profile <name>` |
| A serverless **SQL warehouse** | Everything reads through it. |
| A **Unity Catalog catalog** you can `CREATE SCHEMA` in | The schema is created for you. |
| A **Lakebase** (serverless Postgres) instance | Holds the approval state machine. There is a per-workspace quota, so reusing an existing instance is fine — state is isolated by schema. |
| A **chat model serving endpoint** | Any chat model; used by the router and fuser. |
| Python 3.10+ and Node 18+ | `npm` is needed to build the frontend. |
| *Optional:* a **Vector Search endpoint** | For semantic document search. Endpoints are shared, billable, per-workspace resources, so this project does not create one. Leave blank to disable the feature; everything else works. |

Permissions you will need: `CREATE SCHEMA`, `CREATE TABLE`, `CREATE VOLUME`, `CREATE FUNCTION` on the
catalog; `CAN_USE` on the warehouse; and the ability to create a Databricks App and Genie spaces.

---

## Install

### 1. Clone and configure

```bash
git clone https://github.com/Praneeth16/genie-control-tower.git
cd genie-control-tower

cp app/.env.example .env
$EDITOR .env          # fill in catalog, warehouse id, lakebase instance, chat endpoint
```

Every value is workspace-specific and **there are no defaults**. A missing one raises at startup naming
the variable, rather than silently pointing at a catalog you cannot see.

### 2. Check prerequisites — changes nothing

```bash
python3 scripts/install.py --check
```

Verifies auth, and that the warehouse, catalog, Lakebase instance, chat endpoint and (if configured)
Vector Search endpoint all actually resolve. Fix anything it flags before continuing.

### 3. Install

```bash
python3 scripts/install.py
```

Ten idempotent steps (`--list` to see them, `--from <step>` to resume, `--only <step>` for one):

| Step | What it does |
|---|---|
| `volumes` | schema + four volumes |
| `data` | generate 268k rows, upload CSVs, build 18 commented tables |
| `governance` | 12 row filters, 9 column masks, tags, 8 UC control functions |
| `lakebase` | approval state machine, approver roles, policies |
| `genie` | create the three Genie Agents |
| `documents` | generate 713 letters, upload, parse into Delta |
| `vector` | Vector Search index over the corpus *(skipped if `VS_ENDPOINT` is blank)* |
| `dashboard` | build and publish the AI/BI dashboard |
| `app` | build the frontend, deploy the bundle |
| `verify` | goldens, governance assertions, dashboard datasets |

**Two steps print ids you must copy back** — the Genie space ids (`genie`) and the dashboard id
(`dashboard`). Put them in `.env` *and* in your bundle variable overrides, then continue.

> **Order matters, and the installer enforces it.** `data/ddl.sql` builds tables with `read_files()` from
> the seed volume, so the CSVs must be uploaded first. And `CREATE OR REPLACE TABLE` **drops row filters
> and column masks**, so governance must be re-applied after any table rebuild — otherwise the app comes
> up ungoverned while looking perfectly healthy.

### 4. Deploy the app

`bundle deploy` creates and configures the app *resource*. Shipping the code is a second step:

```bash
# app.yaml is GENERATED from app.yaml.template. `apps deploy --source-code-path` reads app.yaml from the
# source path and does NOT apply the bundle's config, so skipping this deploys an app with no
# configuration — it crashes on import naming the first missing variable.
python3 scripts/render_app_yaml.py

databricks bundle deploy -t dev --profile <name>          # resource + grants from databricks.yml

WS=/Workspace/Users/$(databricks current-user me -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')/genie-control-tower
rm -rf /tmp/ct_stage && mkdir -p /tmp/ct_stage/frontend
cp -r app/backend /tmp/ct_stage/backend
cp app/app.yaml app/requirements.txt /tmp/ct_stage/
cp -r app/frontend/dist /tmp/ct_stage/frontend/dist
databricks workspace import-dir /tmp/ct_stage "$WS" --overwrite --profile <name>
databricks apps deploy genie-control-tower --source-code-path "$WS" --profile <name>

# The app's service principal exists only once the app does, and `uc_securable` has no SCHEMA level, so
# the grants its guardrails need are applied afterwards. Without this the app runs and every control
# refuses, because the control identity is row-filtered out of the evidence it checks.
python3 scripts/grant_app_sp.py --app genie-control-tower
```

### 5. Grant the app's OBO scopes

The bundle requests `genie`, `sql:restricted-query` and `files` on the user's behalf. `sql:restricted-query`
is **read-only by construction** — the user token cannot write, so "the agent did it" is never an accepted
answer. Confirm with:

```bash
curl -s -H "Authorization: Bearer $(databricks auth token -p <name> | jq -r .access_token)" \
  https://<app-url>/api/health
```

Expect `"obo_active": true` and `"require_obo": true`. If `obo_active` is false, per-user filtering is
**not** in effect and you are seeing everything — stop and fix it before trusting a demo.

---

## Configuration

Runtime config lives in exactly one place: the `variables:` block of
[`databricks.yml`](databricks.yml). It is generated into the app's environment at deploy time, which
**overrides** `app/app.yaml`. `app.yaml` therefore carries only the start command — a bundle variable
cannot be referenced from `app.yaml`, and for an installable project the bundle has to win.

Locally, the same values come from `.env` (gitignored). Set overrides per target in
`.databricks/bundle/<target>/variable-overrides.json`, or with `--var="warehouse_id=..."`.

---

## Verify

```bash
python3 eval/run_eval.py golden              # benchmark integrity — no Genie quota
python3 eval/governance_tests.py             # 23 governance assertions — no Genie quota
python3 dashboards/build_dashboard.py --validate-sql   # datasets + every widget field reference
python3 eval/run_eval.py router              # 42 routing cases — no Genie quota
python3 eval/run_eval.py genie               # 30 questions, ~11 min, spends real Genie quota
python3 eval/run_eval.py genie --heldout     # 15 unseen questions
python3 eval/governance_tests.py --with-genie # + proves masking reaches Genie's prose
node scripts/visual_qa.mjs                   # drives all 7 tabs in a headless browser
```

### Results as measured

| Measure | Result |
|---|---|
| Genie accuracy, **held out** | **12/15 (80%)** on first run |
| Genie accuracy, tuned suite | 30/30 — **in-sample**, see below |
| Router, single-domain | 33/33 exact |
| Router, cross-domain | 9/9 exact, 0.00 wasted Genie calls per question |
| Governance assertions | 23/23 by default; 26/26 with `--with-genie` |

**Read the held-out number, not the 30/30.** The 30 tuned questions were used to *find and fix*
instruction defects, so their score is in-sample and moved 27 → 28 → 30 as those fixes landed. The 15
held-out questions were written afterwards and never tuned against. 100% in-sample against 80% held-out is
the honest picture, and the gap is the most useful thing the benchmark produced.

Genie is also **non-deterministic**: individual cases flip between identical runs. Quote a number with its
run date, and never treat a one-case difference as an improvement.

### What the benchmark caught

Four wrong answers that would otherwise have been delivered with confidence:

- **A confident zero.** "How many complaints are open past SLA" → **0**; the true answer was 16. The flag
  it used is only set at resolution, and a *trusted SQL example written into the space* taught it that.
- **A silently injected time period**, which flipped "which grade has the highest clawback rate".
- **A silently widened filter** — "Affluent" became Affluent + Private + Mass Affluent, 2,813 vs 966.
- **A fan-out double count** (held out, still open): a one-side measure summed across a many-side join
  inflated a denominator 1.30×, answering 43.4% where the truth is 56.45%. Deliberately unfixed —
  see [`docs/DESIGN.md`](docs/DESIGN.md#open).

---

## Repository layout

```
app/backend/          FastAPI: supervisor, action plane, guardrails, voice, documents, governance
app/frontend/         React + Vite, seven tabs
data/                 synthetic generator, templated DDL with column comments, document generator
genie/                the three Genie Agents as code (instructions, metrics, trusted SQL examples)
governance/           row filters, column masks, tags, and the UC functions the controls call
lakebase/             Postgres migrations: actions, approvals, append-only lineage, approver roles
dashboards/           AI/BI dashboard as code, with widget-field validation
eval/                 benchmarks (tuned + held-out), grader, governance test suite
scripts/              install, SQL runner with templating, vector index, browser QA
docs/                 design rationale, operations runbook
```

---

## Notable design choices

- **Guardrails are Unity Catalog functions**, not prompt instructions. `is_within_rbi_conduct_hours()`,
  `has_open_grievance()`, `agent_conduct_status()` — auditable as catalog objects, and callable by anything.
- **Column masks pseudonymise rather than redact.** A constant mask collapsed 9,660 complaints onto one key
  and turned every join into a cross join. A salted hash keeps the mapping one-to-one so counts and joins
  stay correct while the identifier never leaves the table.
- **A prompt rule is guidance; code is enforcement.** An answer-first instruction was added, passed its
  test, then failed again on a held-out question. `agent.narrative_defect()` now checks in code that a
  leg's prose actually states the figure its own query returned.
- **The guardrail identity is verified unblinded on every evaluation**, against a row-count manifest the
  generator writes. Raise any expectation by one and it raises — a control that only ever returns green
  proves nothing. It refuses the action rather than approving it, because a blinded control does not fail
  loudly: it returns a full set of green ticks.
- **Vector Search indexes are ungoverned copies.** Row filters and column masks do *not* follow data into
  an index, so the index is never granted to end users.

---

## Costs

Genie messages are not separately billed during the current free period. What lands on the bill is the
serverless SQL warehouse running the generated SQL, Model Serving for the router and fuser, the Lakebase
instance, the Databricks App compute, and — if enabled — the Vector Search endpoint. The Governance tab
attributes warehouse and model cost per question, which is the number a budget owner needs; billing
aggregates by warehouse, which is not.

A full `eval/run_eval.py genie` run costs 30 Genie messages and about 11 minutes, and will starve
everything else in the workspace while it runs. Do not run it during a demo.

---

## Known issues

An independent audit of this repository found real defects, including two in claims the project makes about
itself. They are recorded in [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) — what was fixed, what is still
open, and corrections to anything previously overstated. Read it before relying on this in anger.

---

## Licence and provenance

Apache 2.0 — see [LICENSE](LICENSE).

Not an official Databricks product. Built as a field reference. All data is synthetic; any resemblance to
a real institution's figures is coincidental. Regulatory rules referenced in the controls (RBI recovery
conduct hours, the Integrated Ombudsman Scheme, NPCI reversal timings) are **paraphrased for
demonstration** and are not legal advice — a bank's own compliance function owns the citations.
