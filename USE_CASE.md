# Use case

[YOUR WORDS] This file was drafted with an AI pair engineer. The problem, the buyers and the value case are scored as yours, so rewrite them in your own words.

## The customer

The customer is a fictional Indian private-sector retail bank with about 6,000 loans across vehicle finance, microfinance, personal loans, cards, home loans and business loans. It has 18 branches in five regions. Every record in this repo is synthetic.

## The buyers

The executive sponsor is the Chief Risk Officer. The CRO is measured on these things:

- Gross NPA, the share of the loan book more than 90 days past due.
- Credit cost.
- Conduct breaches, and the regulatory penalties and reputation damage that follow them.

The domain owner is the Head of Collections and Recovery. The Head of Collections is measured on these things:

- Roll-forward rate, the share of accounts that move into a worse ageing bucket each month.
- Cure rate, the share of delinquent accounts that return to current.
- Cost to collect.
- Contacts outside the hours the RBI permits.

## The problem

Two parts of the loan book are under stress. The bank's microfinance loans in Solapur and its commercial vehicle loans in Indore are both getting worse. The collections team works harder in both places, but collects less.

The collections team does not have one list that says which accounts to work first and why. Each manager builds a list from several systems. The dialer vendor and the field app report the same contact attempts in different formats. So nobody can say with confidence how many contacts broke the rules.

Some of the pressure breaks the RBI rules on recovery agents.

- Agents call borrowers outside 08:00 to 19:00.
- Uncertified agents make contacts.
- Agents keep contacting borrowers whose own complaint is still open.

Those borrowers then complain, and some complaints reach the RBI Ombudsman.

The data also arrives late, or short. In June the dialer vendor's file arrived 37 rows short. Today a short file like that becomes a lower effort number on a report, and nobody notices.

## Why now

- The RBI's August 2022 circular on recovery agents says lenders must not contact borrowers before 08:00 or after 19:00. The lender is responsible for its agencies' conduct.
- Under the RBI Integrated Ombudsman Scheme, 2021, a customer can take an unresolved complaint to the Ombudsman. A complaint about recovery agents is a named ground.
- Microfinance and commercial vehicle stress raises collection pressure in exactly the places where conduct breaches are most likely.

## What the bank gets

- One worklist, refreshed every time new data lands. It ranks the delinquent accounts with a score whose reasons are stored on every row.
- The bank's conduct rules are applied before an account is worked. An account with an open grievance is held. An account contacted out of hours or by an uncertified agent is moved to a certified agency.
- Customer letters are read by an AI step as they arrive. Alleged agent misconduct is flagged for review.
- A completeness check on every source file, so a short or missing file is visible on the day it lands.
- Plain-language answers from Genie agents, governed per person, for both leaders.
- Every action needs a named approver, and the bank's controls can refuse it.

## Value hypothesis

The value case and its assumptions are in the README. The headline figures are in `evidence/HEADLINES.md`, and they come from the final run.
