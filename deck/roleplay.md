# Role-play script and answer bank

The role-play is a 20 to 30 minute session with two personas at once. One funds the work and one has to live with it. In this build they are the Chief Risk Officer and the Head of Collections and Recovery. If the session gives you a technical persona instead, such as a head of data or technology, the same script works and the technical answers below are for that person.

Three facts about how it is scored change how you present.

1. The scorer reads text only. It cannot see a screen. Every "show" has to be said out loud with the actual numbers, as if describing the screen to someone on the phone. "Here you can see the figures" scores nothing. "Gross NPA is 2.95 percent, down from 3.51 last month" scores.
2. It scores five things: demo set-up, tell-show-tell, value communication, reading the room, professionalism. Each demo stop should have all three parts said in words, and each answer should name who asked and answer at their altitude.
3. Present for about 17 minutes, then stop and take questions. After the agenda, ask what they want covered and wait for the answer before going on. Use what they say.

Every number below is from `evidence/HEADLINES.md` and `RUN_EVIDENCE.md`. Do not improvise a number. If asked something the data does not answer, say so and say how the pilot would measure it.

## The talk, in eight parts (about 17 minutes)

### 1. Set the stage (2 minutes)

Say what you heard. "You told me two things. Solapur microfinance went from 11.7 percent delinquent in February to 43.6 percent in May, and Indore commercial vehicles reached 26 percent. Both have eased but are still about twice the rest of the book. And some of the collection pressure is breaking the RBI contact rules, which you learn about when the complaint arrives."

Say your goal. "In the next fifteen minutes I want to show you one worklist that tells your team who to work first, why, and who they must not contact, rebuilt from your source systems' own files every time a month lands."

Give the agenda. "Four stops. The overview for you, [CRO name]. The worklist and one case for you, [Head of Collections name]. One question to Genie. Then a bounded pilot."

Ask and wait. "Before I start, is there anything specific either of you wants covered?" Stop. Wait for the answer. Say where in the four stops you will cover it, and then do.

### 2. The answer up front (1 minute)

"Four numbers. 589 delinquent accounts, 44.1 crore rupees outstanding, each ranked with the reason on the row. 40 accounts held because the borrower's grievance is still open. 2,499 contacts, 4 percent of all contacts, made outside the RBI window of eight in the morning to seven at night. And 176 of 177 source files reconciled to what the sender said it sent. Everything else I show you supports these four."

### 3. Stop one, the overview, for the CRO (3 minutes)

Tell. "This is where the book stands at the August month end, read as you, from the governed tables."

Show, in words. "Gross NPA is 2.95 percent, down from 3.51 in July. The roll-forward rate, accounts that moved to a worse bucket this month, is 9.1 percent. Out-of-hours contacts are 2,499 of 63,230. Below those sits one line you will not have today: 176 of 177 source files reconciled to their senders' manifests, and the one break named. The June dialer file landed 3,455 of 3,492 declared rows, 37 short. Your credit cost is computed too: March, when the stress arrived, needed 120 lakh of new provisions; August released 51.7 lakh, on a stated 15 percent provision assumption you can replace."

Tell. "You see the risk and you see whether the data behind it is complete. A short file is visible on the day it lands, not at quarter end."

### 4. Stop two, the worklist, for the Head of Collections (3 minutes)

Tell. "This is the order your team works the book, and why."

Show, in words. "The top account is a commercial vehicle loan in Indore, 121 days past due, 33 lakh outstanding, score 85. The reasons are written on the row: days past due plus 50, rolled to a worse bucket in two of the last three months plus 20, outstanding above the exposure band plus 15. Next to it, the conduct flags. 153 accounts carry one, and 113 of those are recommended for reassignment to a certified agency. 40 accounts are marked held, grievance open, and the app will not let an officer propose contact on them. Cost to collect is on the overview for you too: 1.23 percent of the amount collected in August, against 1.5 percent in June, on a stated 25 rupees per call and 350 per visit."

