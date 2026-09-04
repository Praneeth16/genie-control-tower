"""FastAPI app for the Genie Control Tower.

One process, one port: the JSON API under /api/* and the built React bundle at /. Databricks Apps
gives you a single port, so this is not a style choice.

Run locally:
    uvicorn main:app --reload --port 8000     # from backend/, with DATABRICKS_CONFIG_PROFILE set
In Apps: app.yaml runs the same command on $DATABRICKS_APP_PORT.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent
import authz
import config
import databricks_client as dbx
import documents
import governance
import identity
import voice
from actions_api import build_actions_router

log = logging.getLogger("control-tower")


def _fail(where: str, exc: Exception) -> HTTPException:
    """Log the real error, return a generic one.

    Returning str(exc) verbatim leaked warehouse diagnostics, internal object names and query text to
    any caller — `GET /api/governance/audit?limit=-1` was enough to see it. The operator needs the
    detail; the HTTP client does not.
    """
    log.exception("%s failed", where)
    return HTTPException(500, f"{where} failed. See the application logs for detail.")

AGENT_NAME = "control-tower-supervisor"

app = FastAPI(title="Genie Control Tower")

# Act -> Approve -> Execute routes.
app.include_router(build_actions_router(AGENT_NAME))

# CORS for the Vite dev server during local frontend work. Apps serves the built bundle from this
# same origin, so this is a development-only allowance.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskReq(BaseModel):
    question: str


class KillSwitchReq(BaseModel):
    flag: str = "actions_enabled"
    enabled: bool
    reason: str


class FeedbackReq(BaseModel):
    session_uuid: str
    rating: int  # +1 / -1
    note: Optional[str] = None


@app.get("/api/health")
def health(request: Request):
    """Liveness plus the configuration the app actually resolved — so a wrong warehouse or a missing
    Genie grant is visible on one URL instead of inferred from a failing question."""
    return {
        "status": "ok",
        "service_identity": dbx.current_user(),
        "caller": identity.user_email(request),
        "obo_active": identity.is_obo(request),
        "catalog": config.CATALOG,
        "schema": config.SCHEMA,
        "warehouse_id": config.WAREHOUSE_ID,
        "genie_agents": {d: bool(sid) for d, sid in config.SPACE_IDS.items()},
        "lakebase": f"{config.LAKEBASE_INSTANCE}/{config.LAKEBASE_SCHEMA}",
        "data_is_synthetic": config.DATA_IS_SYNTHETIC,
        "require_obo": config.REQUIRE_OBO,
        "turn_budget_seconds": config.TURN_BUDGET_SECONDS,
        # The workspace Genie quota is the resource most likely to break a live demo, so it is
        # reported rather than guessed at.
        "genie_quota": agent._GENIE_RATE.snapshot(),
    }


@app.post("/api/ask")
def ask(req: AskReq, request: Request):
    if not req.question.strip():
        raise HTTPException(400, "question is required")
    try:
        return agent.ask(
            req.question,
            user_token=identity.user_token(request),
            user_email=identity.user_email(request),
        )
    except PermissionError as e:
        # No forwarded user token and REQUIRE_OBO is on: refusing to read as the service principal.
        raise HTTPException(403, str(e))
    except Exception as e:
        raise _fail("ask", e)


@app.post("/api/feedback")
def feedback(req: FeedbackReq, request: Request):
    if not req.session_uuid:
        raise HTTPException(400, "session_uuid is required")
    try:
        return agent.record_feedback(
            req.session_uuid, req.rating, req.note,
            user_email=identity.user_email(request),
        )
    except Exception as e:
        raise _fail("feedback", e)


# ---- governance -----------------------------------------------------------
# These endpoints are the evidence layer. Note which identity each one uses: `scope` runs as the
# CALLER because the question is what that person can see; the rest run as the app service principal
# because a catalogue of controls must not itself be filtered by the caller's scope.
@app.get("/api/governance/scope")
def governance_scope(request: Request):
    try:
        return governance.scope(w=agent._user_genie_client(identity.user_token(request)))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise _fail("scope", e)


@app.get("/api/governance/policies")
def governance_policies():
    try:
        return governance.policies()
    except Exception as e:
        raise _fail("policies", e)


@app.get("/api/governance/audit")
def governance_audit(request: Request, hours: int = 48, limit: int = 60):
    """The platform audit feed. ADMIN ONLY — it returns other users' email addresses and source IPs."""
    authz.require_admin(request)
    # Clamp both ends: a negative limit reached Databricks SQL as `LIMIT -1` and failed with a
    # diagnostic that was then returned to the caller.
    try:
        return governance.audit(hours=max(1, min(hours, 168)), limit=max(1, min(limit, 200)),
                                caller=identity.user_email(request))
    except Exception as e:
        raise _fail("audit", e)


@app.get("/api/governance/controls")
def governance_controls():
    try:
        return governance.controls()
    except Exception as e:
        raise _fail("controls", e)


