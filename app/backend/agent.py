"""The supervisor — route to the three Genie Agents, fuse one governed answer.

This is a faithful, self-contained reproduction of an Agent Bricks Multi-Agent Supervisor over three
real Genie Agents. The per-domain `ROUTING_DESCRIPTION` lines below ARE the "description" field you
fill in for each subagent when registering them with a native MAS, so the routing behaviour you tune
here is the routing behaviour you get there.

Two things here are NOT in the workshop scaffold this was forked from, and both are required by the
measured behaviour of these particular Genie Agents:

  1. THE LEGS RUN IN PARALLEL. A reasoning answer from these agents measured 15-36s. Three legs in
     sequence is 45-108s against a Databricks Apps HTTP timeout of 120s — a coin flip on a
     three-domain question. In parallel the turn costs one leg, not three.

  2. THE 5 QPM API QUOTA IS TREATED AS A FIRST-CLASS FAILURE MODE. Genie's Conversation API allows
     ~5 messages/minute shared across the whole workspace. A three-leg question spends three of
     them, so two people demoing at once will hit HTTP 429. A throttled leg reports itself as
     throttled and the answer says which domain is missing, rather than silently returning a
     confident answer built on two thirds of the evidence.
"""
from __future__ import annotations

import collections
import concurrent.futures
import datetime
import json
import os
import re
import threading
import time
import uuid

import config
import databricks_client as dbx
import lakebase as lb
import text2sql
import tracing

# ---------------------------------------------------------------------------
# The three domains
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
GENIE_PATHS = {
    "COLLECTIONS": os.path.join(_HERE, "collections_space.md"),
    "GRIEVANCE": os.path.join(_HERE, "grievance_space.md"),
    "RM": os.path.join(_HERE, "rm_space.md"),
}
SPACE_IDS = config.SPACE_IDS

# >>> THE LAYER YOU TWEAK <<< — one line per registered subagent. Editing these re-routes the
# supervisor without touching a line of control flow.
ROUTING_DESCRIPTION = {
    "COLLECTIONS": "Loan delinquency and recovery: DPD buckets (SMA0/SMA1/SMA2/NPA), roll-forward "
    "and roll-back rates, GNPA, overdue and outstanding principal, collection efficiency, recovery "
    "agent activity and conduct, promise-to-pay. Use for any question about which book is going bad, "
    "why delinquency moved, or how recovery is performing.",
    "GRIEVANCE": "Customer complaints and service quality: complaint volumes by category, SLA "
    "breaches and turnaround time, escalations to the Banking Ombudsman, repeat complainants, UPI "
    "and card disputes, chargebacks. Use for questions about customer harm, service failure, "
    "regulatory complaint exposure, or dispute load.",
    "RM": "Relationship-manager performance and pay: targets versus attainment, CASA and loan "
    "volume, product mix quality, incentive earned, quality-gate failures and clawback, customer "
    "portfolio composition and cross-sell gaps. Use for questions about who is performing, who is "
    "being paid what, and whether the payout matches portfolio quality.",
}

# Terms each domain actually owns. Used to reframe a question into a domain's own language so its
# Genie Agent answers it instead of declining it as out of scope — a real behaviour of these agents,
# whose instruction blocks explicitly tell them to refuse other domains' questions.
_DOMAIN_VOCABULARY = {
    "COLLECTIONS": "DPD buckets, roll-forward rate, GNPA, overdue amount, outstanding principal, "
    "collection efficiency, recovery agent activity, promise-to-pay",
    "GRIEVANCE": "complaint volume by category, SLA breach rate, days to resolve, ombudsman "
    "escalations, repeat complainants, UPI disputes, chargebacks",
    "RM": "attainment percentage, CASA and loan volume, product mix score, incentive earned, "
    "quality gate, clawback, portfolio value, cross-sell gap",
}

_THROTTLE_MARKERS = ("429", "too many requests", "rate limit", "quota", "resource_exhausted")