Tell. "Your managers stop building lists by hand from four systems, and nobody contacts a borrower with an open grievance."

### 5. Stop three, one case (2 minutes)

Tell. "This is what an officer does with one account."

Show, in words. "The officer reads a sixty-word brief the AI wrote from the facts on the row. The officer sets the status to promise to pay and writes a note. The next refresh keeps that note, because the columns a person owns are never overwritten. The officer proposes reassigning the account to agent AG024. The guardrail refuses: AG024 is not conduct certified. With AG007 it passes. Then I try to approve my own proposal, and it is refused: separation of duties. A persona without the approver role is refused too."

Tell. "Every change is recorded in a history the database itself refuses to rewrite. No one approves their own action. Your compliance reviewer can read the whole trail."

### 6. Stop four, Genie (2 minutes)

Tell. "Either of you can ask your own question in plain language."

Show, in words. "I asked, what was the microfinance delinquency percentage in Solapur in May 2026. Genie wrote the SQL, joined delinquency to the branch table, and answered 43.6 percent, 223 of 511 accounts. I ran the ground-truth SQL in the same minute, 43.6. On the full benchmark it matched 35 of 35, and 15 of 15 on a held-out set it had never seen."

Tell. "The answer is governed. A regional head asking the same question sees only their regions, because the filter is in the table, not in Genie."

### 7. How it works, one sentence per stage (2 minutes)

For the CRO, keep it to this. "Your source systems drop their files as they do today. One job starts when the month's manifest lands. A pipeline turns the files into governed tables and quarantines bad rows with a reason. Inside that pipeline, the AI reads the letters and a points score ranks the accounts. The cases go to a Postgres queue your officers work in the app. Genie answers questions. One bundle, one job."

If a technical persona is present, add. "Serverless Spark Declarative Pipelines in SQL. Row filters and masks declared inside the gold table definitions so they survive a full refresh. Lakebase Postgres for the case queue, with an append-only history trigger. ai_query with a strict JSON schema, judged every cycle by MLflow judges from a different model family. Deployed as one Databricks asset bundle."

### 8. The pilot and the ask (2 minutes)

"Six weeks, West and Central collections, your data in your workspace. Three success criteria agreed in week one: roll-forward rate down by a number of points we set together on worked accounts, zero contacts outside RBI hours on worked accounts, and every source file reconciled each month. From you I need three things: read access to the dialer, field app, loan system and CRM extracts, a collections manager for two hours a week, and a named compliance reviewer."

Ask directly. "Can we agree a start date this week, and can you name the collections manager and the compliance reviewer?" Then stop talking.

## Answer bank, by who asks

Answer first, detail second. Name who you are answering. For the CRO, the outcome and the control. For the Head of Collections, what changes on Monday morning. For a technical persona, the mechanism.

### What does success look like after the pilot?

Two to four measurable targets, agreed in week one, measured by the system itself. Roll-forward rate on worked accounts, from the delinquency table. Zero out-of-hours contacts on worked accounts, from the contact table. Every file reconciled, from the reconciliation table. A fourth if you want it: cost to collect on the worked book, from the KPI table. Week six compares against week one in the same tables.

### What does it cost?

Serverless, so you pay while it runs. One cycle is one pipeline update of a few minutes, about 200 short model calls for the briefs, and the evaluation. The pilot measures the real cost on your volumes and prints it, so you are not taking my estimate. We weigh it against the four value drivers, each with its assumption stated: one point of cure on 44 crore is about 44 lakh a year, half the out-of-hours contacts removed is about 1,250 fewer breaches, forty held accounts are forty fewer likely Ombudsman cases a month, and reconciling 18 feeds automatically is about six analyst days a month. Replace any assumption with your own number and the sheet recomputes.

### What if your results disagree with my team's?

Good. That is the point of a pilot. Each difference goes to your named collections manager in the weekly two hours. The score's reasons are on every row, so the reviewer sees which component caused it. Each difference ends one of two ways: our rule was wrong and we fix it, or the old list was wrong and you fix it. Either way the book gets better. We log every one.

