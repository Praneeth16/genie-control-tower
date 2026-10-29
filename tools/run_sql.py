"""Run a SQL script from a job task, with ${PLACEHOLDER} substitution.

    run_sql.py --file governance/policies.sql --var CATALOG=main --var SCHEMA=control_tower_banking

Job tasks use this rather than a SQL file task because UC function bodies cannot take parameter markers:
the catalog and schema have to be literal text in the function, so they are substituted before the
statement is sent. A placeholder left unsubstituted fails the task instead of creating an object in the
wrong place.
"""
from __future__ import annotations

import argparse
import os
import re


def split_statements(text: str) -> list[str]:
    """Split on semicolons that end a line, ignoring -- comment lines and semicolons inside literals."""
    out, buf, in_str = [], [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_str and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        if len(re.findall(r"(?<!\\)'", line)) % 2 == 1:
            in_str = not in_str
        if not in_str and stripped.endswith(";"):
            out.append("\n".join(buf).strip().rstrip(";").strip())
            buf = []
    tail = "\n".join(buf).strip().rstrip(";").strip()
    return out + ([tail] if tail else [])


def render(text: str, values: dict[str, str]) -> str:
    for k, v in values.items():
        text = text.replace("${" + k + "}", v)
    left = sorted(set(re.findall(r"\$\{[A-Z_]+\}", text)))
    if left:
        raise SystemExit(f"unsubstituted placeholders: {left}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", action="append", required=True, help="SQL file, relative to the repo root")
    ap.add_argument("--var", action="append", default=[], help="KEY=VALUE placeholder substitution")
    # Serverless job tasks exec the file, so __file__ is undefined there; the bundle passes its root.
    ap.add_argument("--root", default=".", help="repo root the --file paths are relative to")
    a = ap.parse_args()
    values = dict(v.split("=", 1) for v in a.var)

    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    for f in a.file:
        stmts = split_statements(render(open(os.path.join(a.root, f)).read(), values))
        print(f"{f}: {len(stmts)} statements")
        for i, stmt in enumerate(stmts, 1):
            print(f"  [{i}/{len(stmts)}] {stmt.splitlines()[0][:110]}")
            spark.sql(stmt)
    return 0


if __name__ == "__main__":
    # Not sys.exit(main()): serverless job tasks run under IPython, which reports SystemExit(0) as a
    # failure. Errors raise; returning normally is success.
    main()
