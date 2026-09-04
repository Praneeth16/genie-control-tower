"""Mock downstream bank systems.

One endpoint per system the control tower can act on. Each returns a reference id shaped like the
real system's would be, so the action's `external_ref` in the audit trail looks like something an
operations team could actually search for.

Nothing here has side effects. The point is to prove the governed OUTBOUND path works end to end —
Unity Catalog HTTP connection, service-principal auth, receipt recorded — not to simulate banking.
"""
from __future__ import annotations

import hashlib
import datetime as dt
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock downstream bank systems")

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class Payload(BaseModel):
    # Deliberately permissive: each connector sends its own shape and the mock echoes it back.
    model_config = {"extra": "allow"}


def _ref(system: str, body: dict[str, Any]) -> str:
    """A deterministic reference id, so re-running a demo produces the same ids and a screenshot
    stays valid. Real systems allocate sequentially; a content hash is the honest stand-in."""
    seed = f"{system}|{sorted(body.items())!r}"
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    return f"{system}-{digest}"


def _receipt(system: str, body: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "ref_id": _ref(system, body),
        "system": system,
        "accepted_at": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "echo": body,
        **extra,
    }


@app.get("/health")
def health():
    return {"status": "ok", "systems": ["FOS", "CMS", "HRMS", "CORR", "LOS", "DISP", "NOTIFY"]}


@app.post("/fos/visit")
def fos_visit(p: Payload):
    """Field Operations System — schedules a recovery agent visit."""
    body = p.model_dump()
    return _receipt("FOS", body, status="SCHEDULED",
                    note="visit added to the agent's route sheet")


@app.post("/fos/allocation")
def fos_allocation(p: Payload):
    """Field Operations System — allocates accounts to a recovery agency."""
    body = p.model_dump()
    return _receipt("FOS", body, status="ALLOCATED")


@app.post("/cms/case")
def cms_case(p: Payload):
    """Complaint Management System — creates or updates a grievance case."""
    body = p.model_dump()
    return _receipt("CMS", body, status="LOGGED")


@app.post("/cms/ombudsman")
def cms_ombudsman(p: Payload):
    """Complaint Management System — files a referral under the Integrated Ombudsman Scheme."""
    body = p.model_dump()
    return _receipt("CMS", body, status="REFERRED", scheme="RB-IOS")


@app.post("/hrms/incentive-hold")
def hrms_hold(p: Payload):
    """HRMS — places a hold on an incentive payout pending Compensation review."""
    body = p.model_dump()
    return _receipt("HRMS", body, status="HELD")


@app.post("/hrms/coaching-case")
def hrms_coaching(p: Payload):
    """HRMS — opens a coaching case for a relationship manager."""
    body = p.model_dump()
    return _receipt("HRMS", body, status="OPEN")


@app.post("/correspondence/letter")
def correspondence(p: Payload):
    """Correspondence system — queues a customer letter for dispatch."""
    body = p.model_dump()
    return _receipt("CORR", body, status="QUEUED",
                    channel=body.get("channel", "post"))


@app.post("/los/settlement")
def los_settlement(p: Payload):
    """Loan origination / servicing — records a one-time settlement offer."""
    body = p.model_dump()
    return _receipt("LOS", body, status="OFFER_RECORDED")


@app.post("/los/ptp")
def los_ptp(p: Payload):
    """Loan servicing — records a promise-to-pay against the account."""
    body = p.model_dump()
    return _receipt("LOS", body, status="PTP_RECORDED")


@app.post("/los/fee-reversal")
def los_fee(p: Payload):
    """Loan servicing — reverses a fee or charge."""
    body = p.model_dump()
    return _receipt("LOS", body, status="REVERSED")


@app.post("/disputes/provisional-credit")
def provisional_credit(p: Payload):
    """Disputes engine — posts provisional credit for a disputed transaction."""
    body = p.model_dump()
    return _receipt("DISP", body, status="CREDIT_POSTED")


@app.post("/notify/message")
def notify(p: Payload):
    """Notification fan-out (Teams / email) to an operations channel."""
    body = p.model_dump()
    return _receipt("NOTIFY", body, status="SENT")
