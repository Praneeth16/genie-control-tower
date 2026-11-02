# FE Bar context

Read this file before every task in this repo, and follow it.

## Purpose

This is my FE Bar submission. It is a working prototype for an Indian private-sector retail bank (fictional, all data synthetic). It helps the bank work its delinquent loans in the right order without breaking the RBI rules on recovery-agent conduct.

- Executive sponsor. The Chief Risk Officer, who is measured on gross NPA, credit cost, and conduct breaches and the penalties that follow them.
- Domain owner. The Head of Collections and Recovery, who is measured on roll-forward rate, cure rate, cost to collect, and contacts outside the permitted hours.

## Rules

- One connected journey from raw synthetic data. The stages are Lakeflow ingest, Unity Catalog governance, Lakebase serving, AI inside the flow, Genie agents, and a Databricks App. Each stage uses the output of the one before it.
- The evaluator reads text only. Every stage needs committed text evidence from a real run, written by `tools/generate_evidence.py` into `evidence/` and by `tools/verify_run.py` into `run_output/`. The first scoring did not see `evidence/` or `data/`, and the second did not see `run_output/` either, so proof of execution lives in root markdown files (`README.md`, `RUN_EVIDENCE.md`) as pasted output, and the Genie specification in `GENIE_SPACES.md` and `GENIE_BENCHMARKS.md`. Re-run `tools/verify_run.py` and `tools/render_genie_spec.py` after any change.
- The repo is public.
- Synthetic data only. No customer names, real institutions, people's names, or internal system names, in code, data, docs, commit messages or the deck.
- My own work. No Solution Builder output and no one else's build.
- The narrative, opinions and decisions were drafted with the AI and then rewritten in plain style on 2026-11-02. I review them before I submit. Do not add new narrative without marking it for my review.

## Workspace

- CLI profile `fe-vm-lakebase-praneeth`. Pass `--profile` on every command.
- Catalog `serverless_lakebase_praneeth_catalog`, schema `control_tower_banking`.
- Lakebase project `genie-control-tower`.
- Everything deploys with the bundle (`databricks.yml`, `resources/*.yml`).

## How to work

- Small steps. After each step, say what changed, how it was verified, and what is next.
- Record each decision in `DECISIONS.md`, and each attempt, failure and fix in `BUILD_LOG.md`.
- A task is done when it is deployed, it ran, a query or API call shows the result, and the build log has a line for it.
