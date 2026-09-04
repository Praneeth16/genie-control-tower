"""Automated governance tests: does the masking actually hold, and are the controls actually attached?

This is the suite that was a known gap. It asserts properties, not vibes, and each test names the
failure it is defending against — because a governance test that nobody can explain gets deleted the
first time it goes red.

    python3 eval/governance_tests.py                # structural + data tests, no Genie quota
    python3 eval/governance_tests.py --with-genie   # also proves masking reaches Genie's PROSE (2 messages)

Identity note, and it decides how every result reads. The runner is in NONE of the privileged groups
(`<prefix>_ai_coe`, `<prefix>_pii_readers`, `<prefix>_auditors`) — verified, not assumed, because an
earlier draft of this file asserted the opposite and I nearly "fixed" a mask that was working perfectly.
So the suite sees MASKED output and can therefore test the controls end to end by simply selecting the
column, which is the strongest form available.

The non-vacuity test matters most and is easy to get wrong: seeing `V. Verma` does not prove a mask ran,
because the raw value could always have been `V. Verma`. A mask that protects nothing looks identical to
a mask that works. So the suite compares the governed table against the UNGOVERNED CSV the generator
wrote — raw `Vivaan Verma` against masked `V. Verma` — which is the only way to prove the control does
something rather than merely existing.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app", "backend"))
# Auth comes from DATABRICKS_CONFIG_PROFILE / DATABRICKS_HOST, set in .env or the shell.
os.environ.setdefault("TRACING_ENABLED", "false")

import config                      # noqa: E402
import databricks_client as dbx    # noqa: E402

FQ = config.FQ
CAT = config.CATALOG
SCH = config.SCHEMA

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"\n          {detail}" if detail else ""))


def q(sql: str) -> list[dict]:
    return dbx.run_sql(sql)["rows"]


# --------------------------------------------------------------------- masks: behaviour
def test_mask_behaviour() -> None:
    print("\n[1] Column mask behaviour — the pseudonym must hide the identifier without breaking joins")

    # Call the mask on literals. Under a privileged identity the CASE returns the input, so evaluate the
    # ELSE branch explicitly: that is the expression every non-privileged caller gets.
    rows = q(f"""
        SELECT customer_id,
               CONCAT('CU-', SUBSTR(SHA2(CONCAT('{config.PSEUDONYM_SALT}:', customer_id), 256), 1, 10)) AS masked
        FROM (SELECT explode(array('CU000001','CU000002','CU009000','CU000001')) AS customer_id)
    """)
    masked = [r["masked"] for r in rows]

    check("pseudonym has the documented shape CU-<10 hex>",
          all(re.fullmatch(r"CU-[0-9a-f]{10}", m) for m in masked),
          f"got {masked[:3]}")

    # The bug this defends: a constant mask ('CUXXXXXX') collapsed 9,660 complaints onto one key and
    # turned every join on customer_id into a cross join.
    check("mask is DETERMINISTIC — the same customer yields the same pseudonym, so joins survive",
          masked[0] == masked[3], f"CU000001 -> {masked[0]} and {masked[3]}")
    check("mask is INJECTIVE on the sample — distinct customers yield distinct pseudonyms",
          len(set(masked[:3])) == 3, f"{masked[:3]}")
    check("pseudonym does not leak the source identifier",
          not any("000001" in m or "009000" in m for m in masked))

    # Injectivity at full scale: a hash collision would silently merge two customers.
    row = q(f"""
        SELECT COUNT(*) AS n, COUNT(DISTINCT masked) AS d FROM (
          SELECT CONCAT('CU-', SUBSTR(SHA2(CONCAT('{config.PSEUDONYM_SALT}:', customer_id), 256), 1, 10)) AS masked
          FROM {FQ}.customer_portfolio)
    """)[0]
    check("no pseudonym collisions across the whole customer master",
          int(row["n"]) == int(row["d"]),
          f"{row['n']} customers -> {row['d']} distinct pseudonyms")

    # End-to-end, not just the function: what does the governed table actually return to this caller?
    live = q(f"SELECT customer_id FROM {FQ}.customer_portfolio LIMIT 20")
    vals = [r["customer_id"] for r in live]
    check("governed table returns ONLY pseudonymised customer ids to an unprivileged caller",
          all(re.fullmatch(r"CU-[0-9a-f]{10}", v) for v in vals), f"e.g. {vals[:2]}")
    names = [r["agent_name"] for r in q(f"SELECT agent_name FROM {FQ}.recovery_agents LIMIT 20")]
    check("governed table returns ONLY initialised person names to an unprivileged caller",
          all(re.fullmatch(r"[A-Z]\. \S+", n) for n in names), f"e.g. {names[:2]}")
    txt = q(f"SELECT complaint_text FROM {FQ}.complaints LIMIT 3")
    check("free-text narrative is redacted for an unprivileged caller",
          all("redacted" in str(r["complaint_text"]).lower() for r in txt),
          f"{txt[0]['complaint_text'][:60]!r}")

    nm = q("""SELECT name, CONCAT(SUBSTR(name,1,1), '. ', SPLIT(name,' ')[SIZE(SPLIT(name,' '))-1]) AS masked
              FROM (SELECT explode(array('Vikram Verma','Meera Mehta')) AS name)""")
    check("person names reduce to initial + surname, never the given name",
          all(r["masked"] == exp and r["name"].split()[0] not in r["masked"]
              for r, exp in zip(nm, ("V. Verma", "M. Mehta"))),
          f"{[r['masked'] for r in nm]}")


# --------------------------------------------------------------------- masks: non-vacuity
def test_masks_are_not_vacuous() -> None:
    """Prove the masks CHANGE something.

    This is the test that catches the most embarrassing kind of governance failure: a control listed in
    the panel, attached to the table, syntactically correct, and inert — because the underlying data
    never contained anything for it to hide. From inside SQL it is undetectable, since the masked and
    unmasked values are identical. The generator's CSV is the only available ground truth.
    """
    print("\n[1b] Non-vacuity — do the masks actually change the value?")
    import csv

    out_dir = os.path.join(ROOT, "data", "out")
    checks = [
        ("recovery_agents", "agent_name", "agent_id",
         lambda raw: " " in raw and not re.fullmatch(r"[A-Z]\. .+", raw)),
        ("loan_accounts", "customer_id", "loan_account_id",
         lambda raw: bool(re.fullmatch(r"CU[0-9]{6}", raw))),
    ]
    for table, column, key, raw_is_sensitive in checks:
        path = os.path.join(out_dir, f"{table}.csv")
        if not os.path.exists(path):
            check(f"{table}.{column} raw values available for comparison", False,
                  f"{path} not found — regenerate with data/generate_banking_data.py")
            continue
        with open(path) as fh:
            raw_rows = {r[key]: r[column] for _, r in zip(range(400), csv.DictReader(fh))}
        keys = list(raw_rows)[:25]
        placeholders = ", ".join(f":k{i}" for i in range(len(keys)))
        params = {f"k{i}": (k, "STRING") for i, k in enumerate(keys)}
        seen = {r[key]: r[column] for r in dbx.run_sql(
            f"SELECT {key}, {column} FROM {FQ}.{table} WHERE {key} IN ({placeholders})",
            parameters=params)["rows"]}

        sensitive = [k for k in seen if raw_is_sensitive(raw_rows[k])]
        check(f"{table}.{column}: the raw data really does contain sensitive values",
              bool(sensitive), f"e.g. {raw_rows[sensitive[0]]!r}" if sensitive
              else "nothing sensitive in the source — this mask would be inert")
        changed = [k for k in sensitive if seen[k] != raw_rows[k]]
        check(f"{table}.{column}: the mask CHANGES every sensitive value it is applied to",
              bool(sensitive) and len(changed) == len(sensitive),
              (f"raw {raw_rows[sensitive[0]]!r} -> governed {seen[sensitive[0]]!r} "
               f"({len(changed)}/{len(sensitive)} changed)") if sensitive else "")


# --------------------------------------------------------------------- masks: attachment
def test_controls_attached() -> None:
    print("\n[2] Are the controls ATTACHED? A correct mask on no table protects nothing")

    masks = q(f"""SELECT table_name, column_name, mask_name FROM {CAT}.information_schema.column_masks
                  WHERE table_schema = '{SCH}'""")
    masked_cols = {(r["table_name"], r["column_name"]) for r in masks}

    # Every table that physically carries customer_id must have it masked. This is the regression that
    # matters: someone adds a table, forgets the mask, and the identifier is in the clear.
    cust_cols = q(f"""SELECT table_name FROM {CAT}.information_schema.columns
                      WHERE table_schema = '{SCH}' AND column_name = 'customer_id'""")
    unmasked = sorted({r["table_name"] for r in cust_cols}
                      - {t for t, c in masked_cols if c == "customer_id"}
                      # The vector-index source is deliberately excluded: it carries no customer_id.
                      - {"document_index_source"})
    check("every table carrying customer_id has a column mask on it",
          not unmasked, f"unmasked: {unmasked}" if unmasked else f"{len(cust_cols)} columns checked")

    name_cols = q(f"""SELECT table_name, column_name FROM {CAT}.information_schema.columns
                      WHERE table_schema = '{SCH}' AND column_name IN ('agent_name','rm_name')""")
    unmasked_names = sorted({(r["table_name"], r["column_name"]) for r in name_cols} - masked_cols)
    check("every person-name column has a column mask on it",
          not unmasked_names, f"unmasked: {unmasked_names}" if unmasked_names else "")

    filters = q(f"""SELECT table_name, filter_name, target_columns
                    FROM {CAT}.information_schema.row_filters WHERE table_schema = '{SCH}'""")
    filtered = {r["table_name"] for r in filters}
    # Any table with a region or branch dimension is scoped data and must be filtered.
    scoped = q(f"""SELECT DISTINCT table_name FROM {CAT}.information_schema.columns
                   WHERE table_schema = '{SCH}' AND column_name IN ('region','branch_id')
                     AND table_name NOT IN ('branch_master','region_entitlement','document_index_source')""")
    unfiltered = sorted({r["table_name"] for r in scoped} - filtered)
    check("every table with a region or branch dimension has a row filter",
          not unfiltered, f"unfiltered: {unfiltered}" if unfiltered else
          f"{len(filtered)} tables filtered")

    check("free-text complaint narrative is masked",
          ("complaints", "complaint_text") in masked_cols)


# --------------------------------------------------------------------- fairness / structural
def test_no_region_structurally_invisible() -> None:
    print("\n[3] Fairness — can any region's problems be structurally hidden?")

    regions = {r["region"] for r in q(f"SELECT DISTINCT region FROM {FQ}.branch_master")}
    ent = {r["region"] for r in q(f"SELECT DISTINCT region FROM {FQ}.region_entitlement")}
    covered = regions if "ALL" in ent else regions & ent
    check("every operating region is reachable through some entitlement",
          not (regions - covered),
          f"regions with no entitlement: {sorted(regions - covered)}" if regions - covered
          else f"{len(regions)} regions covered")

    # The guardrail identity must see the whole book, or a control can be blinded into approving anything.
    from action_plane import guardrails
    seen = guardrails.assert_not_blinded()
    check("guardrail identity is not blinded (verified against the generated manifest)",
          not seen["blinded"], f"source: {seen.get('expected_source')}")

    # And the check must be capable of failing, or it proves nothing.
    saved = dict(guardrails.EXPECTED_VISIBILITY)
    guardrails.EXPECTED_VISIBILITY = {**saved, "complaints": saved["complaints"] + 1}
    try:
        guardrails.assert_not_blinded()
        fired = False
    except guardrails.GuardrailsBlinded:
        fired = True
    finally:
        guardrails.EXPECTED_VISIBILITY = saved
    check("the blinding check actually fires when visibility is short", fired)


# --------------------------------------------------------------------- corpus / index leakage
def test_corpus_and_index() -> None:
    print("\n[4] Unstructured lane — PII in documents, and the index that copies them")

    docs = q(f"""SELECT COUNT(*) AS n,
                        SUM(CASE WHEN document_text RLIKE '(?i)name withheld' THEN 1 ELSE 0 END) AS withheld
                 FROM {FQ}.complaint_documents WHERE document_type = 'customer_letter'""")[0]
    check("every customer letter withholds the customer's name",
          int(docs["n"]) > 0 and int(docs["n"]) == int(docs["withheld"]),
          f"{docs['withheld']}/{docs['n']} letters")

    # A raw CU000123-style id in the corpus would defeat the pseudonym everywhere else.
    leak = q(f"""SELECT COUNT(*) AS n FROM {FQ}.complaint_documents
                 WHERE document_text RLIKE 'CU[0-9]{{6}}'""")[0]
    check("no raw customer identifier appears in any document",
          int(leak["n"]) == 0, f"{leak['n']} documents contain a CU###### token")

    try:
        idx = q(f"""SELECT COUNT(*) AS n,
                           SUM(CASE WHEN document_text RLIKE 'CU[0-9]{{6}}' THEN 1 ELSE 0 END) AS leaks
                    FROM {FQ}.document_index_source""")[0]
        check("no raw customer identifier in the Vector Search source (the index is an UNGOVERNED copy)",
              int(idx["leaks"]) == 0, f"{idx['n']} indexed documents, {idx['leaks']} leaking")
    except Exception as e:
        check("vector index source present", False, f"{type(e).__name__}: {e}"[:120])


# --------------------------------------------------------------------- Genie prose
def test_genie_prose(enabled: bool) -> None:
    print("\n[5] Does masking reach Genie's PROSE, not just the result grid?")
    if not enabled:
        print("          skipped (pass --with-genie; costs 2 Genie messages)")
        return
    import agent
    w = dbx.client()
    for question, want in (
        ("List three recovery agents by name with their agency and how many complaints are against them.",
         "agent_name"),
        ("Show me five customer ids from the complaints table with their complaint status.",
         "customer_id"),
    ):
        try:
            leg = agent._genie_leg(config.SPACE_IDS["COLLECTIONS" if want == "agent_name" else "GRIEVANCE"],
                                   question, w=w)
        except Exception as e:
            check(f"Genie answered ({want})", False, f"{type(e).__name__}: {e}"[:140])
            continue
        blob = (leg.get("description") or "") + " " + str(leg.get("rows"))
        if want == "customer_id":
            raw = re.findall(r"\bCU[0-9]{6}\b", blob)
            check("Genie's narrative and rows contain NO raw customer identifier",
                  not raw, f"leaked: {raw[:3]}" if raw else "only CU-<hash> pseudonyms present")
            check("the pseudonymised form IS present (so the mask ran rather than the column being dropped)",
                  bool(re.search(r"CU-[0-9a-f]{10}", blob)))
        else:
            # A masked name is "V. Verma". A full given name would mean the mask did not reach the prose.
            full = re.findall(r"\b(?:Vikram|Meera|Anil|Priya|Rahul|Sunita|Arjun)\s+[A-Z][a-z]+", blob)
            check("Genie's narrative contains no full personal name",
                  not full, f"leaked: {full[:3]}" if full else "initial + surname only")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-genie", action="store_true")
    a = ap.parse_args()
    print(f"governance tests · {FQ} · identity {dbx.current_user()}")
    test_mask_behaviour()
    test_masks_are_not_vacuous()
    test_controls_attached()
    test_no_region_structurally_invisible()
    test_corpus_and_index()
    test_genie_prose(a.with_genie)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} governance assertions passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
