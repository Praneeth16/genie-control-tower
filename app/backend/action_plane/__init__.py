"""Action Plane — the one governed plane every agent in this app acts through.

    from action_plane import ActionPlane, evaluate

`ActionPlane` is the state machine over Lakebase `actions`/`action_events`; `evaluate` runs the
guardrail checks (`action_policies` plus the Unity Catalog control functions) before anything
executes; `execute` dispatches an approved action to its connector(s), routed by `ROUTING`
(action_type -> connector keys), re-checking the kill switch and the guardrails on the way.
"""
from .executor import ROUTING, UnroutableAction, execute
from .guardrails import (GuardrailsBlinded, actions_enabled, assert_not_blinded,
                         authorise_approver, approver_roles, evaluate)
from .model import (
    ActionNotFound,
    ActionPlane,
    IllegalTransition,
    APPROVED,
    EXECUTED,
    EXECUTING,
    ESCALATED,
    FAILED,
    PROPOSED,
    REJECTED,
)

__all__ = [
    "ActionPlane",
    "evaluate",
    "actions_enabled",
    "assert_not_blinded",
    "authorise_approver",
    "approver_roles",
    "GuardrailsBlinded",
    "execute",
    "ROUTING",
    "UnroutableAction",
    "ActionNotFound",
    "IllegalTransition",
    "PROPOSED",
    "APPROVED",
    "EXECUTING",
    "EXECUTED",
    "REJECTED",
    "FAILED",
    "ESCALATED",
]