### Can I trust the AI?

The AI reads and explains. It does not decide. The bank's rules decide how an account may be worked, in SQL your audit team can read. The letter triage is measured against the ground your grievance desk recorded: 97 percent agreement on 713 letters, and it found every letter alleging agent misconduct. Each brief is checked by rules and by a judge from a different model family, every cycle, and the results sit in a governed table. The officer makes the call, and every action needs a named approver who is not the proposer. When the judge was wrong early on, we rewrote the judge, not the pass mark; both versions are in the record.

### What about a late or corrupted file?

Each sender declares what it sent in a manifest. Every file is reconciled against it: declared, landed, loaded, quarantined. A short file shows as a break with the number of missing rows, on the day. You have one already: the June dialer file, 37 rows short. Bad rows go to quarantine with the reason, never dropped. A re-sent file is safe, because each file is read once and re-sent records are de-duplicated, which is how 589 duplicate dialer rows were removed last cycle. A late record is kept and flagged, not lost.

### Security, integration, operations?

Security. Every published table with customer data carries column masks, every table with a region carries a row filter, declared in the table definition so they survive a refresh. The raw and quarantine layers are granted to no one. Entitlements are rows a steward can change and audit. Four real service principals ran the same query and got four different answers; that run is in the repository.

Integration. Your source systems do not change. They drop files into a volume as they do today. The dialer and field app arrive in different shapes and are conformed into one table.

Operations. One bundle, one job. The job starts when a drop's manifest lands. Every cycle re-evaluates the AI and writes the scores to a table, so drift is visible. The officers' notes live in Lakebase Postgres and survive every refresh.

### Pushback you should expect, and the answer

Why not our dialer vendor's analytics? They see their own calls. They do not see the field app, the loan system, the complaints or the letters. The breaches we found are visible only when all five are in one place.

Our data must stay in India. The workspace is in your region. Nothing leaves it. The model calls go to Databricks model serving inside the same platform.

RBI outsourcing rules for agencies. The build enforces the two rules the circular puts on you: contact hours and agent certification. Both are functions in the catalog and both refused an action in the demo.

Hallucination. The model never writes a number it was not given. A deterministic check reads every digit in every brief back against the facts; last cycle it passed on 100 percent of 200 briefs. The letter summaries are masked like the letters themselves.

A manager will override the score. Good. The override is a human-owned column and it survives the refresh. We count overrides in the pilot and review them weekly. Many overrides on one component means the rule is wrong.

How long to add a new source? A new file type is one bronze table, one typed view with its quality rules, and a manifest from the sender. The pattern is the same for all 18 feeds.

Why Postgres as well as the lakehouse? Officers edit one case at a time and need it saved instantly. That is a transactional store. The lakehouse recomputes the book each cycle. Each does the job it is built for, and the case status is published back to the governed tables so the CRO sees the work.

What did the AI get wrong while building this? Say it plainly. The first brief prompt agreed with the bank's rules 14 percent of the time. Putting the rules in the prompt reached 100 percent but the briefs cited rule numbers and the grounded score fell. Giving the model the decision as a fact and asking it only to explain fixed both. The judge was mis-specified once and was rewritten, not softened. All in the build log.

## Rehearsal plan

1. Read parts 1 to 8 aloud, timed. Target 15 to 17 minutes. Cut words until it fits.
2. Have someone, or an AI chat, play the CRO and the Head of Collections. Ask them to interrupt with the six prepared questions and three of the pushback items. Answer from memory.
3. Record yourself once. Listen for numbers said wrong. Fix the three you fumble.
4. In the session: send the agenda, ask what they want covered, then stop and wait. Do not continue until they answer.
5. At each stop, say the three parts in words. "Here is what I will show you." The numbers. "Here is what it means for you."
6. Close with the ask and stop talking.
