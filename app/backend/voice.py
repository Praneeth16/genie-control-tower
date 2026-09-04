"""Voice lane — AGENT ASSIST, not a customer-facing voice bot.

That distinction is the whole design, and it is deliberate rather than a shortcut.

The Databricks voice reference implementation (Suneel Sunkara's `genie-voice-agent`: Qwen3-ASR on GPU
Model Serving, Silero VAD for semantic end-of-turn, VoxCPM2 TTS streamed as ~80ms PCM slices) has a
measured end-to-end latency of 30-40 seconds in its current version, and its deck states plainly that
the Model Serving stack does not yet support real-time inference. A 30-second pause is fatal to a
self-service bot and it is also the wrong product for a bank: putting a generative voice in front of a
retail borrower is an RBI conduct and DPDP exposure that nobody in an AI CoE wants to own on day one.

Reframed as assist, that same latency becomes an asset — the human keeps talking while the platform
looks things up behind them. So:

  * Speech to text happens IN THE BROWSER (Web Speech API), on the officer's device. Nothing about
    that choice is a compromise: it is lower latency than any hosted ASR, and no customer audio ever
    leaves the machine or reaches Databricks, which is the answer to the first question a bank's
    privacy officer asks.
  * This module does the part that needs governed data: pull the identifiers out of what was said,
    fetch the account and grievance facts UNDER THE CALLER'S OWN IDENTITY, and run the same RBI
    conduct checks the action plane runs — live, while the call is still happening.
  * Nothing here speaks to the customer and nothing here acts. It produces facts and a warning
    banner. Any action still goes through the approval plane with a named human on it.

Deliberately NOT Genie: a Genie message costs one of roughly five per minute for the whole workspace
and takes seconds. An assist HUD refreshes on every few words. This lane therefore uses narrow
parameterised SQL against the same governed tables, which is both faster and cheaper. The typed Ask
tab remains the path to open-ended questions — voice never becomes the only way to get an answer.
"""
from __future__ import annotations

import re
from typing import Any

import config
import databricks_client as dbx
import tracing
from action_plane import guardrails

# Identifier shapes as they exist in the governed tables. Anchored and bounded: these are pasted into
# nothing, but they are used to decide WHICH parameterised query runs, and a sloppy pattern would send
# a complaint id down the loan-account path and return a confusing empty snapshot.
_LOAN = re.compile(r"\bLN\s?0*([0-9]{1,8})\b", re.IGNORECASE)
_COMPLAINT = re.compile(r"\bCM\s?0*([0-9]{1,9})\b", re.IGNORECASE)
_AGENT = re.compile(r"\bAG\s?0*([0-9]{1,5})\b", re.IGNORECASE)

# Spoken digits, because a person reading an account number aloud says "L N zero zero one" and the
# browser's recogniser writes it as words about as often as it writes numerals.
#
# Hindi and Marathi are here for a concrete reason, not as decoration: the borrowers this demo is about
# are microfinance customers in Solapur and Indore, and a Solapur field officer takes that call in
# Marathi. Both languages are written here in Devanagari AND in the Roman transliteration the Web Speech
# API often returns for `hi-IN` / `mr-IN`, because which one you get depends on the recogniser and the
# handset, and an officer whose account number silently fails to resolve has no way to know why.
#
# Devanagari digit GLYPHS (०-९) are handled separately below, since a recogniser given numerals may emit
# those rather than ASCII.
_SPOKEN_DIGITS: dict[str, str] = {
    # English
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "double": "",
    # Hindi — Devanagari
    "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
    "पांच": "5", "पाँच": "5", "छह": "6", "छः": "6", "सात": "7", "आठ": "8", "नौ": "9",
    # Hindi — Roman transliteration
    "shunya": "0", "shoonya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "chhah": "6", "chah": "6", "chhe": "6", "saat": "7",
    "aath": "8", "nau": "9",
    # Marathi — Devanagari (differs from Hindi at 5, 6 and 9)
    "शून्य ": "0", "दोन": "2", "पाच": "5", "सहा": "6", "नऊ": "9",
    # Marathi — Roman transliteration
    "don": "2", "paach": "5", "saha": "6", "nau_mr": "9", "shunn": "0",
}

