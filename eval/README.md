# Benchmark

Two numbers, deliberately kept apart, plus the caveats that decide how much either is worth.

```bash
python3 eval/run_eval.py golden     # validate the benchmark itself — no Genie quota spent
python3 eval/run_eval.py router     # 42 routing cases, no Genie quota
python3 eval/run_eval.py genie      # 30 questions against the three Genie Agents (~11 min)
python3 eval/run_eval.py genie --only GRV-08,RM-03
```

## What is measured

**Router accuracy** — did the supervisor send the question to the right domain agent(s)? Scored three
ways, because one number flatters it: `exact` (the routed set equals the expected set), `full recall`
(no expected domain was missed, so no blind spot in the answer), and `wasted Genie calls per question`
(domains consulted that nobody asked for — under a ~5 message/minute workspace quota, waste is the
constraint that matters, not latency).

Single-domain and cross-domain cases are reported separately. Routing "what is the GNPA by region" to
collections is nearly free; the real test is "why did complaints rise where delinquency rose", which
needs two agents and must not reach for a third.

**Genie accuracy** — did the domain agent return the right number? Graded against **ground-truth SQL
executed at run time**, on the same warehouse, under the same identity, in the same minute as the
Genie call. Never against a frozen expected value: a frozen number rots the moment anyone reloads the
data, and a rotted benchmark reports a regression that never happened.

Both the **result grid** and the **narrative** are checked, and they are not interchangeable. The
narrative is what a banker reads. GRV-07 computed the chargeback win rate correctly and then replied
"would you prefer to see this by card type?" without ever stating the figure — right grid, useless
answer. That is a failure, and only a grader that reads the prose catches it.

## The held-out suite

```bash
python3 eval/run_eval.py golden --heldout   # validate it
python3 eval/run_eval.py genie  --heldout   # 15 fresh questions, ~6 min
```

`eval/heldout/` holds 15 questions that were **never used to fix anything**. They exist because the main
suite cannot answer the only question that matters to someone deciding whether to trust this: how does the
agent do on questions nobody tuned it against?

They deliberately probe different ground from the tuned suite — recovery rate as a ratio across two tables,
contactability, PTP rate by channel, NPA exposure by product, bucket improvement, resolution TAT by ground,
repeat-complainant share, escalation rate by channel, UPI resolution paths, chargeback recovery, quality-gate
failures, mix score by grade, quarterly insurance, churn cohort size, weakest loan attainment.

### Results

| Run | Score | What changed |
|---|---|---|
| **First run — the number that counts** | **12/15 (80%)** | Nothing. This is the generalisation estimate. |
| Current regression | 13/15 (86.7%) | A **data** defect the suite exposed was fixed (`sla_tracker` did not reconcile with `complaints`). **No instruction was tuned**, and the suite's questions were not edited. |

Compare with 30/30 on the tuned suite. That gap — 100% in-sample against 80% held-out — is the single most
useful number in this project, and it is why the tuned score should never be quoted on its own.

**The two that still fail, diagnosed but deliberately not fixed:**

* **HO-01 is a real agent defect, and the most instructive one found anywhere in this project.** Asked for
  the microfinance recovery rate, Genie joined `collections_activity` to `delinquency_monthly` on
  `loan_account_id` and summed `overdue_amount` across that join. `overdue_amount` lives on the ONE side and
  the join fans out to many contact attempts per loan, so the denominator inflated **1.30x** and the answer
  came back as **43.4%** instead of 56.45%. Stated confidently, in prose, with the workings shown. Nothing
  about it looks wrong. This is classic fan-out double counting and no instruction currently warns about it;
  the fix is to pre-aggregate one-side measures in a CTE before joining. It is left unfixed on purpose —
  tuning against a held-out failure destroys the only thing the suite is for. Fix it, then measure it on a
  **new** held-out set.
* **HO-09 is this benchmark's bug, not the agent's.** Asked how many disputes were "settled" per resolution
  path, Genie filtered `status = 'Closed'`; the golden counted every dispute. Genie's reading of "settled" is
  arguably the better one. The question is **left exactly as written**, because editing a question after
  seeing the answer is how an eval becomes worthless. It is recorded here as a known-weak case instead.