class GenieThrottled(RuntimeError):
    """Genie refused the call, or would have, because the workspace message quota is exhausted."""


class _RollingRateLimiter:
    """Admission control over a rolling window — MESSAGES PER MINUTE, not concurrent calls.

    A semaphore was the obvious thing to reach for and it is the wrong tool: capping three
    simultaneous calls does nothing to stop six calls starting inside the same minute, which is
    exactly what two overlapping three-domain questions do. Genie's quota is a rate, so the control
    has to be a rate: keep the start timestamps of recent admissions and refuse (or wait) when the
    window is full.

    `acquire` blocks until a slot frees or the deadline passes, so a throttled leg surfaces as an
    honest "quota exhausted" instead of an opaque HTTP 429 from the far side.
    """

    def __init__(self, per_minute: int, window: float = 60.0) -> None:
        self.capacity = max(1, per_minute)
        self.window = window
        self._starts: collections.deque[float] = collections.deque()
        # Cumulative admissions since this process started. The window occupancy is the control, but it
        # is a 60s window and a three-domain question takes 40 to 65 seconds, so by the time an answer is
        # on screen its Genie calls have usually aged out and the occupancy is legitimately zero. Showing
        # only that made the quota badge look broken after a question that plainly spent quota.
        self._total = 0
        self._lock = threading.Lock()
        self._free = threading.Condition(self._lock)

    def acquire(self, deadline: float) -> bool:
        with self._free:
            while True:
                now = time.monotonic()
                while self._starts and now - self._starts[0] >= self.window:
                    self._starts.popleft()
                if len(self._starts) < self.capacity:
                    self._starts.append(now)
                    self._total += 1
                    return True
                # Wait only until the oldest admission ages out, or the turn's deadline.
                wait_until = self._starts[0] + self.window
                remaining = min(wait_until, deadline) - now
                if remaining <= 0:
                    return False
                self._free.wait(timeout=remaining)

    def snapshot(self) -> dict:
        """Current window occupancy — surfaced in /api/health so the quota is visible, not guessed."""
        with self._lock:
            now = time.monotonic()
            recent = [t for t in self._starts if now - t < self.window]
            return {"used_in_window": len(recent), "capacity": self.capacity,
                    "window_seconds": int(self.window), "sent_total": self._total}


_GENIE_RATE = _RollingRateLimiter(config.GENIE_MESSAGES_PER_MINUTE)


def _user_genie_client(user_token: str | None):
    """A WorkspaceClient bound to the END USER's forwarded token, so Genie reads execute under the
    caller's identity and Unity Catalog row filters and column masks apply per person.

    Falls back to the app service principal only when no token is present (local dev). In Apps this
    fallback must never be the live path: without a user token the app reads as itself and every user
    sees every region, which is precisely the governance bypass this design exists to prevent.
    """
    if not user_token:
        if config.REQUIRE_OBO:
            raise PermissionError(
                "no forwarded user token on this request. Refusing to read as the app service "
                "principal, which would return every region's data to a caller entitled to one. "
                "Set REQUIRE_OBO=false only for local development.")
        return dbx.client()
    from databricks.sdk import WorkspaceClient
    # auth_type='pat' forces token-only auth so the app SP's OAuth env does not collide with the
    # forwarded user token ("more than one authorization method configured").
    return WorkspaceClient(host=dbx.client().config.host, token=user_token, auth_type="pat")


def _is_throttle(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in _THROTTLE_MARKERS)


