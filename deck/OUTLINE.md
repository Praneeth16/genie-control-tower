# Deck outline

[YOUR WORDS] Approve or change this outline before the slides are built. Each title is the takeaway. Every number comes from `evidence/HEADLINES.md`. The slides use the Databricks corporate template ("TEMPLATE Databricks Corporate Slide 2025") and are exported to `deck/genie-control-tower.pdf`.

1. Title. Work the right 589 accounts first, and never contact a borrower you must not contact.

2. The answer up front.
   - 589 delinquent accounts, INR 44.1 crore, ranked with reasons.
   - 40 accounts held because the borrower's grievance is open.
   - 2,499 contacts outside RBI hours found, and a rule that moves those accounts to a certified agency.
   - The ask: a 6-week pilot in the West and Central regions.

3. The problem. Collections effort is up and recovery is down in two stressed books, and 4.0% of contacts break the RBI contact window. Why now: the RBI's 2022 recovery agent circular and the Integrated Ombudsman Scheme.

4. Today against tomorrow.
   - Today: hand-built lists from several systems, short files that nobody sees, and conduct breaches found after the complaint.
   - Tomorrow: one list rebuilt every time data lands, each file checked against what the sender declared, and conduct rules applied before contact.

5. How it works, as one flow. Source files, then the Lakeflow pipeline, then governed tables, then the AI triage and the score, then the Lakebase case queue, then the app and Genie, all run by one job.

6. What you are about to see. The CRO's overview, the Head of Collections' worklist, one case worked and refused, and one question to Genie.

7. What each leader gets.
   - CRO: gross NPA and its trend, conduct exposure in one number, and completeness of the data behind both.
   - Head of Collections: the order to work the book, the reason for each account, and which accounts must not be contacted.

8. The value case, with assumptions stated. The four drivers from the README value table, each with its assumption, so the bank can put in its own numbers.

9. Why you can trust it.
   - Every source file is reconciled against its manifest, and 1,045 bad rows are kept with a reason.
   - The same query gives four personas four different answers, enforced by Unity Catalog.
   - The AI reads and explains. The bank's rules decide. Letter triage matches the recorded ground on 97% of letters, and a judge from another model family checks the briefs.
   - Every action needs a named approver, and the person who raised it cannot approve it.

10. The platform on one page. Lakeflow, Unity Catalog, Lakebase, AI Functions with MLflow evaluation, Genie, Databricks Apps, Lakeflow Jobs.

11. A bounded pilot.
    - Scope: West and Central collections, 6 weeks.
    - Success criteria, agreed in week one: roll-forward rate down by an agreed number of points, zero contacts outside RBI hours on worked accounts, and every source file reconciled each month.
    - What we need from the bank: read access to the dialer, field app, LOS and CRM extracts, a collections manager for two hours a week, and a named compliance reviewer.

12. Close. A start date for the pilot and the people to name this week.
