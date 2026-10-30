<!-- Generated 2026-10-30 10:30 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 08 — Genie agents against ground truth

_Generated 2026-10-30 10:30 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** Every benchmark question was asked through the Genie Conversation API and graded against ground-truth SQL executed in the same minute. Every answer's result grid is checked; for a single-number answer the prose Genie wrote must also state the number, while list and ranking answers pass on the grid alone. The held-out set was never used to tune the spaces, so it is the honest number. Genie is not deterministic, so these are the results of one run at the time shown.

Spaces: collections `01f1d381797215d29c768c621cd5dd7a`, grievance `01f1d381796f188d89c4ca7e49e0a2b3`, rm `01f1d38179711c44b7b1dc4806cde566`.

## Benchmark questions: 35 of 35 graded passed (100.0%), 35 attempted

Questions asked at 2026-10-30 10:25 UTC (`eval/results/genie-latest.json`).

| id | agent | question | outcome | matched in | detail |
|---|---|---|---|---|---|
| COL-01 | COLLECTIONS | What is the delinquency rate by product as of 1 August 2026? | pass | rows | 8/8 key-value pairs matched in rows, 6/8 in narrative |
| COL-02 | COLLECTIONS | What was the microfinance delinquency percentage in Solapur in May 2026? | pass | rows+narrative | expected 43.6; found in rows=True, in narrative=True |
| COL-03 | COLLECTIONS | What is the GNPA percentage by region as of 1 August 2026? | pass | rows | 5/5 key-value pairs matched in rows, 5/5 in narrative |
| COL-04 | COLLECTIONS | Which city had the highest commercial vehicle delinquency in May 2026? | pass | rows | expected top city='Indore'; first row match=True, named in narrative=False |
| COL-05 | COLLECTIONS | How many contact attempts were made outside RBI permitted hours across the whole data window? | pass | rows+narrative | expected 2499.0; found in rows=True, in narrative=True |
| COL-06 | COLLECTIONS | How many recovery agents who are not RBI conduct certified made contact during 2026? | pass | rows+narrative | expected 10.0; found in rows=True, in narrative=True |
| COL-07 | COLLECTIONS | What was the bucket 2 roll-forward percentage for microfinance in May 2026? | pass | rows+narrative | expected 92.6; found in rows=True, in narrative=True |
| COL-08 | COLLECTIONS | What was the total amount collected from Solapur microfinance accounts in June 2026? | pass | rows+narrative | expected 591727.0; found in rows=True, in narrative=True |
| COL-09 | COLLECTIONS | How many contact attempts per account touched were made on Solapur microfinance in May 2026 compared with January 2026? | pass | rows | 2/2 key-value pairs matched in rows, 2/2 in narrative |
| COL-10 | COLLECTIONS | Which are the top 3 agencies by number of out-of-hours contact attempts? | pass | rows | expected top agency_name='Sunrise Recovery Services'; first row match=True, named in narrative=True |
| COL-11 | COLLECTIONS | How many accounts are on the collections worklist in each region, and how much do they owe? | pass | rows | 5/5 key-value pairs matched in rows, 5/5 in narrative |
| COL-12 | COLLECTIONS | How many worklist accounts are on hold because of an open grievance? | pass | rows+narrative | expected 40.0; found in rows=True, in narrative=True |
| COL-13 | COLLECTIONS | What share of the collections worklist carries a conduct flag? | pass | rows+narrative | expected 26.0; found in rows=True, in narrative=True |
| COL-14 | COLLECTIONS | How many accounts on the current worklist has no officer touched yet? | pass | rows+narrative | expected 588.0; found in rows=True, in narrative=True |
| GRV-01 | GRIEVANCE | What is the SLA breach rate by RBI category for August 2026? | pass | rows | 8/8 key-value pairs matched in rows, 7/8 in narrative |
| GRV-02 | GRIEVANCE | What was the payment systems SLA breach percentage in June 2026? | pass | rows+narrative | expected 35.8; found in rows=True, in narrative=True |
| GRV-03 | GRIEVANCE | How many UPI disputes were raised for transactions on 14 June 2026? | pass | rows+narrative | expected 532.0; found in rows=True, in narrative=True |
| GRV-04 | GRIEVANCE | What was the UPI auto-refund percentage on 15 June 2026 compared with 10 June 2026? | pass | rows | 2/2 key-value pairs matched in rows, 2/2 in narrative |
| GRV-05 | GRIEVANCE | How many UPI transaction dispute complaints were received on 17 June 2026? | pass | rows+narrative | expected 82.0; found in rows=True, in narrative=True |
| GRV-06 | GRIEVANCE | How many complaints were escalated to the RBI ombudsman across the whole data window? | pass | rows+narrative | expected 239.0; found in rows=True, in narrative=True |
| GRV-07 | GRIEVANCE | What is the overall chargeback win rate? | pass | rows+narrative | expected 52.4; found in rows=True, in narrative=True |
| GRV-08 | GRIEVANCE | How many complaints were still open and past their SLA as of 31 August 2026? | pass | rows+narrative | expected 7.0; found in rows=True, in narrative=True |
| GRV-09 | GRIEVANCE | Which RBI category has the highest ombudsman escalation percentage? | pass | rows | expected top rbi_category='Recovery agents'; first row match=True, named in narrative=True |
| GRV-10 | GRIEVANCE | How many complaints arrived through the RBI CMS channel? | pass | rows+narrative | expected 1366.0; found in rows=True, in narrative=True |
| GRV-11 | GRIEVANCE | How many complaint letters allege recovery-agent misconduct, according to the AI triage? | pass | rows+narrative | expected 248.0; found in rows=True, in narrative=True |
| RM-01 | RM | How many RM-months have the clawback flag set across the whole data window? | pass | rows+narrative | expected 465.0; found in rows=True, in narrative=True |
| RM-02 | RM | How many distinct relationship managers have attainment of 120 percent or more together with a product mix score below 0.50? | pass | rows+narrative | expected 21.0; found in rows=True, in narrative=True |
| RM-03 | RM | For RM-months with attainment of 120 percent or more, what is the average incentive earned split by whether the product mix score is below 0.50? | pass | rows | 2/2 key-value pairs matched in rows, 2/2 in narrative |
| RM-04 | RM | What is the CASA attainment percentage by region for August 2026? | pass | rows | 5/5 key-value pairs matched in rows, 5/5 in narrative |
| RM-05 | RM | Which relationship manager had the highest attainment in August 2026? | pass | rows | expected top rm_name='Amit Reddy'; first row match=True, named in narrative=True |
| RM-06 | RM | How many customers hold two or fewer products? | pass | rows+narrative | expected 2532.0; found in rows=True, in narrative=True |
| RM-07 | RM | What is the incentive earned per million rupees of business by RM grade from March 2026 onward? | pass | rows | 4/4 key-value pairs matched in rows, 4/4 in narrative |
| RM-08 | RM | How many affluent segment customers do not hold an active credit card? | pass | rows+narrative | expected 966.0; found in rows=True, in narrative=True |
| RM-09 | RM | Which RM grade has the highest clawback rate? | pass | rows | expected top rm_grade='Lead'; first row match=True, named in narrative=True |
| RM-10 | RM | What was the total incentive paid in August 2026? | pass | rows+narrative | expected 1473421.0; found in rows=True, in narrative=True |