# ---------------------------------------------------------------------------
# One Genie leg — ask a real Genie Agent, return its SQL and rows
# ---------------------------------------------------------------------------
def _genie_leg(space_id: str, question: str, w=None, deadline: float | None = None) -> dict:
    """Ask a real Genie Agent via the Conversation API. Genie writes the SQL and runs it under `w`'s
    identity, so the rows that come back are already row-filtered and column-masked for that user.

    Returns {sql, rows, columns, row_count, description}. `description` is Genie's own narrative,
    which is worth keeping: it is the text that proves masking reached the prose layer, not just the
    result grid.
    """
    w = w or dbx.client()
    deadline = deadline if deadline is not None else time.monotonic() + config.TURN_BUDGET_SECONDS

    if not _GENIE_RATE.acquire(deadline):
        raise GenieThrottled(
            f"workspace Genie budget of {config.GENIE_MESSAGES_PER_MINUTE} messages/minute is fully "
            "committed and this turn ran out of time waiting for a slot")

    remaining = deadline - time.monotonic()
    if remaining <= 1:
        raise GenieThrottled("turn budget exhausted before this domain could be asked")
    try:
        # The SDK default is a TWENTY MINUTE wait. Left unset, a slow Genie call keeps a worker and a
        # quota slot alive long after Apps has already given up on the HTTP request at 120s.
        msg = w.genie.start_conversation_and_wait(
            space_id=space_id, content=question,
            timeout=datetime.timedelta(seconds=remaining))
    except Exception as e:
        if _is_throttle(e):
            raise GenieThrottled(str(e)[:200]) from e
        raise

    sql, rows, cols, description = "", [], [], ""
    for att in (msg.attachments or []):
        # A Genie message carries text attachments (the narrative) and query attachments (SQL +
        # results). Keep both: the narrative is the governed answer the user reads.
        text_att = getattr(att, "text", None)
        if text_att is not None and getattr(text_att, "content", None):
            description = text_att.content
        if getattr(att, "query", None) is None:
            continue
        sql = att.query.query or sql
        if getattr(att.query, "description", None):
            description = description or att.query.description
        att_id = getattr(att, "attachment_id", None)
        res, fetch_errors = None, []
        # The result-fetch method name has moved across SDK versions; try each shape.
        for getter in (
            lambda: w.genie.get_message_attachment_query_result(
                space_id=space_id, conversation_id=msg.conversation_id,
                message_id=msg.id, attachment_id=att_id),
            lambda: w.genie.get_message_query_result_by_attachment(
                space_id=space_id, conversation_id=msg.conversation_id,
                message_id=msg.id, attachment_id=att_id),
            lambda: w.genie.get_message_query_result(
                space_id=space_id, conversation_id=msg.conversation_id, message_id=msg.id),
        ):
            try:
                res = getter()
                break
            except Exception as fetch_exc:
                fetch_errors.append(f"{type(fetch_exc).__name__}: {fetch_exc}"[:160])
                continue
        if res is None:
            # Genie WROTE the query but we could not read its results — a 403 on the result endpoint,
            # a 429, a timeout. Swallowing this returned "0 rows, no error", which the fuser then
            # reported as a confident complete answer over an empty domain. Fail loudly instead.
            raise RuntimeError(
                "Genie produced a query but its results could not be retrieved: "
                + " | ".join(fetch_errors[-2:]))
        sr = getattr(res, "statement_response", None)
        if sr and getattr(sr, "result", None) and sr.result.data_array:
            cols = [c.name for c in sr.manifest.schema.columns]
            rows = [dict(zip(cols, r)) for r in sr.result.data_array]
    return {"sql": sql, "rows": rows, "columns": cols, "row_count": len(rows),
            "description": description}