# Devanagari digit glyphs, mapped to ASCII so the identifier patterns match.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# The words an officer uses to introduce an identifier, in all three languages. Stripped before parsing
# so "कर्ज खाते एल एन ..." normalises the same way as "loan account L N ...".
_NOISE_WORDS = frozenset({
    "account", "loan", "number", "complaint", "agent",
    "khata", "khate", "karj", "karja", "kraman", "shikayat", "takrar",
    "खाता", "खाते", "कर्ज", "क्रमांक", "नंबर", "शिकायत", "तक्रार", "एजंट", "एजेंट",
})

# Roman transliterations of the LN / CM / AG letter prefixes as a recogniser may render them when the
# officer says them in Hindi or Marathi ("el en" for L N).
_PREFIX_ALIASES = (
    ("el en", "LN"), ("el n", "LN"), ("एल एन", "LN"),
    ("see em", "CM"), ("si em", "CM"), ("सी एम", "CM"),
    ("ay jee", "AG"), ("e ji", "AG"), ("ए जी", "AG"),
)


def _normalise(text: str) -> str:
    """Turn spoken identifiers into the written form the tables use, in English, Hindi or Marathi.

    "loan account L N double zero zero one two three" -> "loan account LN0000123"
    "कर्ज खाते एल एन शून्य शून्य एक एक तीन पाच"        -> "LN001135"

    Without this the HUD stays blank for the whole call while the officer wonders what they said wrong,
    which is worse than having no HUD at all.
    """
    t = text.translate(_DEVANAGARI_DIGITS)
    # Multi-word prefix aliases first, before single letters get glued together.
    low = t.lower()
    for alias, prefix in _PREFIX_ALIASES:
        if alias in low:
            i = low.index(alias)
            t = t[:i] + prefix + t[i + len(alias):]
            low = t.lower()
    t = t.replace("-", " ").replace(".", " ")
    t = re.sub(r"\b([A-Za-z])\s+(?=[A-Za-z]\b)", r"\1", t)          # "L N" -> "LN"
    out: list[str] = []
    for word in t.split():
        key = word.lower().strip(",।")            # danda is Devanagari's full stop
        if key in _NOISE_WORDS:
            continue
        out.append(_SPOKEN_DIGITS.get(key, word))
    joined = " ".join(out)
    # Collapse the digit runs that the substitution above leaves separated by spaces.
    return re.sub(r"(?<=\d) +(?=\d)", "", joined)


def extract_entities(transcript: str) -> dict[str, Any]:
    """Identifiers heard in the call. Zero-padded back to the stored width."""
    t = _normalise(transcript)
    ents: dict[str, Any] = {}
    if m := _LOAN.search(t):
        ents["loan_account_id"] = f"LN{int(m.group(1)):06d}"
    if m := _COMPLAINT.search(t):
        ents["complaint_id"] = f"CM{int(m.group(1)):07d}"
    if m := _AGENT.search(t):
        ents["agent_id"] = f"AG{int(m.group(1)):03d}"
    return ents


# --------------------------------------------------------------------------- governed prefetch
def _loan_snapshot(loan_id: str, w) -> dict[str, Any] | None:
    """Account facts, read AS THE CALLER. A regional officer who is not entitled to this account gets
    no rows here, exactly as they get no rows from the Genie Agent — the HUD must not become a way
    around a row filter."""
    out = dbx.run_sql(
        f"""
        SELECT l.loan_account_id, l.customer_id, l.product_code, l.branch_id,
               b.city, b.region,
               ROUND(l.outstanding_principal, 0) AS outstanding_principal,
               ROUND(l.emi_amount, 0)            AS emi_amount,
               l.customer_segment, l.is_restructured,
               d.dpd_days, d.dpd_bucket, d.is_npa,
               r.next_due_date, r.emis_pending, r.mandate_type,
               DATE_FORMAT(r.last_payment_date, 'yyyy-MM-dd') AS last_payment_date,
               ROUND(r.last_payment_amount, 0)   AS last_payment_amount
        FROM {config.FQ}.loan_accounts l
        LEFT JOIN {config.FQ}.branch_master b ON l.branch_id = b.branch_id
        LEFT JOIN {config.FQ}.repayment_schedule r ON l.loan_account_id = r.loan_account_id
        LEFT JOIN (
            SELECT loan_account_id, dpd_days, dpd_bucket, is_npa
            FROM {config.FQ}.delinquency_monthly
            WHERE snapshot_month = (SELECT MAX(snapshot_month) FROM {config.FQ}.delinquency_monthly)
        ) d ON l.loan_account_id = d.loan_account_id
        WHERE l.loan_account_id = :loan_id
        """,
        parameters={"loan_id": (loan_id, "STRING")}, w=w)
    return out["rows"][0] if out["rows"] else None


