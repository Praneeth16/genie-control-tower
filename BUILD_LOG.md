# Build log

This is the working record of the FE Bar build. Each entry says what was tried, what failed, and what changed. I built it with Claude Code as a pair engineer. The numbers come from the evaluation tables and the evidence files.

## 2026-10-29

### Starting point

The repo already had the governed Genie agents, the app and the action plane. It did not have the data journey that FE Bar asks for.

The gaps were these:

- The data was loaded by hand with `CREATE OR REPLACE TABLE` over clean CSV files. Every business rule was computed in Python before the data was written.
- There was no AI step inside the data flow.
- Lakebase held only state that the app wrote. Nothing flowed from the gold tables into it.
- There was no job that ran every stage.
- No evidence of a run was committed.

### Spikes before building

I tested four things before writing the pipeline.

- A serverless pipeline can create a materialized view with a row filter and a column mask declared in its definition, even when the filter function reads another table. It worked.
- `ai_query` with a JSON schema runs inside a streaming table and returns parsed output. It worked on three test letters.
- A Lakebase autoscaling project accepts an OAuth credential from the SDK as the Postgres password. It worked.
- I tried to create OAuth secrets for the persona service principals so the evidence could query as each of them. My coding tool refused to handle the secret locally. I changed the design. Each persona now runs a small job with `run_as` set to its service principal, so no secret leaves the workspace.

### Raw data and the pipeline

- The generator now writes the files each source system would send, split by month, in each system's own field names, with the derived fields removed.
- I planted twelve kinds of defect with fixed counts and wrote an answer key for them.
- The first pipeline run failed twice on schema mismatches between the declared columns and the query. Declared columns bind by name, so I aliased the columns.
- I then found that every apostrophe in a table comment had disappeared. Spark joins two adjacent string literals, so `''` inside a comment becomes nothing. I changed every `''` to `\'`.
- The `roll_direction` column used to disagree with the account's own history, because the generator drew a fresh random "previous month". The pipeline now derives it with `lag()` over the real snapshots.

### Governance

- Policies moved into the gold table definitions. An `ALTER TABLE` on a table that the pipeline owns is lost on a full refresh.
- Entitlements are now rows in a table, so an access change is a row change.
- The persona jobs failed three times before they ran.
  - I did not have the `servicePrincipal.user` role on the service principals.
  - The service principals could not read the bundle files.
  - The service principals did not have workspace access.
- The same queries now return different rows and values for each persona.

### AI: letter triage

- The model reads only the body of each letter. The old letters carried the grievance desk's labels, so I removed those lines. Otherwise the model could copy the answer.
- Prompt v1 matched the recorded ground on 87.1% of 690 letters. It found every recovery-agent conduct letter and flagged no other letter.
- Most misses fell into three groups.
  - A deposit account complaint was read as a charges complaint (40 letters).
  - A KYC complaint was read as a deposit complaint (34 letters).
  - An ATM complaint was read as a cards complaint (15 letters).
- Prompt v2 defined each ground in the bank's terms. Accuracy rose to 97.0% on the same 690 letters.
- The 21 misses that remain are deposit account complaints about charges. The recorded label is defensible either way, so I left them and report them.

### AI: worklist briefs

- Prompt v1 agreed with the bank's conduct rules on only 14% of the 200 briefs. It did not know the order in which the rules apply.
- The first grounded judge (j1) failed every brief. Its own rationales listed every stated fact as present. It was failing the model's reasoning, e.g., "this makes it a high-priority case", as if that were an invented fact. I rewrote the judge (j2) to separate an invented fact from a judgement drawn from the facts. Both judge versions stay in the results.
- Under j2, the judge still failed briefs that called product code "PV" a "personal vehicle loan". The bank means passenger vehicle. The model had expanded the code from its own knowledge. I added the product name to the facts the model receives.
- My own number check also had a bug. It failed "INR 33.39 L", which is a correct rounding of the outstanding amount. I fixed the check to allow rounding, and to allow amounts written in lakh or crore.
- Prompt v2 listed the conduct rules in the prompt. Rule agreement rose to 100%. The grounded pass rate fell from 38% to 21%, and the plain language pass rate fell from 88% to 51%. The briefs now said "Per Rule 3". That rule is not in the facts, and an officer cannot read it. The judges were right.
- Prompt v3 gives the model the bank's decision as a fact (`bank_rule`). The model explains the decision and does not decide it. On the July accounts, grounded rose to 64.5% and rule agreement stayed at 100%.
- v3 had two new problems. Only 23.5% of the July briefs stayed within 60 words, because the model now listed every fact. The grounded judge also failed briefs that added a step the rule does not state, e.g., "before further collection activity".
- Prompt v4 asks for exactly two sentences. The first says why the account is ranked, in at most 30 words. The second says what to do, in the rule's own words, in at most 20 words. v4 scored 90% grounded, 100% rule agreement, 86% plain language and 86% within 60 words, on the 200 August briefs.
- The evaluation had judged every brief for an account still on the list, including briefs written from an earlier month's facts. It now judges only briefs written from the current month end.