def call_leg(domain: str, question: str, genie_w=None, deadline: float | None = None) -> dict:
    """One domain subagent. Returns a structured leg result; a failing leg degrades, never sinks the
    turn, and always says HOW it degraded so the fused answer can disclose it.

    The whole body runs inside one trace span so the span's duration is the real cost of the leg and
    every exit path — throttled, timed out, errored, fallback, success — is recorded rather than only
    the happy one.
    """
    started = time.time()
    deadline = deadline if deadline is not None else time.monotonic() + config.TURN_BUDGET_SECONDS
    space_id = SPACE_IDS.get(domain, "")

    with tracing.span(f"genie:{domain.lower()}", span_type="RETRIEVER",
                      domain=domain, question=question, space_id=space_id) as leg_span:

        def done(result: dict) -> dict:
            # The SQL and the ROW COUNT go into the trace; the rows themselves never do. Row data is
            # row-filtered and column-masked for the person who asked, and a trace is read by other
            # people — copying their masked view into a shared trace would quietly undo the masking.
            tracing.set_outputs(leg_span, {
                "via": result["via"], "sql": result["sql"], "row_count": result["row_count"],
                "elapsed_ms": result["elapsed_ms"], "error": result["error"]})
            return result

        def failure(via: str, error: str) -> dict:
            return done({"domain": domain, "via": via, "sql": "", "rows": [], "columns": [],
                         "row_count": 0, "description": "", "error": error, "narrative_defect": None,
                         "elapsed_ms": int((time.time() - started) * 1000)})

        via, res, error = None, None, None

        if space_id:
            try:
                res, via = _genie_leg(space_id, question, w=genie_w, deadline=deadline), "genie_agent"
            except GenieThrottled as e:
                # Do NOT silently fall back to text2sql. A throttled leg means the workspace quota is
                # exhausted; the honest answer names the gap instead of hiding it behind a weaker lane.
                return failure("throttled",
                               f"Genie message quota exhausted (workspace limit): {e}")
            except Exception as e:
                error, res, via = str(e)[:300], None, None

        if res is None and time.monotonic() >= deadline - 5:
            # No time left to attempt the fallback. Say so rather than starting a job whose answer
            # would arrive after Apps has already cut the HTTP request.
            return failure("timeout",
                           f"turn budget of {config.TURN_BUDGET_SECONDS}s exhausted"
                           + (f"; last error: {error}" if error else ""))

        if res is None:
            # Fallback lane: instruction-driven text2sql over the same space definition. Keeps the
            # domain answerable during a Genie outage, at the cost of Genie's own reasoning.
            # genie_w is threaded through so this executes under the SAME identity as the Genie lane;
            # without it a Genie error would silently promote the read to the app service principal
            # and return rows the caller is not entitled to see.
            try:
                res = text2sql.ask(question, genie_instructions_path=GENIE_PATHS[domain], w=genie_w)
                via = "text2sql_fallback"
            except Exception as e:
                return failure("error", f"{error + ' | ' if error else ''}{str(e)[:300]}")

        return done({
            "domain": domain, "via": via, "sql": res.get("sql", ""),
            "rows": res["rows"][:50], "columns": res["columns"], "row_count": res["row_count"],
            "description": res.get("description", ""), "error": error,
            # Recorded per leg so the fuser can refuse to lean on an unusable narrative and the UI can
            # tell the operator why the wording looks thin. Never silently swallowed.
            "narrative_defect": narrative_defect(res["rows"], res.get("description", "")),
            "elapsed_ms": int((time.time() - started) * 1000),
        })


# ---------------------------------------------------------------------------
# NARRATIVE COMPLETENESS
# ---------------------------------------------------------------------------
_NARR_NUM = re.compile(r"(?<![\w.-])-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?![\w-])|(?<![\w.-])-?\d+(?:\.\d+)?(?![\w-])")


