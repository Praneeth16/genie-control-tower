"""Build the Vector Search index over the complaint document corpus.

Why this exists at all: the structured lane already answers "how many recovery-conduct complaints in
Solapur" perfectly well in SQL. What SQL cannot do is find *"letters where the borrower says the agent
came after dark and spoke to their self-help group"* — that phrasing appears nowhere as a column. The
letters are 713 free-text narratives with five different conduct stories in them, which is exactly the
shape where retrieval earns its place. Below a few hundred documents it would be theatre.

    python3 scripts/build_vector_index.py --create     # source table, CDF, index
    python3 scripts/build_vector_index.py --status
    python3 scripts/build_vector_index.py --query "agent visited after dark and told my neighbours"

GOVERNANCE WARNING, and it belongs in the demo rather than a footnote:
A Vector Search index is a COPY of the text, held outside the governed table. Unity Catalog row filters
and column masks on `complaint_documents` do NOT follow the data into the index — an index built by a
privileged identity and queried by anyone is a way around the very controls this project spends its time
demonstrating. Two things follow, and both are done here:
  * The indexed text contains no customer names by construction (the generator writes "name withheld"),
    so the corpus is narrative and identifiers, not identity.
  * The index is a separate UC securable and must be granted deliberately. It is NOT granted to the app's
    end users; the app queries it as the service principal and returns only complaint ids, which the
    caller then reads back through the governed table under their OWN entitlements. Retrieval finds the
    document; governance still decides whether you may read it.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "backend"))
# Auth comes from DATABRICKS_CONFIG_PROFILE / DATABRICKS_HOST, set in .env or the shell.

import config  # noqa: E402

ENDPOINT = os.environ.get("VS_ENDPOINT", "")
SOURCE = f"{config.FQ}.document_index_source"
INDEX = os.environ.get("VS_INDEX") or f"{config.FQ}.document_index"
EMBEDDING = os.environ.get("VS_EMBEDDING_ENDPOINT", "databricks-gte-large-en")

if not ENDPOINT:
    raise SystemExit(
        "VS_ENDPOINT is not set. Vector Search endpoints are not created by this script because they are "
        "a shared, billable, per-workspace resource — list yours with "
        "`databricks vector-search-endpoints list-endpoints`, or create one, then set VS_ENDPOINT.")


def _w():
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient()


def build_source() -> None:
    import databricks_client as dbx
    # A dedicated source table rather than indexing complaint_documents directly: the index needs a
    # genuinely unique primary key, and complaint_documents has one row per FILE, including agency
    # agreements with no complaint_id at all. Change Data Feed is required for a delta-sync index.
    dbx.run_sql(f"""
        CREATE OR REPLACE TABLE {SOURCE} (
          doc_id        STRING  COMMENT 'Unique key for the vector index. file_path is the natural key.',
          complaint_id  STRING  COMMENT 'Complaint this document belongs to; NULL for agency and policy documents.',
          document_type STRING  COMMENT 'customer_letter, agency_agreement, compliance_note.',
          rbi_ground    STRING  COMMENT 'RBI ground of complaint, carried for metadata filtering.',
          city          STRING  COMMENT 'Branch city, carried for metadata filtering.',
          status        STRING  COMMENT 'Complaint status at capture.',
          document_text STRING  COMMENT 'Full document text. Synthetic. Contains no customer names.'
        )
        TBLPROPERTIES (delta.enableChangeDataFeed = true)
        COMMENT 'Flattened source for the Vector Search index over the document corpus. All synthetic.'
    """)
    dbx.run_sql(f"""
        INSERT INTO {SOURCE}
        SELECT d.file_path AS doc_id,
               d.complaint_id,
               d.document_type,
               cc.rbi_category AS rbi_ground,
               b.city,
               c.status,
               d.document_text
        FROM {config.FQ}.complaint_documents d
        LEFT JOIN {config.FQ}.complaints c ON d.complaint_id = c.complaint_id
        LEFT JOIN {config.FQ}.complaint_categories cc ON c.category_code = cc.category_code
        LEFT JOIN {config.FQ}.branch_master b ON c.branch_id = b.branch_id
    """)
    out = dbx.run_sql(f"SELECT COUNT(*) n, COUNT(DISTINCT doc_id) ids FROM {SOURCE}")
    row = out["rows"][0]
    print(f"source table {SOURCE}: {row['n']} rows, {row['ids']} distinct doc_id")
    if row["n"] != row["ids"]:
        raise SystemExit("doc_id is not unique — the index would silently drop rows")


def create_index() -> None:
    from databricks.sdk.service.vectorsearch import (
        DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn, PipelineType, VectorIndexType)
    w = _w()
    existing = [i.name for i in w.vector_search_indexes.list_indexes(endpoint_name=ENDPOINT)]
    if INDEX in existing:
        print(f"index exists, syncing: {INDEX}")
        w.vector_search_indexes.sync_index(index_name=INDEX)
        return
    w.vector_search_indexes.create_index(
        name=INDEX, endpoint_name=ENDPOINT, primary_key="doc_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=SOURCE,
            # TRIGGERED, not CONTINUOUS: this corpus is regenerated in batches, and a continuous
            # pipeline would bill for compute sitting idle between workshops.
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[
                EmbeddingSourceColumn(name="document_text", embedding_model_endpoint_name=EMBEDDING)],
            columns_to_sync=["doc_id", "complaint_id", "document_type", "rbi_ground", "city",
                             "status", "document_text"],
        ))
    print(f"created index {INDEX} on {ENDPOINT} using {EMBEDDING}")


def status() -> str:
    w = _w()
    ix = w.vector_search_indexes.get_index(index_name=INDEX)
    st = ix.status
    detail = getattr(st, "message", "") or ""
    ready = bool(getattr(st, "ready", False))
    print(f"{INDEX}\n  ready={ready}  indexed_rows={getattr(st, 'indexed_row_count', None)}  {detail[:120]}")
    return "READY" if ready else "PENDING"


def query(text: str, k: int = 5, ground: str | None = None) -> None:
    w = _w()
    flt = {"rbi_ground": ground} if ground else None
    res = w.vector_search_indexes.query_index(
        index_name=INDEX, columns=["complaint_id", "rbi_ground", "city", "status", "document_text"],
        query_text=text, num_results=k, filters_json=None if not flt else __import__("json").dumps(flt))
    rows = (res.result.data_array if res.result else []) or []
    print(f'\nquery: "{text}"' + (f"  [ground={ground}]" if ground else ""))
    for r in rows:
        cid, gnd, city, st, txt = r[0], r[1], r[2], r[3], r[4]
        score = r[-1]
        snippet = " ".join(str(txt).split())
        # Show the sentence that actually matched, not the letterhead.
        low = snippet.lower()
        for kw in text.lower().split():
            if len(kw) > 4 and kw in low:
                i = low.index(kw)
                snippet = "…" + snippet[max(0, i - 90): i + 130] + "…"
                break
        print(f"  {score:.4f}  {cid}  {gnd:<20} {city:<12} {st:<24}")
        print(f"           {snippet[:190]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--ground", default="")
    ap.add_argument("--wait", action="store_true", help="poll until the index is ready")
    a = ap.parse_args()
    if a.create:
        build_source()
        create_index()
    if a.wait:
        for _ in range(60):
            if status() == "READY":
                break
            time.sleep(20)
    elif a.status:
        status()
    if a.query:
        query(a.query, ground=a.ground or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