def _contact_history(loan_id: str, w) -> dict[str, Any]:
    out = dbx.run_sql(
        f"""
        SELECT COUNT(*) AS contact_attempts,
               COALESCE(SUM(CASE WHEN within_rbi_hours = FALSE THEN 1 ELSE 0 END), 0) AS out_of_hours,
               COALESCE(SUM(CASE WHEN outcome = 'Contacted - PTP' THEN 1 ELSE 0 END), 0) AS promises_to_pay,
               COALESCE(ROUND(SUM(amount_collected), 0), 0) AS amount_collected,
               MAX(DATE_FORMAT(activity_date, 'yyyy-MM-dd')) AS last_contact
        FROM {config.FQ}.collections_activity
        WHERE loan_account_id = :loan_id
        """,
        parameters={"loan_id": (loan_id, "STRING")}, w=w)
    return out["rows"][0] if out["rows"] else {}


def _grievance_state(customer_id: str, w) -> dict[str, Any]:
    """Open complaints for this customer. This is the fact that most often changes what an officer is
    allowed to say next: a borrower with a live grievance must not be pressed for recovery."""
    out = dbx.run_sql(
        f"""
        SELECT COUNT(*) AS open_complaints,
               SUM(CASE WHEN escalated_to_ombudsman THEN 1 ELSE 0 END) AS ombudsman_cases,
               MAX(CASE WHEN status = 'Open' THEN complaint_id END) AS open_complaint_id,
               MAX(CASE WHEN status = 'Open' THEN c.rbi_category END) AS open_ground
        FROM {config.FQ}.complaints x
        LEFT JOIN {config.FQ}.complaint_categories c ON x.category_code = c.category_code
        WHERE x.customer_id = :cid AND x.status = 'Open'
        """,
        parameters={"cid": (customer_id, "STRING")}, w=w)
    return out["rows"][0] if out["rows"] else {}


def _complaint_snapshot(complaint_id: str, w) -> dict[str, Any] | None:
    out = dbx.run_sql(
        f"""
        SELECT x.complaint_id, x.customer_id, x.channel, x.severity, x.status,
               x.product_code, x.repeat_complainant, x.escalated_to_ombudsman,
               DATE_FORMAT(x.received_date, 'yyyy-MM-dd') AS received_date,
               x.sla_days, x.sla_breached,
               DATEDIFF(DATE'2026-08-31', x.received_date) AS days_open,
               c.category_name, c.rbi_category
        FROM {config.FQ}.complaints x
        LEFT JOIN {config.FQ}.complaint_categories c ON x.category_code = c.category_code
        WHERE x.complaint_id = :cm
        """,
        parameters={"cm": (complaint_id, "STRING")}, w=w)
    return out["rows"][0] if out["rows"] else None