def narrative_defect(rows: list[dict], narrative: str) -> str | None:
    """Detect a Genie reply whose SQL answered the question but whose PROSE did not.

    This is a real, repeating failure mode, not a hypothetical. Genie sometimes computes the right
    figure into the result grid and then replies with only a clarifying question — "would you prefer to
    see this by card type?" — never stating the number. The grid is not what a person reads, so that is
    a non-answer wearing a correct answer's clothes.

    It was first found by the benchmark, "fixed" by adding an answer-first rule to all three space
    instruction blocks, and then it happened AGAIN on a held-out question. That is the finding worth
    keeping: a prompt-level rule is guidance, not enforcement. Detecting it in code is enforcement.

    Returns a short reason string when the narrative is unusable, else None.
    """
    text = (narrative or "").strip()
    if not text:
        return "the domain agent returned no narrative at all"
    if not rows:
        return None                     # nothing to have failed to state
    nums_in_text = {m.group(0).replace(",", "") for m in _NARR_NUM.finditer(text)}
    has_numeric_cell = False
    for r in rows:
        for v in r.values():
            if isinstance(v, bool) or v is None:
                continue
            try:
                float(str(v).replace(",", "").rstrip("%"))
            except (TypeError, ValueError):
                continue
            has_numeric_cell = True
            break
        if has_numeric_cell:
            break
    if not has_numeric_cell:
        return None                     # a purely categorical answer needs no figure
    if not nums_in_text:
        # Ends in a question mark and quotes nothing: the clarifying-question failure exactly.
        if text.endswith("?"):
            return ("the domain agent asked a clarifying question instead of stating its result; the "
                    "figure below comes from its own query")
        return "the domain agent's narrative states no figure, though its query returned one"
    return None


# ---------------------------------------------------------------------------
# ROUTER
# ---------------------------------------------------------------------------
def _strip_json(raw: str) -> str:
    t = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", t, re.DOTALL | re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    return t.strip()


def _build_router_prompt(question: str, descriptions: dict) -> str:
    lines = "\n".join(f"- {d}: {desc}" for d, desc in descriptions.items())
    return (
        "You are the routing controller for an Indian retail bank's Multi-Agent Supervisor. "
        "Registered domain subagents:\n"
        f"{lines}\n\n"
        "Decide which subagent(s) are needed to fully answer the user's question. A cross-domain "
        "'why' question usually needs more than one: a collections problem often shows up as a "
        "complaint spike, and an incentive problem often shows up as portfolio quality.\n"
        "For EACH chosen domain write a focused subquestion phrased ENTIRELY in that domain's own "
        "terms, because each agent is instructed to decline questions belonging to another domain.\n"
        "Choose the FEWEST domains that genuinely answer the question — every extra domain spends "
        "one of the workspace's limited Genie messages.\n"
        "Output ONLY a JSON object, no prose:\n"
        '{"domains": ["COLLECTIONS"|"GRIEVANCE"|"RM", ...], '
        '"reasons": {"COLLECTIONS": "<why this domain>", ...}, '
        '"subquestions": {"COLLECTIONS": "<domain-specific question>", ...}}\n\n'
        f"Question: {question}"
    )


def _reframe_subquestion(question: str, domain: str) -> str:
    """Rewrite the user's question into one domain's vocabulary so its agent answers rather than
    declines. Only called when the router failed to supply a subquestion for a chosen domain."""
    raw = dbx.chat(
        messages=[{"role": "user", "content": (
            f'The user asked: "{question}"\n\n'
            f"Rewrite it as a focused data question for a bank's {domain} analytics agent, which "
            f"covers ONLY: {_DOMAIN_VOCABULARY[domain]}. Keep the same subject and scope (the same "
            "product, region, branch and time period) but ask only for this domain's own metrics. "
            "Output ONLY the rewritten question, one line, no preamble."
        )}],
        max_tokens=160,
    )
    return raw.strip().strip('"')


def route(question: str, descriptions: dict | None = None) -> dict:
    """NL question -> {domains, reasons, subquestions}."""
    descriptions = descriptions or ROUTING_DESCRIPTION
    with tracing.span("router", span_type="LLM", question=question,
                      registered_domains=list(descriptions)) as router_span:
        raw = dbx.chat(
            messages=[{"role": "user", "content": _build_router_prompt(question, descriptions)}],
            max_tokens=900,
        )
        decision = _parse_routing(raw, question)
        # The routing decision is the single most useful thing in the trace: it is the answer to
        # "why did it look there?", which is the first question anyone asks about a wrong answer.
        tracing.set_outputs(router_span, {"domains": decision["domains"],
                                          "reasons": decision.get("reasons"),
                                          "fallback": bool(decision.get("router_fallback"))})
    return decision


