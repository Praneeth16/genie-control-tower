"""Guardrail engine — the controls that run BEFORE an action touches the world.

`evaluate(action)` scores one proposed action against its row in `action_policies` and returns a
structured verdict. It mutates nothing: the caller (the API, or the executor's final gate) decides
whether to escalate.

Three properties make this different from asking a model to behave.

1. THE CONTROLS ARE GROUNDED IN GOVERNED DATA, NOT IN THE PAYLOAD.
   A model can put anything in a payload, including `"agent_certified": true`. So the checks that
   matter do not read the payload at all — they call Unity Catalog functions over the bank's own
   tables (`agent_conduct_status`, `has_open_grievance`, `account_dpd_days`, `contacts_on_date`).
   Every check reports `verified_by`, so the UI can show how many controls were confirmed against the
   catalog versus taken on trust from the request. That ratio is the honest measure of how much of
   this is real.

2. IT FAILS CLOSED.
   If the verification query errors — warehouse down, EXECUTE revoked, a control renamed — that is a
   BREACH, not a skipped check. A control that reports "passed" when it could not run is worse than
   no control, because it manufactures an audit trail saying the action was cleared.

3. IT RUNS AS THE GUARDRAIL IDENTITY, NOT THE CALLER.
   Unity Catalog SQL functions execute with the invoker's permissions, and the row filters in
   policies.sql apply. If these checks ran on behalf of the requesting user, a recovery agent's
   missing certification would become invisible to anyone scoped to another region, and the control
   would pass for the wrong reason. So `evaluate` deliberately uses the app service principal, which
   is entitled to the whole book and holds SELECT only. `assert_not_blinded()` proves that on EVERY
   evaluation — see Gate 0 in evaluate(). Proving it once at startup would only show it was true once.

One batched round trip: all applicable data checks go in a single SELECT. Five separate statements
would add five warehouse round trips to every approval click.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

import databricks_client as dbx
import lakebase

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Full row counts of the tables the controls read. assert_not_blinded() compares the guardrail
# identity's visible counts against these: anything lower means a row filter is hiding part of the book
# from the control.
#
# These are LOADED FROM A MANIFEST the data generator writes, not typed in here. They were hand-copied
# once, and that is a landmine: regenerate or reload the data and the control sees a different number
# from its hardcoded constant, concludes it is being row-filtered, and FAILS CLOSED — correct behaviour
# for the check, but the app then refuses all traffic and it presents as a security incident rather than
# a stale literal. The manifest makes the two impossible to desync.
#
# The fallback values are the counts as of the 2026-09-03 rebuild, so a missing manifest degrades to the
# old behaviour rather than disabling the control — an absent file must never mean "assume unblinded".
_FALLBACK_VISIBILITY = {
    "recovery_agents": 60,
    "complaints": 9660,
    "delinquency_monthly": 108000,
    "collections_activity": 63267,
}


def _load_expected_visibility() -> tuple[dict[str, int], str]:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "row_counts.json")
    try:
        with open(path) as fh:
            counts = json.load(fh)
        # Every expected table must be present. A manifest missing a key would otherwise silently drop
        # that table's check, which is a blinding the blinding-detector cannot see.
        missing = [k for k in _FALLBACK_VISIBILITY if k not in counts]
        if missing:
            raise ValueError(f"manifest is missing {missing}")
        return ({k: int(counts[k]) for k in _FALLBACK_VISIBILITY},
                f"manifest {os.path.basename(path)}")
    except Exception:
        return dict(_FALLBACK_VISIBILITY), "built-in fallback (row_counts.json not found)"


EXPECTED_VISIBILITY, EXPECTED_VISIBILITY_SOURCE = _load_expected_visibility()


class GuardrailsBlinded(RuntimeError):
    """The guardrail identity cannot see the whole book, so its verdicts cannot be trusted."""


def _payload(action: dict[str, Any]) -> dict[str, Any]:
    raw = action.get("payload")
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw) if isinstance(raw, dict) else {}


def _policy(action_type: str) -> dict[str, Any] | None:
    rows = lakebase.query(
        "SELECT * FROM action_policies WHERE action_type = %s", (action_type,))
    return rows[0] if rows else None


def _scheduled_epoch(action: dict[str, Any], payload: dict[str, Any]) -> tuple[int, str]:
    """The instant the action would take effect, as epoch seconds, plus a human rendering in IST.

    Order of preference: the first-class `scheduled_at` column, then a `scheduled_at` in the payload,
    then now. "Now" is the right default: an action with no stated time is an immediate dispatch, and
    an immediate dispatch at 22:00 must be refused exactly like a scheduled one.
    """
    value = action.get("scheduled_at") or payload.get("scheduled_at")
    when: dt.datetime
    if isinstance(value, dt.datetime):
        when = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            when = dt.datetime.fromisoformat(text)
        except ValueError:
            when = dt.datetime.now(dt.timezone.utc)
    else:
        when = dt.datetime.now(dt.timezone.utc)
    if when.tzinfo is None:
        # A naive timestamp from a bank's own scheduler is local wall-clock time, i.e. IST. Assuming
        # UTC here would shift every check by 5h30m and silently permit evening contact.
        when = when.replace(tzinfo=IST)
    return int(when.timestamp()), when.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def _check(rule: str, *, applicable: bool, passed: bool, detail: str,
           limit: Any = None, value: Any = None, verified_by: str = "payload",
           legal_basis: str | None = None) -> dict[str, Any]:
    return {"rule": rule, "applicable": applicable, "passed": passed, "limit": limit,
            "value": value, "detail": detail, "verified_by": verified_by,
            "legal_basis": legal_basis}


# ---------------------------------------------------------------------------
# Startup assertion
# ---------------------------------------------------------------------------
def assert_not_blinded(w=None) -> dict[str, Any]:
    """Confirm the guardrail identity sees the whole book. Raises GuardrailsBlinded if not.

    Called at startup and exposed on /api/health. This is the check that stops the most dangerous
    failure in the whole design: a row filter quietly narrowing what the CONTROL can see, so that
    every action comes back compliant because the evidence against it was filtered out.
    """
    res = dbx.run_sql("SELECT guardrail_visibility() AS v", w=w)
    raw = res["rows"][0]["v"]
    seen = json.loads(raw) if isinstance(raw, str) else dict(raw)
    seen = {k: int(v) for k, v in seen.items()}
    short = {k: (seen.get(k, 0), n) for k, n in EXPECTED_VISIBILITY.items() if seen.get(k, 0) < n}
    if short:
        raise GuardrailsBlinded(
            "the guardrail identity is being row-filtered and cannot see the data it must check: "
            + "; ".join(f"{k}: sees {got} of {want}" for k, (got, want) in short.items())
            + ". Grant it an unrestricted region_entitlement before serving traffic — a blinded "
              "control reports every action compliant.")
    return {"visible": seen, "expected": EXPECTED_VISIBILITY, "blinded": False,
            "expected_source": EXPECTED_VISIBILITY_SOURCE}


# ---------------------------------------------------------------------------
# The kill switch
# ---------------------------------------------------------------------------
def actions_enabled() -> tuple[bool, str]:
    """Read the kill switch. Fails CLOSED: if the flag cannot be read, actions are off.

    An AI CoE that needs a redeploy to stop its agents does not control them, so stopping is a data
    change. And if we cannot confirm we are permitted to act, we are not permitted to act.
    """
    try:
        rows = lakebase.query(
            "SELECT enabled, reason FROM runtime_flags WHERE flag = 'actions_enabled'")
    except Exception as e:
        return False, f"kill switch state could not be read, so actions are disabled: {e}"
    if not rows:
        return False, "kill switch row 'actions_enabled' is missing, so actions are disabled"
    if not rows[0]["enabled"]:
        return False, f"actions are disabled by the kill switch: {rows[0].get('reason') or 'no reason given'}"
    return True, "actions enabled"


# ---------------------------------------------------------------------------
# Approver authorisation
# ---------------------------------------------------------------------------
def approver_roles(principal: str) -> list[str]:
    """The approval roles this person holds, from the role directory."""
    rows = lakebase.query(
        "SELECT role FROM approver_roles WHERE lower(principal) = lower(%s) ORDER BY role",
        (principal,))
    return [r["role"] for r in rows]


def authorise_approver(action: dict[str, Any], approver: str) -> tuple[bool, str]:
    """May `approver` approve this action? Returns (allowed, reason).

    Two independent conditions, both required:

      * SEPARATION OF DUTIES — the proposer may not approve their own proposal.
      * ROLE — the approver must hold the role `action_policies.approver_role` names.

    The role check is the one that is easy to skip and easy to fake. Without it the approval queue
    displays "requires HR Compensation" and then accepts a click from the RM's own line manager,
    which is precisely the conflict of interest the policy exists to prevent.

    Fails CLOSED: if the directory cannot be read, the approval is refused.
    """
    if action.get("requested_by") and action["requested_by"] == approver:
        return False, "separation of duties: you cannot approve an action you requested"

    policy = _policy(action.get("action_type"))
    if policy is None:
        return False, f"no policy for action_type '{action.get('action_type')}'"
    required = policy.get("approver_role")
    if not policy.get("requires_approval") or not required:
        return True, "this action type needs no named approver role"

    try:
        held = approver_roles(approver)
    except Exception as e:
        return False, f"approver role directory could not be read, so approval is refused: {e}"

    if required in held:
        return True, f"{approver} holds the {required} role"
    return False, (f"{approver} does not hold the '{required}' role required to approve "
                   f"{action.get('action_type')}"
                   + (f" (holds: {', '.join(held)})" if held else " (holds no approval roles)"))


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------
def evaluate(action: dict[str, Any], w=None) -> dict[str, Any]:
    """Score one action against its policy.

    Returns {"passed", "breaches", "checks", "policy", "verified_count", "payload_count"}.
    """
    action_type = action.get("action_type")
    region = action.get("region")
    payload = _payload(action)
    checks: list[dict[str, Any]] = []
    breaches: list[str] = []

    # --- Gate 0: is this control able to see the evidence at all? ------------
    #
    # This has to run HERE, per evaluation, and not only at startup or on a governance panel. It did not,
    # and that was the single largest hole in the design: every other check below asks "does the evidence
    # against this action exist?", and if the guardrail identity is being row-filtered the answer comes
    # back no for reasons that have nothing to do with the action. A blinded control does not fail — it
    # APPROVES, with a full set of green ticks. Checking it at startup proves only that it was unblinded
    # once; a grant can be revoked at any time afterwards.
    #
    # Fails CLOSED, and the breach names the blinding rather than the action.
    try:
        visibility = assert_not_blinded(w=None)   # never `w`: the caller must not verify their own control
        checks.append(_check("guardrail_integrity", applicable=True, passed=True,
                             detail=f"guardrail identity sees the whole book "
                                    f"({visibility.get('expected_source', 'unknown source')})",
                             verified_by="unity_catalog:guardrail_visibility"))
    except GuardrailsBlinded as e:
        checks.append(_check("guardrail_integrity", applicable=True, passed=False, detail=str(e)[:400],
                             verified_by="unity_catalog:guardrail_visibility"))
        breaches.append("the guardrail identity is row-filtered, so no verdict on this action can be "
                        "trusted; refusing rather than approving")
        return {"passed": False, "breaches": breaches, "checks": checks, "policy": None,
                "verified_count": 1, "payload_count": 0}
    except Exception as e:
        checks.append(_check("guardrail_integrity", applicable=True, passed=False,
                             detail=f"integrity check unavailable: {type(e).__name__}: {e}"[:400],
                             verified_by="unavailable"))
        breaches.append("the guardrail integrity check could not run; refusing rather than assuming it "
                        "would have passed")
        return {"passed": False, "breaches": breaches, "checks": checks, "policy": None,
                "verified_count": 1, "payload_count": 0}

    # --- Gate 1: the kill switch ---------------------------------------------
    enabled, why = actions_enabled()
    checks.append(_check("kill_switch", applicable=True, passed=enabled, detail=why,
                         verified_by="lakebase:runtime_flags"))
    if not enabled:
        breaches.append(why)
        return {"passed": False, "breaches": breaches, "checks": checks, "policy": None,
                "verified_count": 2, "payload_count": 0}

    # --- Gate 1: the action type must have a policy --------------------------
    policy = _policy(action_type)
    known = policy is not None
    checks.append(_check("action_type_allowed", applicable=True, passed=known,
                         value=action_type, verified_by="lakebase:action_policies",
                         detail="known action type" if known
                                else f"no policy exists for action_type '{action_type}', so it "
                                     "cannot be authorised"))
    if not known:
        breaches.append(f"action_type '{action_type}' is not allowed (no policy)")
        return {"passed": False, "breaches": breaches, "checks": checks, "policy": None,
                "verified_count": 2, "payload_count": 0}

    basis = policy.get("legal_basis")

    # --- Autonomy rung -------------------------------------------------------
    level = int(action.get("level") or 2)
    max_level = int(policy.get("max_autonomy_level") or 2)
    ok = level <= max_level
    checks.append(_check("autonomy_level", applicable=True, passed=ok, limit=max_level, value=level,
                         verified_by="lakebase:action_policies",
                         detail=f"requested autonomy L{level} against a ceiling of L{max_level} "
                                f"for this action type"))
    if not ok:
        breaches.append(f"autonomy L{level} exceeds the L{max_level} ceiling for {action_type}")

    # --- Value cap (INR) -----------------------------------------------------
    cap = policy.get("max_amount_inr")
    amount = next((v for v in (payload.get("amount_inr"), payload.get("amount")) if v is not None),
                  None)
    if cap is not None and amount is not None:
        try:
            amount_val = float(amount)
        except (TypeError, ValueError):
            checks.append(_check("max_amount_inr", applicable=True, passed=False, limit=float(cap),
                                 detail=f"amount {amount!r} is not a number, so the cap cannot be "
                                        "applied"))
            breaches.append(f"amount {amount!r} is not a valid number")
        else:
            ok = amount_val <= float(cap)
            checks.append(_check("max_amount_inr", applicable=True, passed=ok, limit=float(cap),
                                 value=amount_val, legal_basis=basis,
                                 detail=f"INR {amount_val:,.0f} against a cap of INR {float(cap):,.0f}"))
            if not ok:
                breaches.append(f"amount INR {amount_val:,.0f} exceeds the cap of INR {float(cap):,.0f}")
    elif cap is not None:
        # A capped action type with no amount is under-specified, not automatically fine.
        checks.append(_check("max_amount_inr", applicable=True, passed=False, limit=float(cap),
                             detail="this action type carries a value cap but the request states no "
                                    "amount, so the cap cannot be checked"))
        breaches.append(f"{action_type} requires an amount_inr to check against its cap")
    else:
        checks.append(_check("max_amount_inr", applicable=False, passed=True,
                             detail="no value cap configured for this action type"))

    # --- Region scope --------------------------------------------------------
    allowed = policy.get("allowed_regions")
    if allowed:
        ok = region in allowed
        checks.append(_check("allowed_regions", applicable=True, passed=ok, limit=list(allowed),
                             value=region, legal_basis=basis, verified_by="lakebase:action_policies",
                             detail=f"region '{region}' " + ("is in scope" if ok else
                                    f"is not in scope; this action is sanctioned only in "
                                    f"{', '.join(allowed)}")))
        if not ok:
            breaches.append(f"region '{region}' is outside the sanctioned regions {list(allowed)}")
    else:
        checks.append(_check("allowed_regions", applicable=False, passed=True, value=region,
                             detail="no regional restriction on this action type"))

    # --- The data-grounded conduct controls, in ONE round trip --------------
    checks.extend(_conduct_checks(action, policy, payload, basis, breaches, w=w))

    # --- Approval requirement (informational) -------------------------------
    needs_approval = bool(policy.get("requires_approval"))
    checks.append(_check("requires_approval", applicable=True, passed=True, value=needs_approval,
                         limit=policy.get("approver_role"), verified_by="lakebase:action_policies",
                         legal_basis=basis,
                         detail=(f"requires sign-off by {policy.get('approver_role')} before it may "
                                 "execute") if needs_approval else
                                "may execute without human sign-off when within policy"))

    verified = sum(1 for c in checks if c["verified_by"] != "payload" and c["applicable"])
    from_payload = sum(1 for c in checks if c["verified_by"] == "payload" and c["applicable"])
    return {"passed": not breaches, "breaches": breaches, "checks": checks,
            "policy": {k: v for k, v in policy.items()},
            "verified_count": verified, "payload_count": from_payload}


def _conduct_checks(action: dict, policy: dict, payload: dict, basis: str | None,
                    breaches: list[str], w=None) -> list[dict[str, Any]]:
    """The checks that read the bank's own data, batched into a single SELECT.

    Builds only the expressions this policy actually needs, binds every model-supplied value as a
    named parameter, and treats any failure to run as a breach.
    """
    checks: list[dict[str, Any]] = []
    loan = payload.get("loan_account_id") or action.get("subject")
    agent_id = payload.get("agent_id")
    epoch, when_ist = _scheduled_epoch(action, payload)

    selects: list[str] = []
    params: dict[str, tuple[Any, str]] = {}
    wanted: list[str] = []

    if policy.get("rbi_conduct_hours"):
        selects.append("is_within_rbi_conduct_hours(:epoch) AS conduct_hours_ok")
        params["epoch"] = (epoch, "BIGINT")
        wanted.append("rbi_conduct_hours")

    if policy.get("requires_agent_certification"):
        if agent_id:
            selects.append("agent_conduct_status(:agent_id) AS agent_status")
            params["agent_id"] = (str(agent_id), "STRING")
            wanted.append("agent_certification")
        else:
            checks.append(_check("agent_certification", applicable=True, passed=False,
                                 legal_basis=basis,
                                 detail="this action requires a certified recovery agent but the "
                                        "request names none"))
            breaches.append(f"{action.get('action_type')} requires an agent_id to verify conduct "
                            "certification")

    needs_loan = (policy.get("blocked_by_open_grievance") or policy.get("min_dpd_days") is not None
                  or policy.get("max_contacts_per_day") is not None)
    if needs_loan and not loan:
        checks.append(_check("loan_account_resolvable", applicable=True, passed=False,
                             detail="the account-level controls for this action need a "
                                    "loan_account_id and the request states none"))
        breaches.append(f"{action.get('action_type')} requires a loan_account_id")
    elif needs_loan:
        params["loan"] = (str(loan), "STRING")
        # ALWAYS resolve the account first. `has_open_grievance` and `contacts_on_date` answer
        # "nothing found", which for a loan id that does not exist is indistinguishable from "clean
        # record" — so a typo or a hallucinated account number would sail through both controls
        # reporting no grievance and no prior contact. Absence of evidence is not evidence of
        # compliance: if the account cannot be resolved, the account-level controls have not run.
        selects.append("loan_customer_id(:loan) AS resolved_customer")
        wanted.append("account_exists")
        if policy.get("blocked_by_open_grievance"):
            selects.append("has_open_grievance(loan_customer_id(:loan)) AS open_grievance")
            wanted.append("grievance_hold")
        if policy.get("min_dpd_days") is not None:
            selects.append("account_dpd_days(:loan) AS dpd_days")
            wanted.append("dpd_floor")
        if policy.get("max_contacts_per_day") is not None:
            selects.append("contacts_on_date(:loan, :on_date) AS contacts_today")
            params["on_date"] = (dt.datetime.fromtimestamp(epoch, IST).date().isoformat(), "DATE")
            wanted.append("contact_cap")

    if not selects:
        return checks

    try:
        row = dbx.run_sql("SELECT " + ", ".join(selects), parameters=params, w=w)["rows"][0]
    except Exception as e:
        # FAIL CLOSED. Every control we could not run becomes a breach, named individually so the
        # officer sees which protections were unavailable rather than a single opaque error.
        for rule in wanted:
            checks.append(_check(rule, applicable=True, passed=False, legal_basis=basis,
                                 verified_by="unity_catalog:UNAVAILABLE",
                                 detail=f"could not be verified against Unity Catalog, so it is "
                                        f"treated as failed: {str(e)[:160]}"))
        breaches.append("conduct controls could not be verified against Unity Catalog, so the "
                        f"action is refused: {str(e)[:160]}")
        return checks

    def as_bool(v: Any) -> bool:
        return str(v).lower() == "true"

    if "account_exists" in wanted:
        resolved = row.get("resolved_customer")
        exists = resolved not in (None, "", "null")
        checks.append(_check("account_exists", applicable=True, passed=exists, value=loan,
                             verified_by="unity_catalog:loan_customer_id",
                             detail=(f"account {loan} resolves to a customer on the book"
                                     if exists else
                                     f"account {loan} does not exist on the book, so the "
                                     "account-level conduct controls could not be evaluated")))
        if not exists:
            breaches.append(f"loan account {loan} could not be found, so the grievance and contact "
                            "controls for it cannot be verified; the action is refused")
            # Do not report the dependent controls as passed on evidence that does not exist.
            for dependent in ("grievance_hold", "contact_cap"):
                if dependent in wanted:
                    wanted.remove(dependent)
                    checks.append(_check(dependent, applicable=True, passed=False,
                                         legal_basis=basis,
                                         verified_by="unity_catalog:NOT_EVALUATED",
                                         detail="not evaluated: the account it applies to could not "
                                                "be resolved"))

    if "rbi_conduct_hours" in wanted:
        ok = as_bool(row.get("conduct_hours_ok"))
        checks.append(_check(
            "rbi_conduct_hours", applicable=True, passed=ok, limit="08:00-19:00 IST", value=when_ist,
            verified_by="unity_catalog:is_within_rbi_conduct_hours", legal_basis=basis,
            detail=f"contact scheduled for {when_ist}, "
                   + ("inside" if ok else "OUTSIDE") + " the permitted borrower-contact window"))
        if not ok:
            breaches.append(f"contact at {when_ist} falls outside the permitted 08:00-19:00 IST "
                            "borrower-contact window")

    if "agent_certification" in wanted:
        status = str(row.get("agent_status") or "unknown")
        ok = status == "OK"
        checks.append(_check("agent_certification", applicable=True, passed=ok, value=agent_id,
                             verified_by="unity_catalog:agent_conduct_status", legal_basis=basis,
                             detail=f"agent {agent_id}: " + ("conduct certification current"
                                                             if ok else status)))
        if not ok:
            breaches.append(f"recovery agent {agent_id} may not be deployed: {status}")

    if "grievance_hold" in wanted:
        open_grievance = as_bool(row.get("open_grievance"))
        checks.append(_check("grievance_hold", applicable=True, passed=not open_grievance,
                             value=loan, verified_by="unity_catalog:has_open_grievance",
                             legal_basis=basis,
                             detail=("this borrower has an unresolved complaint, so recovery "
                                     "pressure must not continue" if open_grievance
                                     else "no open grievance against this account")))
        if open_grievance:
            breaches.append(f"account {loan} has an open customer grievance; recovery action is "
                            "suspended until it is resolved")

    if "dpd_floor" in wanted:
        dpd = int(row.get("dpd_days") or 0)
        floor = int(policy["min_dpd_days"])
        ok = dpd >= floor
        checks.append(_check("dpd_floor", applicable=True, passed=ok, limit=floor, value=dpd,
                             verified_by="unity_catalog:account_dpd_days", legal_basis=basis,
                             detail=f"account is {dpd} days past due against a floor of {floor} "
                                    f"days for this action"))
        if not ok:
            breaches.append(f"account {loan} is only {dpd} days past due; {action.get('action_type')}"
                            f" requires at least {floor} days, so this action is disproportionate")

    if "contact_cap" in wanted:
        contacts = int(row.get("contacts_today") or 0)
        cap = int(policy["max_contacts_per_day"])
        ok = contacts < cap
        checks.append(_check("contact_cap", applicable=True, passed=ok, limit=cap, value=contacts,
                             verified_by="unity_catalog:contacts_on_date", legal_basis=basis,
                             detail=f"{contacts} contact attempt(s) already recorded against this "
                                    f"account today, against a daily cap of {cap}"))
        if not ok:
            breaches.append(f"account {loan} has already been contacted {contacts} time(s) today; "
                            f"the daily cap is {cap}")

    return checks
