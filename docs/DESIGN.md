# Design notes

Why this is built the way it is, and — more usefully — the defects that shaped it. Most of these were
found by an eval or a browser-driven QA run, not by looking at the app, which is the argument for having
both.

---

## Two identities, and why that decision drives everything

Business reads run **on behalf of the signed-in user**. Guardrail verification runs as the **app service
principal**.

That split is not symmetry for its own sake. Unity Catalog row filters mean two people asking one shared
agent the same question correctly get different answers. But a *control* must not work that way: if the
guardrail that checks "does this borrower have an open grievance?" runs under the caller's filters, then a
caller who cannot see the grievance gets told there isn't one, and the action is approved. A control that
the caller's own entitlements can blind is not a control.

So `action_plane/guardrails.py` deliberately omits the user's client, and `assert_not_blinded()` runs as
**Gate 0 of every action evaluation** — not merely at startup — proving the guardrail identity can see the
whole book — compared against a
row-count manifest the data generator writes, not against numbers typed in by hand.

The check is also proven **capable of failing**. Raise any expectation by one and it raises. A control that
only ever returns green is evidence of nothing, and the test suite asserts that it goes red.

---

## The controls are catalog objects, not prompt text

`is_within_rbi_conduct_hours()`, `agent_conduct_status()`, `has_open_grievance()`, `account_dpd_days()`,
`guardrail_visibility()` are Unity Catalog SQL functions. Three consequences:

- A compliance reviewer can read them without trusting the application.
- Anything can call them — the app, a notebook, a job, another team's service.
- They are evaluated in one batched round trip, so a guardrail pass is one query rather than eight.

Every check records `verified_by`. `payload` means the model's own claim was taken at face value; anything
prefixed `unity_catalog:` was confirmed against governed data. The UI renders that distinction rather than
showing all checks as equal, because an approver deserves to know which is which.

<a name="open"></a>
## A prompt rule is guidance; code is enforcement

The clearest lesson here, and it took two rounds.

The benchmark caught Genie computing a chargeback win rate correctly into its result grid and then replying
with only a clarifying question — *"would you prefer to see this by card type?"* — never stating the figure.
The grid is not what a person reads, so that is a non-answer wearing a correct answer's clothes.

The fix was an instruction in all three spaces: state the computed answer before offering any breakdown;
never reply with only a follow-up question. The case passed.

Then it happened again on a **held-out** question, with the rule in place. Asked for a recovery rate, Genie
computed 56.45% and replied *"would you prefer this calculated using collections and overdue from the same
month, or…"*. The instruction had not generalised.

It is now enforced in code. `agent.narrative_defect()` compares the figures in a leg's prose against the
numeric cells in its own result grid and flags prose that states none of them, with a special case for a
reply ending in a question mark. The fuser is told to read the figure out of `rows` itself rather than
repeat the question back, and the UI shows the operator why that lane's wording looks thin.

**Instructions move behaviour reliably enough to be worth writing, and not reliably enough to be a
control.** Anything you would be embarrassed to get wrong in front of a regulator belongs in code, where it
can be tested.

### Still open: fan-out double counting

The held-out suite caught Genie joining `collections_activity` to `delinquency_monthly` on
`loan_account_id` and summing `overdue_amount` across that join. `overdue_amount` is on the *one* side and
the join fans out to many contact attempts per loan, so the denominator inflated **1.30×** and the answer
came back as 43.4% instead of 56.45% — confidently, in prose, with the workings shown. Nothing about it
looks wrong.

This is classic fan-out double counting. The fix is to instruct pre-aggregation of one-side measures in a
CTE before joining. It is **deliberately unfixed**: tuning against a held-out failure destroys the only
honest measurement available. Fix it, then measure on a *new* held-out set.

---

## Pseudonymisation, not redaction

The first column mask returned a constant, so every customer became `CUXXXXXX`. It hid the identifier
perfectly and broke the data silently: thousands of complaint rows collapsed onto one key, so any join on
`customer_id` became a cross join. A guardrail asking "does this borrower have an open grievance?" would
have matched every borrower and blocked every action, for reasons nobody would have found quickly.

A salted hash keeps the mapping one-to-one — joins, counts and `DISTINCT` stay correct while the real
identifier never leaves the table. The governance suite asserts determinism, injectivity across the whole
customer master, and that the output leaks none of the input.

In production the salt belongs in a secret scope and must be identical everywhere: two tables masked with
different salts will join to nothing, silently.

---

## Referential integrity, and the control it silently disabled

Worth reading before extending the synthetic data, because this failure mode produces no error at all.

The customer master had 9,000 rows. Four other tables drew `customer_id` from a range 4.5× larger, so only
**21%** of loan and complaint customer references pointed at a customer that existed. Nothing failed —
Spark joins simply dropped the unmatched rows, every query returned a plausible number, every dashboard
rendered.

But the grievance hold resolves *loan → customer → open complaints*, and with both sides scattered across a
key space that size it almost never found a match. The control appeared to work — it fired in a demo — by
coincidental id collision.

Fixed with one id-producing helper and one constant. Then a second, deeper fix: correct keys alone left
complaints statistically independent of collections, so no account was simultaneously past due, contacted
*and* carrying an open grievance. That is not how a bank works — the RBI keeps "Recovery agents" as its own
ground of complaint precisely *because* recovery pressure produces grievances. Recovery-conduct complaints
are now generated from actual recovery pressure, scored on contact volume and out-of-hours breaches, and
they resolve slower because they genuinely do.

Two related defects, same root cause — a fact duplicated instead of derived:

- Complaint `product_code` and `branch_id` were random, so a recovery complaint from a microfinance borrower
  could be tagged as a vehicle loan in another city. It was visible in the call-assist HUD.
