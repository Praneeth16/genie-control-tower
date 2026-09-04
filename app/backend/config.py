"""Single source of truth for every environment-bound name this app uses.

Why this module exists: the forked scaffold read os.environ in six different places with six
different fallback defaults, so a wrong warehouse id could be right in one module and stale in
another. Everything is resolved once, here, and imported.

In Databricks Apps every value below arrives from app.yaml `env:`, which the Databricks Asset Bundle
generates from its own variables. Locally they come from a `.env` file or the shell.

There are deliberately NO workspace-specific defaults. An earlier version defaulted to the workspace it
was built in, which is fine until someone installs it elsewhere and the app comes up pointing at a
catalog they cannot see — succeeding at connecting, failing at everything after. Anything environment-
bound that is missing raises at import with a message naming the variable, so a misconfiguration fails
at startup rather than mid-demo.
"""
from __future__ import annotations

import json
import os
from typing import Final


def _load_dotenv() -> None:
    """Load a local .env if present. Deliberately hand-rolled: this is the FIRST thing config does, so
    depending on python-dotenv would make a third-party import a hard prerequisite of the app starting.
    In Databricks Apps no .env exists and every value arrives from app.yaml, so this is a no-op there.
    Existing environment variables always win — a shell export must beat a stale file.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, "..", ".env"),                       # app/.env
                      os.path.join(here, "..", "..", ".env")):                # repo root
        path = os.path.normpath(candidate)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        break


_load_dotenv()


def _env(name: str, default: str = "", *aliases: str) -> str:
    """First non-empty of `name` then any alias, else the default."""
    for key in (name, *aliases):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return default.strip()


def _required(name: str, hint: str = "", *aliases: str) -> str:
    """An environment-bound name with no sane default. Fail loudly at import."""
    value = _env(name, "", *aliases)
    if not value:
        raise RuntimeError(
            f"{name} is not set. In Databricks Apps it comes from app.yaml, which the bundle generates "
            f"from databricks.yml variables; locally, copy app/.env.example to .env and fill it in."
            + (f" {hint}" if hint else ""))
    return value


# --- Unity Catalog -----------------------------------------------------------
CATALOG: Final = _required("CT_CATALOG", "The Unity Catalog holding the workshop schema.")
SCHEMA: Final = _env("CT_SCHEMA", "control_tower_banking")
FQ: Final = f"{CATALOG}.{SCHEMA}"          # fully-qualified prefix for governed reads

# --- Compute -----------------------------------------------------------------
WAREHOUSE_ID: Final = _required("DATABRICKS_WAREHOUSE_ID", "A serverless SQL warehouse id.")
CHAT_ENDPOINT: Final = _env("DATABRICKS_CHAT_ENDPOINT", "databricks-claude-opus-4-8")

# --- Lakebase (app state: actions, approvals, sessions) ----------------------
# The instance name is deliberately not assumed: Lakebase has a per-workspace instance quota, so an
# installer may well have to point at an existing instance rather than create one. State is isolated by
# SCHEMA (LAKEBASE_SCHEMA), not by instance, so sharing an instance with another project is safe.
LAKEBASE_INSTANCE: Final = _required("LAKEBASE_INSTANCE", "A Lakebase (serverless Postgres) instance name.")
LAKEBASE_DBNAME: Final = _env("LAKEBASE_DBNAME", "databricks_postgres")
LAKEBASE_SCHEMA: Final = _env("LAKEBASE_SCHEMA", "control_tower")

# --- Genie Agents ------------------------------------------------------------
# Created config-as-code by genie/create_genie_agents.py; ids recorded in genie/space_ids.json.
# A blank id makes that domain leg fall back to instruction-driven text2sql over the bundled
# *_space.md, so the app degrades instead of going dark.
SPACE_IDS: Final = {
    "COLLECTIONS": _env("COLLECTIONS_SPACE_ID"),
    "GRIEVANCE": _env("GRIEVANCE_SPACE_ID"),
    "RM": _env("RM_SPACE_ID"),
}

# --- Request budget and quota ------------------------------------------------
# Databricks Apps terminates an HTTP request at 120s. The turn budget is deliberately BELOW that so
# the app returns a partial, honest answer instead of having the proxy cut the connection while
# background threads keep spending Genie quota on a reply nobody will ever see.
TURN_BUDGET_SECONDS: Final = int(_env("TURN_BUDGET_SECONDS", "95"))

# Genie's Conversation API allows roughly 5 messages/minute for the WHOLE workspace. Budget 4 to keep
# headroom for a colleague's interactive Genie session during the same demo.
GENIE_MESSAGES_PER_MINUTE: Final = int(_env("GENIE_MESSAGES_PER_MINUTE", "4"))

# Never consult more domains than this in one turn, whatever the router says. Three is the number of
# registered agents; a router that returns more is malfunctioning, and honouring it would spend the
# workspace's entire message budget on one question.
MAX_DOMAINS_PER_TURN: Final = int(_env("MAX_DOMAINS_PER_TURN", "3"))

# --- Identity ----------------------------------------------------------------
# When true, a request WITHOUT a forwarded user token is refused rather than served as the app
# service principal. In Apps that fallback is a privilege escalation: it would read the whole book
# for a user entitled to one region. Set false only for local development.
REQUIRE_OBO: Final = _env("REQUIRE_OBO", "false").lower() in ("1", "true", "yes")

# --- MLflow tracing ----------------------------------------------------------
MLFLOW_EXPERIMENT: Final = _env("MLFLOW_EXPERIMENT", "/Shared/genie-control-tower")
TRACING_ENABLED: Final = _env("TRACING_ENABLED", "true").lower() not in ("0", "false", "no")

# --- Volumes (unstructured lane) --------------------------------------------
VOLUME: Final = _env("CT_VOLUME", "docs")
VOLUME_ROOT: Final = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

# --- Embedded AI/BI dashboard ------------------------------------------------
# Built and published config-as-code by dashboards/build_dashboard.py. Published deliberately
# WITHOUT embedded credentials, so each viewer's own row filters and column masks apply to the
# dashboard exactly as they apply to the Genie Agents — the two surfaces cannot disagree.
DASHBOARD_ID: Final = _env("DASHBOARD_ID")

# --- Vector Search (semantic retrieval over the letter corpus) ---------------
# Blank disables the Documents tab's search box and the app says so, rather than erroring: the index is
# optional and the structured lane works without it.
VS_ENDPOINT: Final = _env("VS_ENDPOINT")
VS_INDEX: Final = _env("VS_INDEX", f"{FQ}.document_index" if CATALOG else "")

# --- Governance naming -------------------------------------------------------
# Account-group prefix for the entitlement and masking groups (<prefix>_ai_coe, <prefix>_pii_readers, ...).
# Parameterised so the governance model is not stamped with one customer's name.
GROUP_PREFIX: Final = _env("GROUP_PREFIX", "control_tower")

# Salt for the customer-id pseudonym. It must be identical everywhere and STABLE FOREVER: change it and
# every pseudonym changes, so any join against data masked with the old salt silently returns nothing.
# A literal default is acceptable for a synthetic workshop; in production this belongs in a secret scope.
PSEUDONYM_SALT: Final = _env("PSEUDONYM_SALT", "control-tower-pseudonym-v1")

# --- The institution this demo depicts ---------------------------------------
# A CONFIG VALUE with a deliberately unmistakable default, because the generator writes customer
# correspondence — letterheads, grievance intake forms, compliance notes. Fabricated records bearing a
# real institution's name are the one thing in this project that must never ship publicly, however clearly
# the surrounding text is marked synthetic: a reader who sees only the letter sees a real bank's name on a
# complaint that never happened. "Demo Retail Bank" cannot be mistaken for anyone.
#
# Set BANK_NAME to the institution being presented to when running a workshop for a specific customer.
BANK_NAME: Final = _env("BANK_NAME", "Demo Retail Bank")

# --- Demo posture ------------------------------------------------------------
# Every row of data in this workspace is SYNTHETIC. Surfaced in the UI and in the audit trail so a
# screenshot can never be mistaken for real customer data.
DATA_IS_SYNTHETIC: Final = True

# The bank's operating regions, as present in branch_master. Used by the guardrail region check.
REGIONS: Final = ["North", "South", "East", "West", "Central"]


def space_ids_from_file(path: str) -> dict[str, str]:
    """Read genie/space_ids.json (lowercase keys) into the UPPERCASE domain keys used here.
    Only used by local tooling; the app itself takes ids from env."""
    with open(path) as f:
        raw = json.load(f)
    return {k.upper(): v for k, v in raw.items()}
