# Role-play script, demo sequence and answer bank

[YOUR WORDS] This is a draft. Read it aloud twice and rewrite anything you would not naturally say. The role-play has two people in one session: the Chief Risk Officer, who funds it, and the Head of Collections, who must live with it. Present for about 17 minutes and leave the rest for questions.

## Set the stage (2 minutes)

- Say what you heard. "Solapur microfinance and Indore commercial vehicles spiked this year and are still about twice the rest of the book. Some of the collection pressure is breaking the RBI contact rules, and your teams find out when the complaint arrives."
- Say your goal. "In the next fifteen minutes I want to show you one worklist that tells your team who to work first, why, and who they must not contact."
- Give the agenda: the overview, the worklist, one case, one question to Genie, then the pilot.
- Ask what they want covered, then wait. Use the answer in the demo.

## Demo stops (tell, show, tell)

1. The overview, for the CRO.
   - Tell: "This is where the book stands this month, read as you."
   - Show: gross NPA, the roll-forward rate, out-of-hours contacts, and the completeness line with the June dialer file 37 rows short.
   - Tell: "You see the risk and you see whether the data behind it is complete. A short file is visible on the day it lands."

2. The worklist, for the Head of Collections.
   - Tell: "This is the order your team works the book."
   - Show: the top accounts, the reasons in words, the conduct flags, and the held accounts.
   - Tell: "Your managers stop building lists by hand, and nobody contacts a borrower with an open grievance."

3. One case.
   - Tell: "This is what an officer does with one account."
   - Show: the AI brief, then change the status and add a note, then propose a reassignment, then try to approve it yourself and show the refusal.
   - Tell: "The officer's notes survive every refresh. Every change is recorded. No one approves their own action."

4. Genie.
   - Tell: "You can ask your own question in plain language."
   - Show: "How many accounts are on the collections worklist in each region, and how much do they owe?"
   - Tell: "The answer is governed. A regional head asking the same question sees only their regions."

5. New data lands (if time allows).
   - Show: run `ct_land_period` and the job starting on its own.

## Close

Ask directly. "Can we agree a six-week pilot in West and Central, starting on a date you choose, with these three success criteria?"

## Answer bank

- What does success look like after the pilot?
  - Agree two to four targets in week one. For example, roll-forward rate down by an agreed number of points on worked accounts, zero out-of-hours contacts on worked accounts, and every source file reconciled each month.

- What does it cost?
  - It runs on serverless compute, so you pay while it runs. One cycle is one pipeline update, about 200 short model calls for the briefs, and the evaluation.
  - The pilot measures the real cost on your data volume.
  - We weigh that against the recovery and conduct drivers in the value case.

- What if your results disagree with my team's?
  - Each difference goes to a named reviewer in your team each week.
  - The score's reasons are on every row, so the reviewer can see which component caused it.
  - Each difference either fixes our rules or fixes the old list. Either way it is a calibration result.

- Can I trust the AI?
  - The AI reads letters and writes explanations. It does not decide.
  - The bank's rules decide how an account may be worked.
  - Letter triage is measured against the ground your desk recorded. It matches on 97% of letters, and it found every letter alleging agent misconduct.
  - A judge from a different model family checks every brief. The officer makes the final call, and every action needs an approver.

- What about a late or corrupted file?
  - Each sender declares what it sent. Every file is reconciled. A short file shows as a break with the number of missing rows.
  - Bad rows are kept in quarantine with a reason, never dropped.
  - A re-sent file is safe, because each file is read once and re-sent records are de-duplicated.

- Security, integration and operations?
  - Every published table that holds customer data carries column masks, and every table with a region carries a row filter. The raw and quarantine layers are not granted to anyone. Entitlements are rows a steward can change.
  - The case queue lives in Lakebase. The app shows each person only the regions Unity Catalog grants them.
  - Your source systems do not change. They drop files into a volume as they do today.
  - It is one bundle and one job, and the job starts when a drop's manifest lands.