def _parse_routing(raw: str, question: str) -> dict:
    """Coerce the router's reply into a usable decision. Separated from route() so the span above
    stays readable and this logic is unit-testable without an LLM call."""
    try:
        decision = json.loads(_strip_json(raw))
    except Exception:
        # Router parse failure: consult COLLECTIONS only rather than spending three Genie messages on
        # a guess. Consulting all three would be the expensive wrong default under a 5 QPM quota.
        decision = {"domains": ["COLLECTIONS"], "reasons": {},
                    "subquestions": {}, "router_fallback": True}

    # The model returns JSON, which is not the same as returning the SHAPE we asked for. A reply with
    # "reasons": [] parses fine and then raises .get on a list several seconds and three Genie
    # messages later, after all the expensive work is done. Coerce every field here, once.
    raw_domains = decision.get("domains")
    if not isinstance(raw_domains, list):
        raw_domains = []
    # Dedupe while preserving order, keep only known domains, and hard-cap the count. An unbounded
    # list (or a repeated one) would spawn a thread and spend a Genie message per entry, and the
    # completion dict is keyed by domain so duplicates also silently overwrite each other's results.
    domains: list[str] = []
    for d in raw_domains:
        if isinstance(d, str) and d in GENIE_PATHS and d not in domains:
            domains.append(d)
    decision["domains"] = domains[:config.MAX_DOMAINS_PER_TURN] or ["COLLECTIONS"]

    reasons = decision.get("reasons")
    decision["reasons"] = reasons if isinstance(reasons, dict) else {}

    subqs = decision.get("subquestions")
    subqs = dict(subqs) if isinstance(subqs, dict) else {}
    for d in decision["domains"]:
        value = subqs.get(d)
        if not isinstance(value, str) or not value.strip():
            subqs[d] = _reframe_subquestion(question, d)
    decision["subquestions"] = subqs
    return decision


# ---------------------------------------------------------------------------
# FUSER
# ---------------------------------------------------------------------------
_ACTION_TYPES = (
    "schedule_field_visit", "assign_recovery_agency", "record_ptp", "offer_settlement",
    "escalate_to_ombudsman", "issue_provisional_credit", "waive_fee",
    "dispatch_customer_letter", "hold_incentive_payout", "open_coaching_case",
)


