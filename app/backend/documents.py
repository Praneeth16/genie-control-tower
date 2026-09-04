"""The volumes lane — reading the bank's documents, and writing new ones.

This is the half of a bank's evidence that never fits in a table. A complaint row says
`category_code = 'REC', severity = 'Critical'`; the letter says the agent came at 9:15 pm and shouted
the borrower's name so the neighbours could hear. The row tells you to act, the letter tells you why.

Two directions, and the governance is different for each:

  READING  runs on behalf of the USER. A customer letter is customer data, so the same row filters and
           column masks that govern the structured tables govern this. The parsed text lives in a
           Delta table in the same schema precisely so it inherits those controls rather than sitting
           in a separate store with its own, weaker ones.

  WRITING  runs as the APP service principal, into an `outbound/` prefix. The agent DRAFTS; a named
           human approves the dispatch through the action plane. Nothing here sends anything — writing
           a draft to a volume and dispatching a letter to a customer are deliberately two different
           acts requiring two different authorities.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import uuid
from typing import Any

import config
import databricks_client as dbx

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OUTBOUND = f"{config.VOLUME_ROOT}/outbound"

# A complaint id is the only user-supplied value that reaches a volume PATH. Everything else is bound
# as a SQL parameter, but a path cannot be parameterised, so it is validated against a strict pattern
# rather than escaped — a value like "../../etc/passwd" must never become part of a file path.
_COMPLAINT_ID = re.compile(r"^CM[0-9]{4,10}$")


class BadComplaintId(ValueError):
    """The complaint id is not in the expected form, so it will not be used to build a path."""


def _validate(complaint_id: str) -> str:
    cid = (complaint_id or "").strip().upper()
    if not _COMPLAINT_ID.match(cid):
        raise BadComplaintId(
            f"'{complaint_id}' is not a valid complaint id (expected CM followed by digits)")
    return cid


def evidence(complaint_id: str, w=None) -> dict[str, Any]:
    """The structured record and the customer's own words, side by side, for one complaint.

    Runs as the caller, so a user who is not entitled to this branch's complaints gets nothing — the
    document lane is not a way around the row filters on the tables.
    """
    cid = _validate(complaint_id)
    rows = dbx.run_sql(
        f"""SELECT c.complaint_id, CAST(c.received_date AS STRING) AS received_date,
                   c.category_code, cc.category_name, cc.rbi_category, c.severity, c.status,
                   c.product_code, c.sla_days, c.days_to_resolve, c.sla_breached,
                   c.escalated_to_ombudsman, c.repeat_complainant, c.customer_id,
                   b.city, b.region, c.complaint_text,
                   d.file_path, d.document_text
            FROM {config.FQ}.complaints c
            LEFT JOIN {config.FQ}.complaint_categories cc ON c.category_code = cc.category_code
            LEFT JOIN {config.FQ}.branch_master b ON c.branch_id = b.branch_id
            LEFT JOIN {config.FQ}.complaint_documents d ON d.complaint_id = c.complaint_id
            WHERE c.complaint_id = :cid
            LIMIT 1""",
        parameters={"cid": (cid, "STRING")}, w=w)["rows"]
    if not rows:
        return {"complaint_id": cid, "found": False,
                "note": "No complaint with that id is visible to you. It may not exist, or it may "
                        "belong to a branch outside your entitlement."}
    r = rows[0]
    return {"complaint_id": cid, "found": True, "record": r,
            "has_letter": bool(r.get("document_text")),
            "letter_path": r.get("file_path")}


def draft_letter(complaint_id: str, w=None, author: str | None = None) -> dict[str, Any]:
    """Draft a resolution letter for one complaint and write it to the outbound volume prefix.

    Grounded in the complaint record AND the customer's own letter, so the reply answers what they
    actually said rather than a generic template. The draft is explicitly marked as unsigned: the
    Integrated Ombudsman Scheme expects a written, reasoned reply from a named bank officer, and an
    automated system is not that officer.
    """
    ev = evidence(complaint_id, w=w)
    if not ev["found"]:
        return {"ok": False, **ev}
    rec = ev["record"]

    prompt = (
        "You are drafting a grievance resolution letter for an Indian retail bank, for review by a "
        "named bank officer who will sign it. Write in plain, respectful English a retail customer "
        "will understand. Do not invent facts, compensation amounts, or dates that are not given "
        "below. If the complaint is still open, say what happens next and by when rather than "
        "claiming it is resolved.\n\n"
        f"Complaint record (authoritative):\n"
        f"  id: {rec.get('complaint_id')}\n"
        f"  received: {rec.get('received_date')}\n"
        f"  ground of complaint (RBI category): {rec.get('rbi_category')}\n"
        f"  category: {rec.get('category_name')}\n"
        f"  severity: {rec.get('severity')}\n"
        f"  status: {rec.get('status')}\n"
        f"  product: {rec.get('product_code')}\n"
        f"  SLA days: {rec.get('sla_days')}, days to resolve: {rec.get('days_to_resolve')}, "
        f"SLA breached: {rec.get('sla_breached')}\n"
        f"  escalated to Ombudsman: {rec.get('escalated_to_ombudsman')}\n"
        f"  branch city: {rec.get('city')}, region: {rec.get('region')}\n\n"
        f"What the customer wrote:\n{(rec.get('document_text') or rec.get('complaint_text') or '(no letter on file)')[:3500]}\n\n"
        "Write the letter body only — no letterhead, no signature block, no placeholders in square "
        "brackets. Four short paragraphs at most: acknowledge what they told us, state what we found, "
        "state what we are doing or have done, and tell them how to escalate to the Banking Ombudsman "
        "if they remain dissatisfied."
    )
    body = dbx.chat(messages=[{"role": "user", "content": prompt}], max_tokens=900).strip()

    now = dt.datetime.now(IST)
    header = (
        "*** SYNTHETIC DOCUMENT — generated in a Databricks workshop from synthetic data. "
        "Not a real customer communication. ***\n\n"
        f"{config.BANK_NAME} — Grievance Redressal\n"
        "DRAFT FOR REVIEW — UNSIGNED. This draft has no authority until a named bank officer approves\n"
        "its dispatch through the action plane. It is not a reply to the customer as it stands.\n\n"
        f"Complaint ID   : {rec.get('complaint_id')}\n"
        f"Received       : {rec.get('received_date')}\n"
        f"Ground         : {rec.get('rbi_category')}\n"
        f"Branch city    : {rec.get('city')}\n"
        f"Drafted        : {now.strftime('%Y-%m-%d %H:%M IST')}\n"
        f"Drafted by     : Genie Control Tower (automated draft)\n"
        f"Requested by   : {author or 'unknown'}\n"
        f"{'-' * 78}\n\n"
    )
    footer = (
        f"\n\n{'-' * 78}\n"
        "If you remain dissatisfied you may approach the Reserve Bank of India's Ombudsman under the\n"
        "Reserve Bank - Integrated Ombudsman Scheme. The bank's Principal Nodal Officer's contact\n"
        "details are published on the bank's website and at every branch.\n\n"
        "Signed by: ______________________________  (name and designation of the approving officer)\n"
    )
    document = header + body + footer

    # Second resolution is not enough. Two officers drafting for the same complaint inside the same
    # second produced the same path, and `overwrite=True` meant the second upload silently replaced the
    # first — so an approver could review one draft while dispatch later read a different one. A short
    # random suffix makes each draft its own immutable artefact.
    suffix = uuid.uuid4().hex[:6]
    filename = (f"{rec.get('complaint_id')}_resolution_draft_"
                f"{now.strftime('%Y%m%dT%H%M%S')}_{suffix}.txt")
    path = f"{OUTBOUND}/{filename}"
    # The draft is written by the APP identity, not the caller: it is the app's artefact, and the
    # user's token is deliberately read-only.
    dbx.client().files.upload(path, io.BytesIO(document.encode("utf-8")), overwrite=True)

    return {
        "ok": True,
        "complaint_id": rec.get("complaint_id"),
        "document_path": path,
        "preview": document[:1400],
        "characters": len(document),
        "grounded_in_letter": bool(rec.get("document_text")),
        # Everything the dispatch action needs, so the UI can propose it without re-deriving anything.
        "action_draft": {
            "action_type": "dispatch_customer_letter",
            "subject": rec.get("complaint_id"),
            "region": rec.get("region"),
            "payload": {
                "complaint_id": rec.get("complaint_id"),
                "customer_id": rec.get("customer_id"),
                "document_path": path,
                "template": "grievance_resolution",
                "channel": "post",
                "note": "Draft generated from the complaint record and the customer's own letter.",
            },
            "level": 2,
        },
        "note": "Draft only. Dispatch requires approval by the Service Manager through the action "
                "plane; the letter is unsigned until then.",
    }


def list_outbound(limit: int = 25) -> dict[str, Any]:
    """What the agent has drafted. Read as the app identity — these are the app's own artefacts."""
    try:
        items = list(dbx.client().files.list_directory_contents(OUTBOUND))
    except Exception as e:
        return {"documents": [], "error": str(e)[:200]}
    docs = [{"name": i.name, "path": i.path, "size": i.file_size,
             "modified": getattr(i, "last_modified", None)} for i in items]
    docs.sort(key=lambda d: d["name"], reverse=True)
    return {"documents": docs[:limit], "outbound_path": OUTBOUND}


