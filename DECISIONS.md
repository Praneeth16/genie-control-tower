# Decisions and trade-offs

[YOUR WORDS] Each entry below was drafted with an AI pair engineer from decisions I made during the build. Rewrite each one in your own words before you submit.

Each entry has the same shape. It says what we chose, what the other options were, and why.

## 1. Start from the files each source system sends, not from clean tables

- Options. Load clean CSV files into tables, or write the raw exports each system would send.
- Choice. Raw exports, split by month, in each system's own field names, with the derived fields removed and defects planted.
- Why. A bank's data team receives files like these. The pipeline has to conform two contact sources into one table. It has to compute the business rules and catch the bad rows. The answer key gives exact counts, so we can check that it did.

## 2. Keep the 18 published table names

- Options. Rename the tables to follow a medallion naming scheme, or keep the names the Genie agents, the app and the UC functions already use.
- Choice. Keep the names for the governed gold tables. Bronze, silver, core and quarantine tables get layer prefixes.
- Why. Nothing downstream had to change its SQL when the data stopped being loaded by hand.

## 3. Declare row filters and masks in the gold table definitions

- Options. Attach the policies with `ALTER TABLE` after each run, or declare them in each materialized view.
- Choice. Declare them in the definition.
- Why. An `ALTER` on a table the pipeline owns is lost on a full refresh. The table then comes back ungoverned and looks healthy.

## 4. Compute from private core tables, publish governed gold tables

- Options. Derive the score, the SLA rollup and the row counts from the governed tables, or from private tables that no policy touches.
- Choice. Private core tables. Policies apply only to the gold tables people query.
- Why. Nothing the pipeline computes can depend on whose row filter it ran through. A policy changes who sees an answer. It never changes the answer.

## 5. Store entitlements as data

- Options. Write each persona's access into the policy functions, or keep it in a table that the functions read.
- Choice. An `entitlements` table, one row per principal and region, with flags for identifiers and free text.
- Why. A data steward can change access by changing a row. "Who can see the West region" is a query, not a code review.

## 6. Prove governance with real identities

- Options. Simulate personas by swapping my own entitlement row, or run the same queries as four real service principals.
- Choice. Four persona service principals. Each runs a probe job with `run_as` set to itself.
- Why. The evidence shows what Unity Catalog returned to each identity. No credential leaves the workspace.

## 7. Rank with an explainable score, and let the AI explain it

- Options. Train a model to rank accounts, use an LLM to rank them, or use a points score with named components.
- Choice. A points score with the components and the reasons stored on every row. The conduct rules decide how an account may be worked. The LLM explains the result in plain words.
- Why. A Head of Collections can argue with "+35 because SMA-2". Nobody can argue with an opaque probability. The AI explains the decision and does not make it.

## 8. Put the letter triage inside the pipeline

- Options. Run the LLM when a user clicks a button in the app, or run it as a streaming table in the pipeline.
- Choice. A streaming table with `ai_query` and a fixed JSON schema.
- Why. Each letter is read once, when it lands. The output feeds the worklist's conduct flags and the grievance agent. It is measured against the ground the grievance desk recorded.

## 9. Judge the AI with a different model family

- Options. Use the same model family as the generator to judge, or a different one.
- Choice. The generator is Claude Sonnet. The judge is GPT-5.5.
- Why. A judge from the same family tends to share the generator's blind spots. When the first judge was wrong, I rewrote the judge's definition and kept both versions in the results. I did not soften it to raise the pass rate.

## 10. Split Lakebase columns into machine-owned and human-owned

- Options. Overwrite each case on every refresh, or let people edit the cases while the pipeline refreshes them.
- Choice. The sync's upsert names only the machine-owned columns. Status, owner, notes and next action date belong to people. A trigger writes every change to the history, and the history refuses UPDATE and DELETE.
- Why. A refresh can never undo a decision somebody made. No code path can change a case without leaving a record.

## 11. Apply the UC region rule to Lakebase rows in the app

- Options. Show every case to every user, or filter the cases by the regions Unity Catalog grants the user.
- Choice. The app asks Unity Catalog, as the signed-in user, which regions that user can see. It shows only the cases in those regions.
- Why. Lakebase has no Unity Catalog row filters. One policy has two enforcement points, and the Unity Catalog one is the source of truth.

## 12. Trigger the cycle on file arrival

- Options. A schedule, a manual run, or a file-arrival trigger.
- Choice. File arrival on the manifests folder. Every sender writes its manifest last.
- Why. A run starts only when a drop is complete. In the demo, landing the held-back month starts the whole cycle with no manual step.

## 13. Keep the planted truncated transfer as a visible break

- Options. Fix every planted defect so the evidence shows a clean reconciliation, or leave the one truncated file as a break.
- Choice. Leave it. The dialer's June file arrived 37 rows short and the reconciliation shows it.
- Why. It shows the answer to "what happens with a late or corrupted file?" The break names the file and the missing rows.
