<!-- Generated 2026-10-29 12:37 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 07 — Lakebase: the case queue people work

_Generated 2026-10-29 12:37 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** Lakebase holds the operational record. A person's edit, made through the app, survives the pipeline's next refresh because the sync only writes machine-owned columns; every change is in the history with who made it and whether a person or the sync did; and the history refuses to be rewritten.

## The edit-survives-refresh test, on case 1312 (LN000666)

| step | result |
|---|---|
| 1. edit through the app (PATCH /api/cases) | HTTP 200 |
|    status / owner / notes after the edit | promise_to_pay / Collections officer (West) / Evidence test 2026-10-29 12:36: borrower asked for calls after 18:00 only |
|    refreshed_at before the sync | 2026-10-29T12:23:39.307312+00:00 |
| 2. run the Lakebase sync (ct_cycle, task sync_cases) | run 199261380563882: SUCCESS |
|    refreshed_at after the sync | 2026-10-29T12:37:04.239875+00:00 |
|    status / owner / notes after the sync | promise_to_pay / Collections officer (West) / Evidence test 2026-10-29 12:36: borrower asked for calls after 18:00 only |
| 3. human edit survived the refresh | YES |
| 4. attempt to rewrite the history (UPDATE case_history) | case_history is append-only: UPDATE refused |

## History of that case (newest first)

| changed_at | changed_by | source | field | old | new |
|---|---|---|---|---|---|
| 2026-10-29T12:36:32 | builder@example.com | app | next_action_date |  | 2026-09-05 |
| 2026-10-29T12:36:32 | builder@example.com | app | notes |  | Evidence test 2026-10-29 12:36: borrower asked for calls after 18:00 only |
| 2026-10-29T12:36:32 | builder@example.com | app | owner |  | Collections officer (West) |
| 2026-10-29T12:36:32 | builder@example.com | app | status | new | promise_to_pay |
| 2026-10-29T10:37:03 | sync_cases (builder@example.com) | pipeline_sync | case_opened |  | rank 2, Settlement or legal review |

## Cases on the worklist, by status

| status | cases |
|---|---|
| new | 588 |
| promise_to_pay | 1 |

## Every history row, by who changed what

| source | field | rows |
|---|---|---|
| app | next_action_date | 1 |
| app | owner | 1 |
| app | status | 1 |
| app | notes | 1 |
| pipeline_sync | case_opened | 1178 |
| pipeline_sync | on_worklist | 589 |
| pipeline_sync | priority_rank | 66 |
| pipeline_sync | dpd_bucket | 47 |
| pipeline_sync | recommended_treatment | 35 |
| pipeline_sync | ai_recommended_action | 16 |