def read_document(path: str) -> dict[str, Any]:
    """Read one generated draft back. Restricted to the outbound prefix: this endpoint must not become
    a way to read arbitrary volume paths."""
    if not path.startswith(OUTBOUND + "/") or ".." in path:
        raise BadComplaintId("path is outside the outbound prefix")
    resp = dbx.client().files.download(path)
    return {"path": path, "text": resp.contents.read().decode("utf-8", errors="replace")}

# ---------------------------------------------------------------------------
# SEMANTIC SEARCH over the letter corpus
# ---------------------------------------------------------------------------
VS_INDEX = config.VS_INDEX

_VS_UNAVAILABLE = (
    "Semantic search is not configured. Build the index with "
    "`python3 scripts/build_vector_index.py --create`."
)


def semantic_search(query: str, w, limit: int = 8) -> dict[str, Any]:
    """Find letters by what the borrower SAID, then re-read the records AS THE CALLER.

    The two-step is the governance design, not an implementation detail.

    A Vector Search index is a COPY of the text held outside the governed table, and Unity Catalog row
    filters and column masks do NOT follow data into it. So an index queried directly by end users would
    be a clean way around every control this application exists to demonstrate. Instead:

      1. The INDEX is queried as the app service principal, and returns only complaint ids and the
         snippet that matched. The index is never granted to end users.
      2. Those ids are then read back out of `complaints` **as the caller**, so row filters and column
         masks apply exactly as they do everywhere else.

    The visible consequence is the point: retrieval may find a letter the caller is not entitled to read,
    and the caller is told the count without the content. Retrieval locates; governance still decides.
    """
    q = (query or "").strip()
    if len(q) < 3:
        raise ValueError("search text must be at least 3 characters")
    if not VS_INDEX:
        # Optional capability: the structured lane works without it, so say so rather than erroring.
        return {"ok": False, "note": _VS_UNAVAILABLE, "hits": [], "detail": "VS_INDEX is not configured"}

    try:
        from databricks.sdk import WorkspaceClient  # noqa: F401
        sp = dbx.client()                            # service principal, deliberately NOT the caller
        res = sp.vector_search_indexes.query_index(
            index_name=VS_INDEX,
            columns=["complaint_id", "document_type", "rbi_ground", "city", "document_text"],
            query_text=q, num_results=min(limit, 20))
    except Exception as e:
        return {"ok": False, "note": f"{_VS_UNAVAILABLE} ({type(e).__name__})", "hits": [],
                "detail": str(e)[:200]}

    rows = (res.result.data_array if res.result else []) or []
    hits: list[dict[str, Any]] = []
    for r in rows:
        cid, dtype, ground, city, text = r[0], r[1], r[2], r[3], r[4]
        hits.append({"complaint_id": cid, "document_type": dtype, "rbi_ground": ground,
                     "city": city, "score": r[-1], "snippet": _match_snippet(str(text), q)})

    ids = [h["complaint_id"] for h in hits if h["complaint_id"]]
    visible: dict[str, dict] = {}
    if ids:
        # Read back AS THE CALLER. Parameterised, and the ids came from our own index rather than from
        # user input, but they are still bound rather than interpolated.
        params = {f"id{i}": (cid, "STRING") for i, cid in enumerate(ids)}
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        out = dbx.run_sql(
            f"""SELECT c.complaint_id, c.status, c.severity, c.received_date,
                       c.escalated_to_ombudsman, c.sla_breached, cc.rbi_category
                FROM {config.FQ}.complaints c
                LEFT JOIN {config.FQ}.complaint_categories cc ON c.category_code = cc.category_code
                WHERE c.complaint_id IN ({placeholders})""",
            parameters=params, w=w)
        visible = {r["complaint_id"]: r for r in out["rows"]}

    for h in hits:
        rec = visible.get(h["complaint_id"])
        h["record"] = rec
        # NOT the same as "no such complaint", and the UI must not let anyone read it that way.
        h["outside_your_scope"] = bool(h["complaint_id"]) and rec is None
        if h["outside_your_scope"]:
            # STRIP the content, do not merely label it.
            #
            # The first version returned the ground, the city and a snippet of the letter and set a flag
            # for the UI to render differently. That is not authorisation, it is a CSS choice: the
            # payload had already crossed the boundary, and anyone reading the JSON — or the network
            # tab — got text the caller is not entitled to. The snippet was also built from text the
            # SERVICE PRINCIPAL retrieved, so it leaked precisely the rows the row filter removed.
            #
            # What survives is the fact that a match exists, which is what makes the governance point,
            # and the id needed to request access. Nothing about its content.
            h["snippet"] = ""
            h["rbi_ground"] = None
            h["city"] = None
            h["document_type"] = None

    withheld = sum(1 for h in hits if h["outside_your_scope"])
    return {"ok": True, "hits": hits, "query": q, "index": VS_INDEX,
            "returned": len(hits), "withheld_by_entitlement": withheld,
            "note": ("The index was searched as the application's service principal; every record was "
                     "then re-read under YOUR entitlements, and anything outside them is returned "
                     "WITHOUT its content — not merely flagged. "
                     + (f"{withheld} match(es) are outside your scope and are listed without content."
                        if withheld else "All matches are within your scope.")),
            "data_is_synthetic": config.DATA_IS_SYNTHETIC}


def _match_snippet(text: str, query: str, width: int = 220) -> str:
    """The sentence that matched, not the letterhead. Every letter starts with the same header block, so
    a naive first-N-characters snippet makes all results look identical."""
    flat = " ".join(text.split())
    body = flat.split("To the Grievance Redressal Officer,")[-1]
    low = body.lower()
    for token in sorted((t for t in query.lower().split() if len(t) > 4), key=len, reverse=True):
        if token in low:
            i = low.index(token)
            return ("…" if i > 0 else "") + body[max(0, i - 90): i + width - 90].strip() + "…"
    return body[:width].strip() + "…"
