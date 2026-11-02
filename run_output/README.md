# Run output

This folder holds readable proof that the build executed on a live workspace. Nothing here was typed by hand. The builder's email and the workspace hostname are replaced with placeholders. The `evidence/` folder holds the fuller, section-by-section evidence pack, also generated from the workspace.

| File | What it is | How it was produced |
|---|---|---|
| [verify_run.ipynb](verify_run.ipynb) | A notebook with saved outputs. Eleven cells: pipeline updates, expectation counts from the event log, file reconciliation, quarantine counts, the worklist, the evaluation history, the job runs, one Genie question against ground truth, the Lakebase queue and a refused rewrite of its history, the approver-role check, and the app's health route. | `tools/verify_run.py --profile <profile>` executes each cell against the deployed bundle and saves what it printed. |
| [verify_run.txt](verify_run.txt) | The same cells and outputs as plain text. | Written by the same script. |
| [01_cycle_job_runs.txt](01_cycle_job_runs.txt) | Two runs of the cycle job with every task's result and duration. One run was started by the file-arrival trigger. | `databricks jobs get-run`. |
| [02_pipeline_updates.txt](02_pipeline_updates.txt) | The pipeline's recent updates and the progress events of the update the file-arrival run started. | `databricks pipelines list-updates` and `list-pipeline-events`. |
| [task_logs/evaluate_ai.txt](task_logs/evaluate_ai.txt) | Standard output of the evaluation task: the MLflow run link and every metric it computed, as JSON. | `databricks jobs get-run-output`. |
| [task_logs/evaluate_ai_filearrival.txt](task_logs/evaluate_ai_filearrival.txt) | The same task from the file-arrival run, so two cycles can be compared. | Same. |
| [task_logs/sync_cases.txt](task_logs/sync_cases.txt) | The Lakebase sync: rows published, cases before and after, cases a person had edited. | Same. |
| [task_logs/case_briefs.txt](task_logs/case_briefs.txt) | The brief task's SQL statements as they ran. | Same. |
| [task_logs/govern.txt](task_logs/govern.txt) | The governance task: functions, tags, policies and grants as they ran. | Same. |
| [task_logs/grant_personas.txt](task_logs/grant_personas.txt) | The persona grants as they ran. | Same. |

Quick checks a reader can make from these files alone:

- The cycle job run with trigger `FILE_ARRIVAL` finished `SUCCESS` with every task green, and the pipeline update it started went from `WAITING_FOR_RESOURCES` to `COMPLETED` in about four minutes.
- The evaluation task computed `ground_accuracy` 0.9705 on 713 letters and `rule_agreement_pass_rate` 1.0 on 200 briefs, and logged them to MLflow. The notebook shows the same metrics as rows in `ai_eval_summary` for each cycle.
- Genie answered "What was the microfinance delinquency percentage in Solapur in May 2026?" with 43.6%, and the ground-truth SQL run in the same minute returned 43.6.
- An `UPDATE` on `case_history` was refused by the trigger.
- The Head of Collections persona holds no approval role, so `holds_required_role` refuses it, and the person who raised an action cannot approve it.