@app.get("/api/governance/usage")
def governance_usage():
    try:
        return governance.usage()
    except Exception as e:
        raise _fail("usage", e)


@app.post("/api/governance/kill-switch")
def governance_kill_switch(req: KillSwitchReq, request: Request):
    """Stop or resume the agents' ability to act. A data change, not a redeploy.

    ADMIN ONLY. Without this check any signed-in user could resume actions after someone else had
    stopped them in an emergency, which would make the kill switch decorative."""
    who = authz.require_admin(request)
    try:
        return governance.set_kill_switch(req.flag, req.enabled, req.reason, who)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise _fail("kill switch", e)


# ---- documents (the volumes lane) -----------------------------------------
@app.get("/api/documents/evidence/{complaint_id}")
def document_evidence(complaint_id: str, request: Request):
    """The complaint record and the customer's own letter, read AS THE CALLER so the row filters that
    protect the structured data protect the document text too."""
    try:
        return documents.evidence(
            complaint_id, w=agent._user_genie_client(identity.user_token(request)))
    except documents.BadComplaintId as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise _fail("evidence", e)


@app.post("/api/documents/draft/{complaint_id}")
def document_draft(complaint_id: str, request: Request):
    """Draft a resolution letter into the outbound volume prefix. A DRAFT: it is unsigned and has no
    authority until the dispatch action is approved by a named officer."""
    try:
        return documents.draft_letter(
            complaint_id,
            w=agent._user_genie_client(identity.user_token(request)),
            author=identity.user_email(request))
    except documents.BadComplaintId as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise _fail("draft", e)


class SearchReq(BaseModel):
    query: str
    limit: Optional[int] = 8


@app.post("/api/documents/search")
def document_search(req: SearchReq, request: Request):
    """Semantic search over the 713-letter corpus.

    The index is queried as the service principal and the records are re-read as the caller — see
    documents.semantic_search for why that split is the whole point.
    """
    token = identity.user_token(request)
    if not token and config.REQUIRE_OBO:
        raise HTTPException(403, "no forwarded user token; refusing to read as the service principal")
    try:
        w = agent._user_genie_client(token) or dbx.client()
        return documents.semantic_search(req.query, w=w, limit=req.limit or 8)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise _fail("document_search", e)


@app.get("/api/documents/outbound")
def document_outbound(request: Request):
    """Everything the agent has drafted. ADMIN ONLY — the file names carry complaint ids from every
    region, so an unrestricted listing would leak them across entitlements."""
    authz.require_admin(request)
    return documents.list_outbound()


class VoiceReq(BaseModel):
    transcript: str
    # Epoch seconds of the moment the officer is speaking, sent by the browser so the conduct window is
    # evaluated against the CALL's clock. Defaulting this server-side would be wrong: a demo replayed
    # at 10:00 must still be able to show the 21:45 refusal.
    at_epoch_seconds: Optional[int] = None


@app.post("/api/voice/assist")
def voice_assist(req: VoiceReq, request: Request):
    """Live agent-assist for a call in progress. Reads the account and grievance picture AS THE CALLER,
    then runs the RBI conduct checks as the service principal. Speech never reaches this endpoint —
    only the transcript the browser produced on the officer's own device."""
    if not (req.transcript or "").strip():
        raise HTTPException(400, "transcript is required")
    token = identity.user_token(request)
    if not token and config.REQUIRE_OBO:
        raise HTTPException(403, "no forwarded user token; refusing to read as the service principal")
    try:
        w = agent._user_genie_client(token) or dbx.client()
        return voice.assist(req.transcript[:4000], w=w, epoch_seconds=req.at_epoch_seconds)
    except Exception as e:
        raise _fail("voice_assist", e)


@app.get("/api/dashboard")
def dashboard():
    """The embedded AI/BI dashboard id, if one is configured."""
    return {"dashboard_id": config.DASHBOARD_ID or None,
            "workspace_host": dbx.client().config.host}


# ---- static frontend ------------------------------------------------------
# Mounted last so /api/* wins.
_HERE = os.path.dirname(os.path.abspath(__file__))
_DIST = os.path.normpath(os.path.join(_HERE, "..", "frontend", "dist"))

if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_DIST, "index.html"))

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Serve a built asset, else the SPA shell.

        The path is CONTAINMENT-CHECKED against the build directory. `os.path.join` happily returns
        an absolute path when the second argument is absolute, and resolves `..` not at all, so the
        obvious version of this handler will read any file the container can see — the app's own
        source, or /proc/self/environ with its injected credentials. Resolve, then verify the result
        is still inside the build root.
        """
        root = os.path.realpath(_DIST)
        shell = os.path.join(root, "index.html")
        candidate = os.path.realpath(os.path.join(root, full_path))
        if candidate != root and not candidate.startswith(root + os.sep):
            return FileResponse(shell)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(shell)