**The rule that makes this suite worth anything: do not tune against it.** The moment an instruction is
changed because of a held-out failure, this has become another in-sample regression suite and a new held-out
set is needed. Record the first result, and read later runs as regression checks rather than fresh evidence.
Results are written to `eval/results/heldout-genie-*.json` so they can never be confused with the tuned suite.

## Caveats that must travel with the numbers

**The score is IN-SAMPLE.** These 30 questions were used to find and fix defects in the space
instructions, and three rounds of fixes were made against them. The result therefore measures "the
agents handle their own benchmark", not how they will do on questions nobody has seen. Treat it as a
regression suite, not a generalisation estimate. To measure generalisation, write new questions and
run them once before tuning anything.

**Genie is not deterministic.** Across runs of the identical suite, individual cases flipped in both
directions — GRV-07 and RM-08 passed in one run and failed in the next, while GRV-08 and RM-09 did the
reverse. Quote the number with its run date, and never quote a one-case difference between two runs as
an improvement.

**It measures the domain agent, not the whole app.** `genie` calls `agent._genie_leg()` with the question
verbatim, deliberately, so a miss can be attributed to one Genie space rather than to the supervisor. The
app does not work that way: the router rewrites each question into its domain's vocabulary first, and that
reframing changes the SQL Genie writes. HO-01 is the clean example — through `/api/ask` the same question
came back **56.4%**, correct, with no fan-out join at all, while the eval's verbatim call produced 43.4%.

Do not read that as "the app is more accurate". Genie is non-deterministic and one observation is not a
measurement; the fan-out risk is real either way. Read it as: these numbers bound the *component*, and the
end-to-end path has an extra step that can help or hurt and is not yet separately measured. Measuring it
would need a third harness driving `/api/ask`, at a router LLM call plus a Genie message per question.

**One identity, unrestricted.** The suite runs as a human with full visibility, and the golden SQL runs
as that same identity. A row-filtered user's correct answers are different numbers. This measures the
agent while holding governance constant; it does not test governance. The governance tab and the
guardrail integrity check do that.

**Costs real quota.** Genie's Conversation API allows roughly five messages per minute for the whole
workspace, so a full run takes about eleven minutes and will starve anyone else's Genie session while
it does. Do not run it during a demo.

## What the benchmark found

Worth recording, because these are the defects that would otherwise have surfaced in front of the bank:

| Case | Defect | Fix |
|---|---|---|
| GRV-08 | Asked for complaints open past SLA, Genie answered **0**. `sla_breached` is only computed at resolution and is FALSE for all 132 open complaints — and a *trusted SQL example* in the space taught that exact wrong pattern. The true answer is 5. | Instructions now separate the resolved case (use the flag) from the open case (use ageing vs `sla_days`), and the bad example was corrected. A confidently wrong "0" reads as good news, which makes it the worst possible failure mode. |
| RM-09 | "Which grade has the highest clawback rate" — Genie silently narrowed to August 2026 and answered Junior. Over the full window the answer is Lead (18.5% vs 18.1%). It disclosed the scope, but nobody asked for it. | All three spaces now say: if the question names no period, use the full window and say so. |
| RM-08 | "Affluent segment customers" was widened to Affluent + Private + Mass Affluent, giving 2,813 instead of 966. | Instructions now require filtering on a value that exists literally in the column, and offering the wider reading separately if at all. |
| GRV-07 | Correct grid, but the narrative was only a follow-up question. | Instructions now require stating the computed answer before offering any breakdown. |
| RM-03 | **Benchmark bug, not an agent bug.** The case demanded the agent guess the benchmark's private band label (`at_or_above_0.50`); the agent returned both averages exactly right under its own headings. | Cases may declare `key_aliases` as regexes. Enumerating phrasings became whack-a-mole — literals accepted ">=0.50" then met "0.50 and above" — so one pattern per band states the intent instead. |
