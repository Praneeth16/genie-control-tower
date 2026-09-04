"""Lakebase (managed Postgres) access — the SHARED write-back module.

This is the WRITE plane, and it exists because Genie must never write: Genie
generates SQL from untrusted natural language, so its run-as identity holds SELECT
only. The approval state machine, action lineage and session memory live here
instead. Auth is a short-lived DB credential minted through the SDK (no stored
password anywhere), psycopg3, sslmode=require, search_path pinned to the
project's own schema.

The credential is short-lived (~1h), so we cache it and transparently refresh on
expiry. `query()` / `execute()` open a fresh autocommit connection per call —
simple and correct for an app's low write volume; swap in a pool later if needed.
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql as psql
from psycopg.rows import dict_row

from databricks_client import client, current_user

import config

INSTANCE_NAME = config.LAKEBASE_INSTANCE
DB_NAME = config.LAKEBASE_DBNAME
PG_SCHEMA = config.LAKEBASE_SCHEMA

_lock = threading.Lock()
_host: str | None = None
_token: str | None = None
_token_exp: float = 0.0
# Refresh a little before the ~1h expiry to avoid mid-request failures.
_TOKEN_TTL_SECONDS = 45 * 60


def _read_write_host() -> str:
    global _host
    if _host is None:
        with _lock:
            if _host is None:
                inst = client().database.get_database_instance(name=INSTANCE_NAME)
                _host = inst.read_write_dns
    return _host


def _db_token() -> str:
    """Short-lived Lakebase credential — the app/service write identity. Cached + refreshed."""
    global _token, _token_exp
    now = time.time()
    if _token is None or now >= _token_exp:
        with _lock:
            # Re-check inside the lock (another thread may have just refreshed).
            if _token is None or time.time() >= _token_exp:
                cred = client().database.generate_database_credential(instance_names=[INSTANCE_NAME])
                _token = cred.token
                _token_exp = now + _TOKEN_TTL_SECONDS
    return _token


@contextmanager
def connection():
    """Open an autocommit psycopg connection with search_path set to the project's schema.

    Rows come back as dicts. Transparently retries once with a fresh token if the
    cached credential has expired.
    """
    global _token

    def _connect() -> psycopg.Connection:
        return psycopg.connect(
            host=_read_write_host(), port=5432, dbname=DB_NAME,
            user=current_user(), password=_db_token(), sslmode="require",
            autocommit=True, row_factory=dict_row,
        )

    stale_token = _token
    try:
        conn = _connect()
    except psycopg.OperationalError:
        # Likely an expired token — force a refresh and retry once.
        #
        # The invalidation happens UNDER THE LOCK and only clears the token we actually failed with.
        # Clearing unconditionally outside the lock meant that when several threads failed on one
        # revoked credential, each of them wiped a token a sibling thread had just minted, producing
        # one credential-generation call per failing thread and a second wave of throttling.
        with _lock:
            if _token is stale_token:
                _token = None
        conn = _connect()

    try:
        with conn.cursor() as cur:
            cur.execute(
                psql.SQL("SET search_path TO {}").format(psql.Identifier(PG_SCHEMA))
            )
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    """Run a read query, return list-of-dicts."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params: tuple | None = None, returning: bool = False):
    """Run a write. If returning=True, fetch and return the first row (a dict)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        if returning:
            return cur.fetchone()
        return None
