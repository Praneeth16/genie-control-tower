"""Tool connectors — one module per downstream bank system the Action Plane acts on.

Each connector exposes functions taking an action payload and returning
{ref_id, system, raw, via}. They post through `_http.post`, which prefers a Unity Catalog HTTP
connection (so every outbound bank action is catalog-governed and appears in lineage) and falls back
to a service-principal direct POST.

`SYSTEMS` maps a stable connector key -> callable, so the executor can dispatch by name and the UI
can introspect what this agent is able to touch. The keys are OPERATIONS, not systems, because two
actions on the same system need different request shapes: an ombudsman referral is not a case note.
"""
from __future__ import annotations

from . import cms, correspondence, disputes, fos, hrms, los, notify
from ._http import ConnectorError

SYSTEMS = {
    # Field Operations System
    "fos.visit": fos.visit,
    "fos.allocation": fos.allocation,
    # Complaint Management System
    "cms.case": cms.case,
    "cms.ombudsman": cms.ombudsman,
    # HRMS
    "hrms.incentive_hold": hrms.incentive_hold,
    "hrms.coaching_case": hrms.coaching_case,
    # Correspondence
    "corr.letter": correspondence.letter,
    # Loan origination / servicing
    "los.settlement": los.settlement,
    "los.ptp": los.ptp,
    "los.fee_reversal": los.fee_reversal,
    # Disputes
    "disp.provisional_credit": disputes.provisional_credit,
    # Notification fan-out
    "notify.message": notify.message,
}

__all__ = ["SYSTEMS", "ConnectorError", "fos", "cms", "hrms", "correspondence", "los",
           "disputes", "notify"]