- The letters were generated from a hardcoded list whose metadata had drifted from the data, so a letter
  describing one city's microfinance visit sat beside a record naming a different city and product — and the
  The documents lane shows letter and record side by side.

**A rollup table that was pure invention.** `sla_tracker` exists to keep common grievance questions off the
raw complaint rows. It was generated with its own independent random numbers and disagreed violently with
`complaints`: **5.8× the complaint count** and **6.5× the ombudsman escalations**. Both tables are in the
same schema and both are legitimate things for an agent to reach for, so one question had two contradictory
answers and no way to tell which you were given. A pre-aggregated table that disagrees with its own detail
table is worse than not having one. It is now a genuine rollup, and every column reconciles exactly.

---

<a name="voice"></a>
## Voice: agent assist, not a voice bot

The Databricks voice reference stack (GPU-hosted ASR, semantic end-of-turn VAD, streaming TTS, Genie in the
middle) measures **30–40 seconds end to end** in its current form, and real-time inference is not yet a
property of the serving stack. Two conclusions follow, and the second matters more:

1. A 30-second pause kills a self-service bot.
2. Putting a generative voice in front of a retail borrower is a conduct and data-protection exposure no
   bank should take on in a first project.

Reframed as **assist**, that latency becomes an asset: the officer keeps talking while the platform looks up
behind them. So speech-to-text runs **in the browser** — lower latency than any hosted ASR, and no customer
audio leaves the device or reaches a model, which is the first question a privacy officer asks. The server
spends its time on the part that needs governance: resolving what was said against Unity Catalog under the
caller's entitlements, and running the same conduct controls the action plane runs.

Deliberately **not** Genie: a Genie message costs one of roughly five per minute for the entire workspace,
and the HUD refreshes every few seconds. The lane uses narrow parameterised SQL. The typed composer remains
the path for open-ended questions — voice is never the only way to get an answer.

Spoken account numbers resolve in English, Hindi and Marathi, in Devanagari script, Devanagari digit glyphs
and Roman transliteration, because which form the Web Speech API returns depends on recogniser and handset.
**Only the number handling is tested.** How well a browser transcribes conversational Hindi or Marathi is
unverified and needs a native speaker and a microphone.

---

## Vector Search is an ungoverned copy

A Vector Search index is a **copy of the text held outside the governed table**, and Unity Catalog row
filters and column masks **do not follow data into it**. An index queried directly by end users is a clean
route around every control described above.

So the app does two steps: the index is queried as the service principal and returns only complaint ids and
the matched snippet; those ids are then re-read from the governed table **as the caller**. The visible
consequence is the feature, not a limitation — retrieval can find a letter the caller may not read, and the
caller is told the match exists without the content. Retrieval locates; governance decides.

The corpus also had to be worth searching. Retrieval over a dozen documents is theatre; it is a category
filter that SQL does better. The generator produces several hundred letters across every ground of
complaint, with multiple distinct narratives per ground, so the index has something to discriminate on.

---

## Operational constraints that shaped the code

- **Genie's Conversation API allows roughly five messages per minute for the whole workspace.** Not a
  concurrency limit — a *rate*. A semaphore is the obvious tool and the wrong one; admission control is over
  a rolling window. A three-domain question spends three of the five.
- **Databricks Apps terminates an HTTP request at 120 seconds.** The turn budget is 95s so the app returns a
  partial, honest answer instead of having the proxy cut the connection while background threads keep
  spending quota on a reply nobody will read.
- **The SDK's default Genie wait is twenty minutes.** Left unset, a slow call holds a worker and a quota slot
  long after Apps has given up.
- **Every Statement Execution API call is an independent session**, so `USE CATALOG` never carries. Catalog
  and schema are bound per statement.
- **MLflow inside an Apps container resolves to a local SQLite file** and disables tracing silently unless
  the tracking and registry URIs are pinned explicitly.
- **`CREATE OR REPLACE TABLE` drops row filters, column masks and comments.** Governance must be re-applied
  after any table rebuild, or the app comes up ungoverned while looking healthy.
- **Traces contain user questions and returned rows**, which are user-scoped data. ACL the MLflow experiment
  to the same people who may read the underlying tables.

---

## Testing approach

Three suites, because they fail differently.

**`eval/run_eval.py`** grades answers against ground-truth SQL executed at run time — never a saved value,
which rots the moment anyone reloads the data. It checks the result grid *and* the narrative separately,
because the narrative is what a person reads — both required for scalar answers, though set and
top-k cases can pass on the grid alone. Router accuracy is reported apart from answer accuracy, and
cross-domain routing apart from single-domain, because routing a DPD question to the collections agent is
nearly free while recognising that one question needs two agents is the actual job.

**`eval/heldout/`** is fifteen questions never used to fix anything. Its score is only meaningful the first
time it runs.

**`eval/governance_tests.py`** asserts the controls, and its most important test is **non-vacuity**. Seeing a
masked-looking value does not prove a mask ran — the raw value could always have looked like that, and a
mask that protects nothing is *indistinguishable in SQL* from one that works. The suite compares the
governed table against the ungoverned CSV the generator wrote. It exists because a masked person-name column
was briefly mistaken for a broken one, and nearly "fixed".

**`scripts/visual_qa.mjs`** drives the real UI in a headless browser. It caught timestamps rendered in UTC
in an application whose subject is a local-time compliance window, a kill switch left off after a rehearsal,
colleague identifiers in an audit feed, a fabricated `:00` minute on a time that never happened, and a
frontend/backend field-name skew that produced a *reassuring empty state* — a panel reporting "no contact
attempts" for an account with 66. None of those are reachable by a type checker.
