# Evidence

Each file below was generated from the live workspace by `tools/generate_evidence.py` after the final run, except the answer key, which the data generator writes. Each generated file starts with the time it was generated. No result in these files was typed by hand.

| File | What it shows |
|---|---|
| [00_answer_key.md](00_answer_key.md) | Every planted defect, with its count, and the rows the gold tables should end up with. |
| [01_pipeline_run.md](01_pipeline_run.md) | The pipeline updates, the rows in every layer, and each expectation's pass and fail counts from the event log. |
| [02_data_quality.md](02_data_quality.md) | The answer key against what the pipeline caught, the gold row counts against the answer key, and the reconciliation of every file against its sender's manifest. |
| [03_business_results.md](03_business_results.md) | The numbers the CRO and the Head of Collections act on. |
| [04_ai_output.md](04_ai_output.md) | Verbatim AI output for the letter triage and the case briefs, with the facts the model was given. |
| [05_ai_evaluation.md](05_ai_evaluation.md) | Every evaluation run, by prompt and judge version, the remaining disagreements, and the judge rationales. |
| [06_governance.md](06_governance.md) | The same queries run as four persona service principals, the entitlements, and the policies attached in Unity Catalog. |
| [07_lakebase.md](07_lakebase.md) | An edit made in the app that survived the next sync, the case history, and the refused attempt to rewrite it. |
| [08_genie.md](08_genie.md) | Every benchmark and held-out question asked through the Genie Conversation API and graded against ground-truth SQL. |
| [09_orchestration.md](09_orchestration.md) | The cycle job's runs, including the one started by file arrival, and the worklist count in gold, Lakebase and the app. |
| [10_app.md](10_app.md) | The deployed app's routes called as the signed-in user, including a refused self-approval. |
| [HEADLINES.md](HEADLINES.md) | The figures the README and the deck quote. |
