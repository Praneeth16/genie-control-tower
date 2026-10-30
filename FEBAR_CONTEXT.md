# FE Bar context

Read this file before every task in this repo, and follow it.

## Purpose

This is my FE Bar submission. It is a working prototype for an Indian private-sector retail bank (fictional, all data synthetic). It helps the bank work its delinquent loans in the right order without breaking the RBI rules on recovery-agent conduct.

- Executive sponsor. The Chief Risk Officer, who is measured on gross NPA, credit cost, and conduct breaches and the penalties that follow them.
- Domain owner. The Head of Collections and Recovery, who is measured on roll-forward rate, cure rate, cost to collect, and contacts outside the permitted hours.

## Rules

- One connected journey from raw synthetic data. The stages are Lakeflow ingest, Unity Catalog governance, Lakebase serving, AI inside the flow, Genie agents, and a Databricks App. Each stage uses the output of the one before it.
- The evaluator reads text only. Every stage needs committed text evidence from a real run, written by `tools/generate_evidence.py`.
- The repo is public.
- Synthetic data only. No customer names, real institutions, people's names, or internal system names, in code, data, docs, commit messages or the deck.
- My own work. No Solution Builder output and no one else's build.
- Mark every drafted narrative, opinion or decision with [YOUR WORDS]. I rewrite those parts myself.

## Workspace

- CLI profile `fe-vm-lakebase-praneeth`. Pass `--profile` on every command.
- Catalog `serverless_lakebase_praneeth_catalog`, schema `control_tower_banking`.
- Lakebase project `genie-control-tower`.
- Everything deploys with the bundle (`databricks.yml`, `resources/*.yml`).

## How to work

- Small steps. After each step, say what changed, how it was verified, and what is next.
- Record each decision in `DECISIONS.md`, and each attempt, failure and fix in `BUILD_LOG.md`.
- A task is done when it is deployed, it ran, a query or API call shows the result, and the build log has a line for it.