def fuse(question: str, decision: dict, legs: list[dict]) -> dict:
    evidence = json.dumps(
        {lr["domain"]: {"sql": lr["sql"], "rows": lr["rows"],
                        "genie_narrative": lr.get("description", ""), "error": lr["error"]}
         for lr in legs},
        default=str,
    )
    missing = [lr["domain"] for lr in legs if lr["via"] in ("throttled", "error")]
    thin = {lr["domain"]: lr["narrative_defect"] for lr in legs if lr.get("narrative_defect")}
    prompt = (
        "You are the Multi-Agent Supervisor for an Indian retail bank's control tower. You consulted "
        "these domain subagents and received governed data. All figures are INR and all data is "
        "synthetic.\n"
        f"Routing decision: {json.dumps(decision)}\n"
        f"Retrieved evidence per domain (JSON): {evidence}\n\n"
        "Fuse ONE answer using ONLY the numbers above. Never invent a figure. If several domains "
        "contributed, CONNECT them into one causal story rather than listing them side by side. "
        "Then propose ONE concrete next action a bank officer could take.\n"
        + (f"IMPORTANT: these domains returned no data and you must say so explicitly in the answer, "
           f"naming them: {missing}. Do not present a complete-sounding answer built on the rest.\n"
           if missing else "")
        + (f"IMPORTANT: for these domains the subagent's own narrative did not state its result "
           f"({json.dumps(thin)}). Read the figures out of that domain's `rows` yourself and state them "
           "plainly. Do NOT repeat a clarifying question back to the user, and do not treat the domain "
           "as having failed — its query succeeded.\n" if thin else "")
        + "Row-level security is active, so the figures are what THIS user is entitled to see; do "
        "not describe them as bank-wide totals.\n"
        "Then draft that action so a bank officer can review and approve it. The draft is a PROPOSAL "
        "only: it is checked against the bank's controls and needs a named human approver before "
        "anything happens, so propose the action the evidence supports and do not soften it.\n"
        "`subject` must be the real identifier the action is about, taken from the rows above — a "
        "loan_account_id for collections, a complaint_id for grievance, an rm_id for RM. Put the same "
        "identifier in payload under its proper key, and include amount_inr where money is involved.\n"
        "Output ONLY a JSON object, no prose, no markdown fences:\n"
        '{"answer": "<=200 words", "recommended_action": "<one concrete next step>", '
        f'"proposed_action_type": "<one of {"|".join(_ACTION_TYPES)}|none>", '
        '"action_draft": {"subject": "<identifier>", "region": "<North|South|East|West|Central>", '
        '"payload": {"loan_account_id|complaint_id|rm_id": "<id>", "amount_inr": <number or null>, '
        '"agent_id": "<recovery agent id if a field action>", "note": "<one line of justification>"}}}\n\n'
        f"User question: {question}"
    )
    with tracing.span("fuser", span_type="LLM", question=question,
                      domains=[lr["domain"] for lr in legs],
                      rows_per_domain={lr["domain"]: lr["row_count"] for lr in legs},
                      domains_missing=missing) as fuse_span:
        raw = dbx.chat(messages=[{"role": "user", "content": prompt}], max_tokens=1200)
        result = _parse_fusion(raw)
        tracing.set_outputs(fuse_span, result)
    return result


def _parse_fusion(raw: str) -> dict:
    """Coerce the fuser's reply. Separate function so the span stays readable and this is testable."""
    try:
        parsed = json.loads(_strip_json(raw))
        proposed = (parsed.get("proposed_action_type") or "none").strip()
        # Never let the model invent an action type that has no policy row. The guardrails would
        # refuse an unknown type anyway, but dropping it here keeps the UI from offering a button
        # that cannot possibly work.
        if proposed not in _ACTION_TYPES:
            proposed = "none"

        draft = parsed.get("action_draft")
        draft = dict(draft) if isinstance(draft, dict) else {}
        payload = draft.get("payload")
        payload = dict(payload) if isinstance(payload, dict) else {}
        region = draft.get("region")
        action_draft = None
        if proposed != "none" and draft.get("subject"):
            action_draft = {
                "action_type": proposed,
                "subject": str(draft["subject"]),
                "region": region if region in config.REGIONS else None,
                "payload": payload,
                # The model never chooses the autonomy rung; policy does. Proposing at L2 means
                # "needs a human", which is the only honest default for a model-drafted action.
                "level": 2,
            }
        return {
            "answer": (parsed.get("answer") or "").strip(),
            "recommended_action": (parsed.get("recommended_action") or "").strip(),
            "proposed_action_type": proposed,
            "action_draft": action_draft,
        }
    except Exception:
        return {"answer": raw.strip(), "recommended_action": "",
                "proposed_action_type": "none", "action_draft": None}


# ---------------------------------------------------------------------------
# SUPERVISE — one full turn
# ---------------------------------------------------------------------------
def ask(question: str, user_token: str | None = None, user_email: str | None = None) -> dict:
    """Full supervisor turn: route -> call the chosen Genie Agents in parallel -> fuse -> persist.

    `user_token` is the end user's forwarded access token. When present every Genie read executes as
    that user, so what comes back is already filtered and masked by Unity Catalog.
    """
    started = time.time()
    # ONE deadline for the whole turn, shared by the router, every leg and the fuser. Apps cuts the
    # HTTP request at 120s; without a shared budget the handler and its worker threads keep running
    # and keep spending Genie quota on an answer that can no longer be delivered.
    deadline = time.monotonic() + config.TURN_BUDGET_SECONDS

    with tracing.span("supervisor_turn", span_type="AGENT", question=question,
                      user=user_email or "unknown", obo=bool(user_token)) as turn_span:
        result = _turn(question, deadline, user_token, user_email)
        tracing.set_outputs(turn_span, {k: result.get(k) for k in
                                        ("answer", "recommended_action", "proposed_action_type",
                                         "latency_ms")})
    return result


