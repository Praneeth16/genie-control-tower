"""Text2SQL — the SHARED natural-language-to-governed-SQL module.

THE FALLBACK LANE, not the main one. When a Genie Agent is unreachable this takes the same space
definition as a system prompt, asks the chat model for one Spark SQL statement, and runs it on the
governed warehouse — so a domain stays answerable without Genie's own reasoning or benchmarking.
Prefer the real Genie Agent whenever it is available; this exists so one revoked grant degrades a
single lane instead of blanking the app.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

import config
import databricks_client as dbx

# The three space definitions are bundled inside backend/ so the app is self-contained when Apps
# deploys it standalone; the repo copy under genie/ is the editing source of truth. Callers always
# pass an explicit path, so this default only matters if one forgets to.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BUNDLED = os.path.join(_HERE, "collections_space.md")
_REPO = os.path.normpath(os.path.join(_HERE, "..", "..", "genie", "collections_space.md"))
_DEFAULT_GENIE = os.environ.get(
    "GENIE_INSTRUCTIONS_PATH",
    _BUNDLED if os.path.isfile(_BUNDLED) else _REPO,
)

_SYSTEM_PREAMBLE = """You are a Spark SQL generator for a governed Databricks lakehouse.
Use ONLY the tables, columns, and business definitions described below. Never invent columns.
Return a SINGLE Spark SQL statement that answers the question — no commentary, no markdown
fences, no trailing semicolon explanation. If the question cannot be answered from these tables,
return exactly: SELECT 'out_of_scope' AS error.

Domain instructions:
---
{instructions}
---
Output ONLY the SQL.
"""


@lru_cache(maxsize=8)
def _instructions(path: str) -> str:
    """Load a domain's instruction document, substituting the deployment's own catalog and schema.

    The documents are templated with ${FQ} / ${CATALOG} / ${SCHEMA} rather than a literal catalog name.
    They used to hardcode the catalog they were authored against, which meant this fallback — the path
    taken when a Genie space id is missing or its grant is revoked — generated SQL against a catalog the
    installing workspace does not have. It would have failed on every question, in the one code path
    whose entire purpose is to keep working when something else has broken.
    """
    with open(path, "r") as f:
        text = f.read()
    for key, value in (("${FQ}", config.FQ), ("${CATALOG}", config.CATALOG),
                       ("${SCHEMA}", config.SCHEMA)):
        text = text.replace(key, value)
    return text


def _strip_sql(text: str) -> str:
    """Pull a clean SQL statement out of a model response (handles code fences)."""
    t = text.strip()
    fence = re.search(r"```(?:sql)?\s*(.+?)```", t, re.DOTALL | re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    return t.rstrip(";").strip()


def generate_sql(question: str, genie_instructions_path: str | None = None) -> str:
    """NL question -> Spark SQL string, grounded in the domain Genie instructions."""
    path = genie_instructions_path or _DEFAULT_GENIE
    system = _SYSTEM_PREAMBLE.format(instructions=_instructions(path))
    raw = dbx.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        max_tokens=1800,
    )
    return _strip_sql(raw)


def ask(question: str, genie_instructions_path: str | None = None, w=None) -> dict:
    """NL question -> {sql, columns, rows, row_count}. The full text2sql round trip.

    `w` is the identity the generated SQL EXECUTES as, and it must be the end user's client whenever
    one exists. This lane is a fallback for a Genie outage, and a fallback that quietly runs as the
    app service principal would hand a West-region user the whole country's book the moment Genie
    returned an error — a governance bypass triggered by an unrelated failure. The LLM call that
    writes the SQL stays on the service principal (it touches no customer data); only the execution
    is bound to the caller.
    """
    sql = generate_sql(question, genie_instructions_path)
    result = dbx.run_sql(sql, w=w)
    return {"sql": sql, **result}