### Lakebase and the app

- The case queue splits machine-owned columns from human-owned columns. A trigger writes the history, and a second trigger refuses any UPDATE or DELETE on the history.
- The first full cycle hit a SIGABRT in the Lakebase sync task. It succeeded on retry. I have not found the cause. The task now retries twice, which is safe because the upsert is idempotent.
- In the deployed app, calling the `region_visible()` function with the user's token was refused. A read through a table with the row filter works. The app now asks for the user's regions through `loan_accounts`.
- The app rejected environment variables with empty values. I removed the optional settings that are off in this build.
- I fixed these action plane defects:
  - The proposer is now the signed-in person, so separation of duties applies to people.
  - The region comes from the record, not the request body.
  - Running an action needs the approver role.
  - A rejection is recorded as a rejection.

### The final month and the trigger

- The first file-arrival run failed after one second. It fired while I was running a pipeline update by hand, and the job reported "Pipeline update already in progress". The job queues its own runs, but it cannot queue behind an update started outside it.
- Landing the held-back August drop started the cycle on its own. That run succeeded on every task.
- Every planted finding matched the answer key except late uploads, which showed 238 against 236. A late call that the vendor also re-sent was counted twice. The quality summary now counts distinct contacts, and it matches.
- After the final run, gold, Lakebase and the app all show 589 accounts on the worklist.

### Bundle

- Development mode pauses every trigger and refuses to unpause them. The file-arrival trigger is part of the demo, so the target does not use development mode.
- The Genie spaces, the dashboard and the Lakebase app resource are bundle resources. The app gets the space ids from the bundle.

## 2026-10-30

### Independent review

I asked a second model (Codex) to review the build and the claims, read-only. It found real defects. I checked each one before fixing it.

- The personas had SELECT on the whole schema, so they could read the bronze and quarantine tables, which hold raw identifiers and letter text with no filter or mask. Personas now get SELECT on the governed tables only. The persona probes now show all four personas refused on bronze and quarantine.
- A proposer could execute or reject an action without the approver role. The role check sat after the separation-of-duties check, and execute and reject skipped that check's refusal. The role check now stands on its own.
- The action routes did not check the caller's region, and the region was resolved from the subject while the conduct checks read a separate payload field. Every action route now checks the caller's Unity Catalog regions, and the payload must name the same record as the subject.
- Switching cases in the worklist kept the previous case's form while the save target changed. The case panel is now keyed by case.
- The Governance screen still read a field I had removed, so it would fail to render. It now shows the personas and the two clearance flags.
- The sync could attach an earlier month's brief to a case. It now takes only a brief written from the current month end.
- The history trigger recorded nine columns, not every business column, which did not match the decision I had written. It now records every business column.
- Reconciliation assumed a file was loaded when it had no rows in silver or quarantine. For feeds with a silver layer, that would hide a total loss. It now counts zero loaded rows in that case.
- A customer letter with no matching complaint had a NULL region, which the document filter treats as a public reference document. It now gets the region UNASSIGNED.
- The overview's "last two months" window covered almost three months. It now covers the latest month and the one before it.
- The number check in the evaluation took digits from JSON keys, so a key such as `contacts_90d` could vouch for an invented 90. It now reads only the values.
- Lakebase output did not flow back to Unity Catalog. The sync now publishes each case's status to a governed table, `collections_case_status`, and the Collections agent can answer from it.
- Several claims in the docs went further than the evidence. "Moved to a certified agency" became "recommended for reassignment". "Getting worse" became the measured spike and its later easing. The v3 numbers now name the July accounts they were measured on.

### Network outage

- A local network outage cut off the first Genie re-run and an app deploy. The evidence generator refused to reuse the old held-out results, which is what its new check is for. I re-ran Genie after the network came back.
- An interrupted clone of the genie-design repository had landed inside this repository, and a deploy was uploading it. I removed it from the commit, the disk and the workspace.

### Second review

I asked Codex to check the fixes. It confirmed nine of the twelve and found new gaps, which I fixed.

- On a fresh install, the grant task could run before the evaluation had created `ai_eval_summary`. The grant task now waits for the evaluation as well as the sync.
- With table-level grants, a persona could no longer read the entitlements table, so the Governance screen would fail for anyone but the administrator. Granting the table would show everyone's access rows. Personas now read a view, `my_entitlements`, that returns only the caller's own rows. The probes show each persona reading only its own rows.
- A request without a user token returned HTTP 500. It now returns 403.
- An action whose subject did not resolve to a region skipped the region check. It is now refused.

