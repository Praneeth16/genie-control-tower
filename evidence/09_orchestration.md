<!-- Generated 2026-10-29 12:47 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 09 — One job runs every stage

_Generated 2026-10-29 12:47 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** One Lakeflow job runs the whole cycle in dependency order (pipeline, governance, AI briefs, AI evaluation, Lakebase sync), started by FILE ARRIVAL when a source drop's manifest lands; and after the run the worklist count agrees across gold, Lakebase and the app.

Job `112274750105468`, trigger: file arrival on `/Volumes/serverless_lakebase_praneeth_catalog/control_tower_banking/landing/_manifests/`.

| run_id | trigger | result | started (UTC) | duration | tasks (first attempt) |
|---|---|---|---|---|---|
| 199261380563882 | ONE_TIME | SUCCESS | 2026-10-29 12:36 | 35s | govern:DISABLED(0s), case_briefs:DISABLED(0s), evaluate_ai:DISABLED(0s), refresh_pipeline:DISABLED(0s), sync_cases:SUCCESS(29s) |
| 77252095941105 | ONE_TIME | SUCCESS | 2026-10-29 12:20 | 826s | govern:DISABLED(0s), case_briefs:SUCCESS(158s), evaluate_ai:SUCCESS(660s), refresh_pipeline:DISABLED(0s), sync_cases:SUCCESS(24s) |
| 366295467750773 | FILE_ARRIVAL | SUCCESS | 2026-10-29 10:28 | 1134s | govern:SUCCESS(64s), case_briefs:SUCCESS(146s), evaluate_ai:SUCCESS(636s), refresh_pipeline:SUCCESS(274s), sync_cases:SUCCESS(44s) |
| 593073173997565 | ONE_TIME | SUCCESS | 2026-10-29 10:15 | 759s | govern:DISABLED(0s), case_briefs:SUCCESS(171s), evaluate_ai:SUCCESS(581s), refresh_pipeline:DISABLED(0s), sync_cases:SUCCESS(25s) |
| 476287392178085 | ONE_TIME | SUCCESS | 2026-10-29 09:54 | 1072s | govern:SUCCESS(55s), case_briefs:SUCCESS(145s), evaluate_ai:SUCCESS(655s), refresh_pipeline:SUCCESS(203s), sync_cases:FAILED(19s) |
| 224454188013264 | ONE_TIME | SUCCESS | 2026-10-29 09:34 | 694s | govern:DISABLED(0s), case_briefs:DISABLED(0s), evaluate_ai:SUCCESS(690s), refresh_pipeline:DISABLED(0s), sync_cases:DISABLED(0s) |
| 1067591713200279 | ONE_TIME | SUCCESS | 2026-10-29 09:17 | 850s | govern:SUCCESS(54s), case_briefs:SUCCESS(146s), evaluate_ai:SUCCESS(641s), refresh_pipeline:DISABLED(0s) |
| 770130929147238 | FILE_ARRIVAL | FAILED | 2026-10-29 09:06 | 1s | govern:UPSTREAM_FAILED(0s), refresh_pipeline:FAILED(0s) |

## Cross-check after the run

| where | accounts on the worklist |
|---|---|
| gold.collections_priority | 589 |
| Lakebase collections_cases (on_worklist) | 589 |
| app GET /api/cases (sum by status) | 589 |