## Held-out questions (not used to tune the spaces): 15 of 15 graded passed (100.0%), 15 attempted

Questions asked at 2026-10-30 10:30 UTC (`eval/results/heldout-genie-latest.json`).

| id | agent | question | outcome | matched in | detail |
|---|---|---|---|---|---|
| HO-01 | COLLECTIONS | What was the recovery rate on microfinance in June 2026, as collections against overdue? | pass | rows+narrative | expected 56.29; found in rows=True, in narrative=True |
| HO-02 | COLLECTIONS | What is our overall contactability on collections attempts? | pass | rows+narrative | expected 71.5; found in rows=True, in narrative=True |
| HO-03 | COLLECTIONS | Which collections channel has the highest promise-to-pay rate? | pass | rows | expected top channel='Email'; first row match=True, named in narrative=False |
| HO-04 | COLLECTIONS | How much exposure sits in the NPA bucket by product as of 1 August 2026? | pass | rows | 8/8 key-value pairs matched in rows, 5/8 in narrative |
| HO-05 | COLLECTIONS | What share of accounts improved their delinquency bucket in July 2026? | pass | rows+narrative | expected 11.3; found in rows=True, in narrative=True |
| HO-06 | GRIEVANCE | What is the average number of days to resolve a complaint, by RBI ground? | pass | rows | 8/8 key-value pairs matched in rows, 7/8 in narrative |
| HO-07 | GRIEVANCE | What percentage of complaints come from customers who have complained before? | pass | rows+narrative | expected 8.9; found in rows=True, in narrative=True |
| HO-08 | GRIEVANCE | Which complaint channel has the highest rate of escalation to the ombudsman? | pass | rows | expected top channel='Call Centre'; first row match=True, named in narrative=True |
| HO-09 | GRIEVANCE | How many UPI disputes were settled on each resolution path? | pass | rows | 4/4 key-value pairs matched in rows, 4/4 in narrative |
| HO-10 | GRIEVANCE | What is the total amount recovered on chargebacks we won? | pass | rows+narrative | expected 77432307.0; found in rows=True, in narrative=True |
| HO-11 | RM | How many relationship managers failed the quality gate in August 2026? | pass | rows+narrative | expected 28.0; found in rows=True, in narrative=True |
| HO-12 | RM | What is the average product mix score by relationship manager grade? | pass | rows | 4/4 key-value pairs matched in rows, 4/4 in narrative |
| HO-13 | RM | What was the total insurance sold between April and June 2026? | pass | rows+narrative | expected 4793.0; found in rows=True, in narrative=True |
| HO-14 | RM | How many customers have a churn risk score above 0.7? | pass | rows+narrative | expected 2688.0; found in rows=True, in narrative=True |
| HO-15 | RM | Which region had the weakest loan attainment in August 2026? | pass | rows | expected top region='South'; first row match=True, named in narrative=True |