def _turn(question: str, deadline: float, user_token: str | None,
          user_email: str | None) -> dict:
    """The turn body. Split out so the enclosing span covers everything including persistence."""
    started = time.time()
    genie_w = _user_genie_client(user_token)

    decision = route(question)
    domains = decision["domains"]

    # Parallel legs — see the module docstring. The semaphore inside _genie_leg is what actually
    # protects the workspace message quota; the pool just stops the wall clock from adding up.
    if len(domains) == 1:
        legs = [call_leg(domains[0], decision["subquestions"][domains[0]],
                         genie_w=genie_w, deadline=deadline)]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(domains)) as pool:
            futures = {pool.submit(call_leg, d, decision["subquestions"][d], genie_w, deadline): d
                       for d in domains}
            done = {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}
        # Preserve the router's domain order regardless of completion order. `domains` is deduplicated
        # in route(), so this cannot repeat or drop a leg.
        legs = [done[d] for d in domains]

    fused = fuse(question, decision, legs)
    latency_ms = int((time.time() - started) * 1000)

    session_uuid = str(uuid.uuid4())
    # Captured INSIDE the trace so it is the id of this turn, and written onto the session row so an
    # action proposed from this answer can be walked back to the evidence that produced it.
    trace_id = tracing.current_trace_id()
    session_id = _persist_session(session_uuid, question, domains, fused["answer"],
                                  user_email=user_email, latency_ms=latency_ms,
                                  trace_id=trace_id)

    return {
        "session_id": session_id,
        "session_uuid": session_uuid,
        "question": question,
        "latency_ms": latency_ms,
        "routing": [{"domain": d, "reason": decision["reasons"].get(d, "selected by router")}
                    for d in domains],
        "router_fallback": bool(decision.get("router_fallback")),
        "legs": legs,
        "trace_id": trace_id,
        "answer": fused["answer"],
        "recommended_action": fused["recommended_action"],
        "proposed_action_type": fused["proposed_action_type"],
        # A draft, not a decision. The UI shows it with its guardrail verdict and a named human has
        # to approve it before anything reaches a bank system.
        "action_draft": fused.get("action_draft"),
        "data_is_synthetic": config.DATA_IS_SYNTHETIC,
    }


# ---------------------------------------------------------------------------
# Lakebase — session memory and feedback
# ---------------------------------------------------------------------------
def _persist_session(session_uuid: str, question: str, domains: list[str], answer: str,
                     user_email: str | None = None, latency_ms: int | None = None,
                     trace_id: str | None = None) -> int | None:
    """Log the turn. A logging failure must not sink a good answer, so this degrades to None."""
    try:
        row = lb.execute(
            """INSERT INTO agent_sessions
                 (session_uuid, user_email, question, routed_domains, fused_answer,
                  latency_ms, trace_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING session_id""",
            (session_uuid, user_email or dbx.current_user(), question,
             ",".join(domains), answer, latency_ms, trace_id),
            returning=True,
        )
        return row["session_id"]
    except Exception:
        return None


def record_feedback(session_uuid: str, rating: int, note: str | None = None,
                    user_email: str | None = None) -> dict:
    row = lb.execute(
        """INSERT INTO agent_feedback (session_uuid, user_email, rating, comment)
           VALUES (%s, %s, %s, %s) RETURNING feedback_id, created_at""",
        (session_uuid, user_email or dbx.current_user(), rating, note),
        returning=True,
    )
    return {"feedback_id": row["feedback_id"], "created_at": str(row["created_at"])}