# --------------------------------------------------------------------------- conduct, live
def _conduct(loan: dict | None, grievance: dict, epoch_seconds: int | None) -> list[dict[str, Any]]:
    """The RBI conduct picture, evaluated WHILE THE CALL IS HAPPENING.

    Same controls the action plane enforces, and — like there — verified as the service principal
    rather than on behalf of the caller. A conduct check a collections officer could blind by their own
    row filters would be theatre.
    """
    checks: list[dict[str, Any]] = []
    verified = guardrails.assert_not_blinded()
    if epoch_seconds is not None:
        try:
            # `ist_hour` returns the HOUR ONLY. Rendering it as "{hr}:00" printed a 21:45 call as
            # "21:00 IST" — a fabricated minute, and the same class of bug as showing IST times in UTC.
            # The verdict still comes from the UC function (that is the control); the clock string is
            # formatted separately and exactly, so the banner never states a time that did not happen.
            out = dbx.run_sql(
                f"""SELECT {config.FQ}.is_within_rbi_conduct_hours(:t) AS ok,
                           DATE_FORMAT(FROM_UTC_TIMESTAMP(TIMESTAMP_SECONDS(:t), 'Asia/Kolkata'),
                                       'HH:mm') AS ist_time""",
                parameters={"t": (str(int(epoch_seconds)), "BIGINT")})
            row = out["rows"][0]
            ok = bool(row["ok"]) if not isinstance(row["ok"], str) else str(row["ok"]).lower() == "true"
            at = row["ist_time"]
            checks.append({
                "rule": "rbi_conduct_hours", "passed": ok,
                "detail": (f"{at} IST is inside the 08:00-19:00 window RBI permits for borrower contact")
                          if ok else
                          (f"{at} IST is OUTSIDE the 08:00-19:00 window — end this call and reschedule; "
                           "do not discuss recovery"),
                "verified_by": "unity_catalog:is_within_rbi_conduct_hours"})
        except Exception as e:
            # Fail CLOSED. An unavailable conduct control must read as "do not proceed", never as a
            # silent pass, because the officer is on a live call and will act on this banner.
            checks.append({"rule": "rbi_conduct_hours", "passed": False,
                           "detail": f"conduct-hours control unavailable, treat as out of hours: {e}"[:200],
                           "verified_by": "unavailable"})

    open_complaints = int(grievance.get("open_complaints") or 0)
    checks.append({
        "rule": "grievance_hold", "passed": open_complaints == 0,
        "detail": "no open grievance on this customer" if open_complaints == 0 else
                  (f"{open_complaints} open grievance(s) — recovery pressure is on hold; "
                   f"ground: {grievance.get('open_ground') or 'unclassified'}"),
        "verified_by": "unity_catalog:complaints"})

    if loan:
        npa = str(loan.get("is_npa")).lower() in ("true", "1")
        checks.append({"rule": "npa_flag", "passed": not npa,
                       "detail": f"DPD {loan.get('dpd_days')} · {loan.get('dpd_bucket')}"
                                 + (" · classified NPA" if npa else ""),
                       "verified_by": "unity_catalog:delinquency_monthly"})
    # assert_not_blinded returns {visible, expected, blinded} and no prose, so say what was actually
    # counted. An integrity banner reading "verified" with an empty reason is indistinguishable from a
    # banner that failed to run.
    seen = verified.get("visible") or {}
    counted = ", ".join(f"{k} {v}" for k, v in sorted(seen.items())) or "nothing counted"
    return checks + [{"rule": "guardrail_integrity", "passed": not verified.get("blinded", True),
                      "detail": f"guardrail identity sees the whole book ({counted})",
                      "verified_by": "unity_catalog:guardrail_visibility"}]


def assist(transcript: str, w, epoch_seconds: int | None = None) -> dict[str, Any]:
    """One HUD refresh. Cheap enough to call every few seconds of speech."""
    with tracing.span("voice:assist", span_type="CHAIN",
                      transcript_chars=len(transcript)) as span:
        ents = extract_entities(transcript)
        loan = contact = complaint = None
        grievance: dict[str, Any] = {}
        customer_id = None

        if lid := ents.get("loan_account_id"):
            loan = _loan_snapshot(lid, w)
            if loan:
                customer_id = loan.get("customer_id")
                contact = _contact_history(lid, w)
        if cm := ents.get("complaint_id"):
            complaint = _complaint_snapshot(cm, w)
            customer_id = customer_id or (complaint or {}).get("customer_id")
        if customer_id:
            grievance = _grievance_state(customer_id, w)

        checks = _conduct(loan, grievance, epoch_seconds)
        result = {
            "entities": ents,
            "resolved": bool(loan or complaint),
            # `not_visible` is not the same as `not found`, and conflating them would be a governance
            # bug dressed as a UI bug: an officer must be told the record exists outside their scope
            # rather than being allowed to conclude the customer has no account.
            "not_visible": bool(ents) and not (loan or complaint),
            "loan": loan, "contact": contact, "complaint": complaint,
            "grievance": grievance, "customer_id": customer_id,
            "conduct": checks,
            "blocked": [c["rule"] for c in checks if not c["passed"]],
            "data_is_synthetic": config.DATA_IS_SYNTHETIC,
        }
        tracing.set_outputs(span, {"entities": ents, "resolved": result["resolved"],
                                   "blocked": result["blocked"]})
        return result
