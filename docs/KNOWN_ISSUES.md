# Known issues

## Fixed in the FE Bar build

- Separation of duties now applies to people. The proposer of an action is the signed-in person, not the
  agent, so whoever asked for an action cannot approve it.
- The guardrail's region check reads the region from the governed record, not from the request body.
- Executing an approved action requires the approver role.
- A rejection is recorded in `rejected_by`, not `approved_by`.
- `complaint_documents` is governed: letters follow their complaint's region and their text is masked.
- The space instructions no longer contain benchmark answers, and the RM space's literal-value rule and its
  example SQL agree.
- The guardrail's expected counts come from `gold_row_counts`, which the pipeline computes, not from a
  manifest file that went stale when the data was rebuilt.
- Install is the bundle. Genie space ids and the dashboard id come from the bundle; nothing is copied by hand.


Written after an independent static audit of this repository. Everything below is either **fixed** and
recorded because the failure mode is instructive, or **open** and listed so nothing here is overclaimed.

Two of these were defects in claims this project makes about itself, which is the worst kind, and both came
from an audit rather than from using the app.

---

## Fixed as a result of the audit

**The guardrail integrity check was not a gate.** `assert_not_blinded()` existed, was tested, and was
called by the voice lane and the governance panel — but **not by `evaluate()`**, and not at startup, while
the module docstring claimed it ran "at startup". So an action could be evaluated and executed by a
guardrail identity that was being row-filtered out of the very evidence it exists to check. That does not
fail loudly: a blinded control returns a full set of green ticks. It is now **Gate 0 of every evaluation**,
fails closed, and is proven capable of failing. Checking once at startup would only have shown it was true
once — a grant can be revoked at any moment afterwards.

**Semantic search returned content outside the caller's entitlement.** `semantic_search` retrieved the
letter text as the service principal, built a snippet, and returned the ground, the city and that snippet
*with a flag* saying the caller was not entitled to the record. A flag is a CSS choice, not
authorisation — the payload had already crossed the boundary and was visible in the JSON and the network
tab. It leaked exactly the rows the row filter had removed. Content is now **stripped**, not labelled: what
survives is the fact that a match exists and the id needed to request access.

**A partial manifest silently dropped a check.** `_load_expected_visibility()` filtered the expected row
counts to whichever keys the manifest happened to contain, so a manifest missing a table meant that table
simply was not verified — a blinding the blinding-detector could not see. A missing key now raises.

**The export tool published the identifiers it was written to suppress.** The denylist was a literal list
of workspace ids, the service principal id and an email — and the file exempted itself from its own scan.
The denylist is now *derived* from the local `.env` and workspace identity, and the tool is excluded from
its own output, so there is nothing in it to leak.

**The text-to-SQL fallback was tied to the authoring catalog.** The bundled instruction documents hardcoded
a catalog name, so the fallback — the path taken precisely when a Genie space is unavailable — would have
generated SQL against a catalog the installing workspace does not have. They are now templated and rendered
at load time.

**Smaller, all real:** `package-lock.json` resolved every dependency through an internal proxy, so external
installs would fail. The chat-model *grant* was hardcoded while the runtime read a variable, so changing the
model produced an app permitted on one endpoint and configured for another. `run_eval.py` exited 0 even when
answers were wrong, making it useless in CI. A fresh app service principal had no `SELECT` on the tables or
`EXECUTE` on the control functions and no unrestricted row entitlement — see `scripts/grant_app_sp.py`.

---

## Open

Listed with what would fix them. None is hidden behind a claim to the contrary.

**Fan-out double counting in generated SQL.** (Found in September 2026. The question passed in the run of
2026-10-29, but Genie is not deterministic, so this stays open.) A one-side measure summed across a
many-side join inflated a denominator 1.30×, answering 43.4% where the truth was 56.45% — confidently, with the workings shown. Found
by the held-out suite and **deliberately left unfixed**, because tuning against a held-out failure destroys
the only honest measurement available. Fix by instructing pre-aggregation in a CTE, then measure on a *new*
held-out set.

**The action list is not scoped to the caller.** `/api/actions` lists every action the agent raised,
not only those in the caller's regions. Execution now requires the approver role (fixed in the FE Bar
build), so a second user can no longer execute an action they could not approve.

**An action's state change and its event are separate writes.** A crash between them can leave a state
change without its event. The events table itself is now append-only by trigger (`lakebase/006`), so the
lineage cannot be rewritten. Fix the remainder by wrapping the transition and its event in one transaction.

**The connector interpolates values into SQL rather than binding them.** `ALTER CONNECTION` embeds a
freshly minted bearer token and `http_request` embeds the JSON payload, both by string interpolation with
manual quoting. Quoting stops it breaking; it does not stop a token and a customer payload appearing in
query history and diagnostics. Fix: bind parameters, and source the token from a secret scope.

**The voice lane can report a green verdict on no evidence.** When no loan or complaint resolves, the
grievance check reads zero open complaints and passes, and the NPA check disappears entirely rather than
being reported as unknown. A control with no evidence should say "unknown", not "clear". The clock selector
is also operator-controlled, which is deliberate for demonstration and means the displayed conduct verdict
is a simulation of a time, not a reading of one.

**The supervisor's budget is partial.** Routing is not deadline-bound, the fuser runs after waiting on all
legs without an overall cap, and the text-to-SQL fallback has no timeout. The rate limiter is
process-local, so two app replicas would each admit the full per-minute budget.

**Failures that return success shapes.** Session-lineage writes to Lakebase are caught and discarded, so a
turn can return a complete answer with broken provenance. Document search and listing convert
infrastructure errors into HTTP 200 with an "unavailable" note. Degrading is right; degrading *silently* is
not — these should surface a warning in the response the UI renders.

**`/api/health` is open to any app user.** It shows the service identity, catalog, schema, warehouse and
Lakebase names. The approver directory now requires the administrator role (fixed in the FE Bar build).

**The Lakebase sync aborted once.** In the first full cycle, `serve/sync_cases.py` ended with a SIGABRT
and succeeded on retry. The cause is not known. The task retries twice, which is safe because the upsert is
idempotent.

**Some letters' ground is ambiguous.** After prompt v2, the letter triage disagrees with the recorded ground
on 21 of 690 letters, all deposit account complaints about charges. Either label is defensible, so the
recorded ground stays the source of truth and the AI ground is shown as a reading of the letter.

**Vector search is off in this build.** The semantic search over letters needs a Vector Search endpoint and
index over `complaint_documents`, which this deployment does not create.

---

## Corrections to claims made elsewhere

- The grader enforces **grid AND prose for scalar answers only**. Set and top-k cases can pass on the result
  grid alone. Earlier wording implied both were required everywhere.
- The governance suite is **23 assertions** by default and 26 only with `--with-genie`.
- `assert_not_blinded()` now runs on every evaluation. Before the audit it ran only in the voice lane and
  the governance panel, despite documentation saying otherwise.
