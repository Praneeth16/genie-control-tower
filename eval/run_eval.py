"""Benchmark the three Genie Agents against ground-truth SQL, and the supervisor's router against
the domain each question belongs to.

Run it:
    python3 eval/run_eval.py golden          # validate the benchmark itself — no Genie quota spent
    python3 eval/run_eval.py router          # router accuracy (30 LLM calls, no Genie quota)
    python3 eval/run_eval.py genie           # the real thing (30 Genie messages, rate limited)
    python3 eval/run_eval.py genie --only COL-01,GRV-03

Two numbers come out, and they must never be merged into one headline:

  * ROUTER accuracy — did the supervisor send the question to the right domain agent? A router miss
    is cheap to fix (one line of instructions) and has a different remedy from a Genie miss.
  * GENIE accuracy — did the domain agent return the right number, in both its result grid and its
    narrative? This is the number that decides whether a bank can trust the answer.

Identity, stated because an eval number is meaningless without it: this runs under the CLI profile,
i.e. as a human with UNRESTRICTED visibility, and the golden SQL runs as that same identity in the
same session. Row-filtered users see a subset, so their correct answers differ from these. This
measures the AGENT, holding governance constant — not the governance.

Genie quota is a workspace-wide rate of roughly 5 messages/minute, so a 30-question run takes about
eight minutes. That is why this is a script and not a request handler.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app", "backend"))
sys.path.insert(0, HERE)

# Auth comes from DATABRICKS_CONFIG_PROFILE / DATABRICKS_HOST, set in .env or the shell.
os.environ.setdefault("REQUIRE_OBO", "false")
# The eval must not write traces into the demo experiment; a benchmark run would swamp the handful of
# live demo traces the audience is shown.
os.environ.setdefault("TRACING_ENABLED", "false")

import config                      # noqa: E402
import databricks_client as dbx    # noqa: E402
import grader                      # noqa: E402

RESULTS = os.path.join(HERE, "results")
_HELDOUT = "--heldout" in sys.argv


def load_cases(only: set[str] | None = None, suite: str = "benchmarks") -> list[dict]:
    cases = []
    for path in sorted(glob.glob(os.path.join(HERE, suite, "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            # Routing-only cases carry no golden SQL: what is being graded is WHERE the question was
            # sent, which needs no ground-truth number.
            if c.get("golden_sql"):
                c["golden_sql"] = "\n".join(c["golden_sql"]).replace("{FQ}", config.FQ)
            if only is None or c["id"] in only:
                cases.append(c)
    return cases


def run_golden(case: dict) -> tuple[list[dict], str | None]:
    try:
        out = dbx.run_sql(case["golden_sql"])
        return out["rows"], None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"[:300]


# --------------------------------------------------------------------------------------- golden
def cmd_golden(cases: list[dict]) -> int:
    """Validate the benchmark before trusting any score from it. A benchmark whose golden SQL errors
    or returns nothing will happily report the agent as 0% correct."""
    bad = 0
    for c in cases:
        rows, err = run_golden(c)
        if err:
            print(f"  FAIL {c['id']}  {err}")
            bad += 1
            continue
        if not rows:
            print(f"  EMPTY {c['id']}  golden SQL returned no rows")
            bad += 1
            continue
        if c["grade"] == "scalar":
            shown = list(rows[0].values())[0]
        elif c["grade"] == "set":
            shown = {str(r[c["key"]]): r[c["value"]] for r in rows}
        else:
            shown = str(rows[0][c["key"]])
        print(f"  ok   {c['id']}  {c['grade']:<7} {shown}")
    print(f"\n{len(cases) - bad}/{len(cases)} golden queries valid")
    return 1 if bad else 0


# --------------------------------------------------------------------------------------- router
def cmd_router(cases: list[dict]) -> int:
    """Router accuracy over BOTH single-domain and cross-domain questions.

    Reported separately, because merging them flatters the router badly. Every accuracy case in this
    benchmark is single-domain by construction, and routing a question about DPD buckets to the
    collections agent is close to free. The router's real job is the cross-domain question — "why did
    complaints rise where delinquency rose" — where it must recognise that one question needs two
    agents, and must not reach for a third that will cost a Genie message and add nothing.

    So each case is scored three ways:
      * EXACT   — the routed set equals the expected set. The strict measure.
      * RECALL  — every expected domain was consulted. A missed domain means a blind spot in the answer.
      * WASTE   — domains consulted that nobody asked for, in Genie messages per question.
    """
    import agent
    results = []
    for c in cases:
        expected = c.get("expected_domains") or [c["domain"]]
        t0 = time.time()
        try:
            decision = agent.route(c["question"])
            got = decision["domains"]
            fallback = bool(decision.get("router_fallback"))
            err = None
        except Exception as e:
            got, fallback, err = [], True, f"{type(e).__name__}: {e}"[:200]
        exact = set(got) == set(expected)
        recall = bool(set(expected) & set(got)) and set(expected) <= set(got)
        waste = len(set(got) - set(expected))
        results.append({"id": c["id"], "expected": sorted(expected), "routed": got,
                        "kind": "cross-domain" if len(expected) > 1 else "single-domain",
                        "exact": exact, "full_recall": recall, "wasted_calls": waste,
                        "router_fallback": fallback, "error": err,
                        "elapsed_ms": int((time.time() - t0) * 1000)})
        flag = "ok  " if exact else ("part" if recall else "MISS")
        print(f"  {flag} {c['id']}  expected={sorted(expected)} routed={got}"
              + (f"  +{waste} wasted" if waste else "") + ("  [fallback]" if fallback else ""))

    def agg(rows: list[dict]) -> dict:
        n = len(rows)
        if not n:
            return {}
        return {"n": n,
                "exact_pct": round(100.0 * sum(r["exact"] for r in rows) / n, 1),
                "full_recall_pct": round(100.0 * sum(r["full_recall"] for r in rows) / n, 1),
                "wasted_calls_per_question": round(sum(r["wasted_calls"] for r in rows) / n, 2)}

    single = [r for r in results if r["kind"] == "single-domain"]
    cross = [r for r in results if r["kind"] == "cross-domain"]
    summary = {"overall": agg(results), "single_domain": agg(single), "cross_domain": agg(cross)}
    for label, block in summary.items():
        if block:
            print(f"\n{label:<14} n={block['n']:<3} exact {block['exact_pct']}%  "
                  f"full recall {block['full_recall_pct']}%  "
                  f"wasted Genie calls/question {block['wasted_calls_per_question']}")
    return _save("router", summary | {"cases": results})


# --------------------------------------------------------------------------------------- genie
def cmd_genie(cases: list[dict]) -> int:
    import agent
    w = dbx.client()
    results = []
    for i, c in enumerate(cases, 1):
        space_id = config.SPACE_IDS.get(c["domain"], "")
        expected_rows, gerr = run_golden(c)
        rec = {"id": c["id"], "domain": c["domain"], "question": c["question"],
               "pinned": bool(c.get("pinned")), "grade": c["grade"], "space_id": space_id}
        if gerr or not expected_rows:
            rec |= {"outcome": "benchmark_broken", "passed": False,
                    "detail": gerr or "golden SQL returned no rows"}
            results.append(rec)
            print(f"[{i:2}/{len(cases)}] {c['id']}  BENCHMARK BROKEN  {rec['detail']}")
            continue

        t0 = time.time()
        try:
            # Deliberately generous: the 95s turn budget exists to protect an interactive HTTP
            # request, and an eval is not one. Capping a benchmark at the UI's budget would report a
            # timeout as an accuracy failure, which is the wrong diagnosis and the wrong fix.
            leg = agent._genie_leg(space_id, c["question"], w=w,
                                   deadline=time.monotonic() + 240)
            g = grader.grade(c, expected_rows, leg["rows"], leg.get("description") or "")
            rec |= {"outcome": "pass" if g["passed"] else "wrong", "passed": g["passed"],
                    "matched_in": g["matched_in"], "detail": g["detail"],
                    "missing": g["missing"], "row_count": leg["row_count"],
                    "sql": leg["sql"], "narrative": (leg.get("description") or "")[:1200]}
        except agent.GenieThrottled as e:
            rec |= {"outcome": "throttled", "passed": False, "detail": str(e)[:300]}
        except Exception as e:
            rec |= {"outcome": "error", "passed": False, "detail": f"{type(e).__name__}: {e}"[:300]}
        rec["elapsed_ms"] = int((time.time() - t0) * 1000)
        results.append(rec)
        print(f"[{i:2}/{len(cases)}] {c['id']}  {rec['outcome'].upper():<17} "
              f"{rec['elapsed_ms']/1000:5.1f}s  {rec.get('detail','')[:110]}")

    return _save("genie", _summarise(results))


def _summarise(results: list[dict]) -> dict:
    graded = [r for r in results if r["outcome"] in ("pass", "wrong")]
    passed = [r for r in graded if r["passed"]]
    by_domain, by_outcome = {}, {}
    for r in results:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
        d = by_domain.setdefault(r["domain"], {"graded": 0, "passed": 0})
        if r["outcome"] in ("pass", "wrong"):
            d["graded"] += 1
            d["passed"] += bool(r["passed"])
    for d in by_domain.values():
        d["accuracy_pct"] = round(100.0 * d["passed"] / d["graded"], 1) if d["graded"] else None
    lat = [r["elapsed_ms"] for r in results if r.get("elapsed_ms")]
    return {
        # Two denominators, kept apart on purpose. Scoring a throttled question as "wrong" would
        # blame the agent for a workspace quota; hiding it would overstate the score. Report both.
        "accuracy_pct_of_graded": round(100.0 * len(passed) / len(graded), 1) if graded else None,
        "accuracy_pct_of_attempted": round(100.0 * len(passed) / len(results), 1) if results else None,
        "graded": len(graded), "passed": len(passed), "attempted": len(results),
        "by_outcome": by_outcome, "by_domain": by_domain,
        "latency_ms": {"p50": int(statistics.median(lat)) if lat else None,
                       "max": max(lat) if lat else None},
        "cases": results,
    }


def _save(kind: str, payload: dict) -> int:
    if _HELDOUT:
        kind = f"heldout-{kind}"
    os.makedirs(RESULTS, exist_ok=True)
    payload |= {"kind": kind, "run_at": datetime.now(timezone.utc).isoformat(),
                "identity": dbx.current_user(), "catalog": config.FQ,
                "warehouse_id": config.WAREHOUSE_ID, "space_ids": dict(config.SPACE_IDS)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(RESULTS, f"{kind}-{stamp}.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    latest = os.path.join(RESULTS, f"{kind}-latest.json")
    if os.path.exists(latest) or os.path.islink(latest):
        os.remove(latest)
    with open(latest, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwrote {path}")
    # Exit code reflects the RESULT, not merely that the run completed. Returning 0 after saving a file
    # full of wrong answers makes this useless in CI: the suite would go green on a regression.
    if kind.endswith("genie"):
        failed = [c for c in payload.get("cases", []) if not c.get("passed")]
        return 1 if failed else 0
    if kind.endswith("router"):
        overall = payload.get("overall") or {}
        return 0 if overall.get("exact_pct") == 100.0 else 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["golden", "router", "genie"])
    ap.add_argument("--only", default="", help="comma separated case ids")
    # The held-out suite exists to answer the one question the main benchmark cannot: how does the agent
    # do on questions that were never used to fix it? Its score is only worth anything the FIRST time it
    # runs. Once you tune against it, it has become another in-sample regression suite and you need a new
    # one — so record the first result and treat any later run as a regression check, not a fresh number.
    ap.add_argument("--heldout", action="store_true",
                    help="run eval/heldout/ instead of eval/benchmarks/ (never tune against this)")
    a = ap.parse_args()
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    cases = load_cases(only, suite="heldout" if a.heldout else "benchmarks")
    if a.cmd != "router":
        cases = [c for c in cases if c.get("golden_sql")]
    
    print(f"{len(cases)} cases · catalog {config.FQ} · identity {dbx.current_user()}\n")
    return {"golden": cmd_golden, "router": cmd_router, "genie": cmd_genie}[a.cmd](cases)


if __name__ == "__main__":
    sys.exit(main())
