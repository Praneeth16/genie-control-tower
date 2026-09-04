"""Grading rules for the Genie Agent benchmark.

Design note, because this is the part of an eval that is easiest to get quietly wrong:

A Genie answer is graded against a GROUND-TRUTH SQL RESULT, never against a reference string. The
golden SQL is executed at run time on the same warehouse, under the same identity, in the same
minute as the Genie call. That matters because these tables are a fixed synthetic snapshot but the
grader must not depend on that: a frozen expected value silently rots the moment anyone reloads the
data, and a rotted eval reports a model regression that never happened.

Two things are checked, and the report keeps them apart:
  * the numbers Genie RETURNED in its result grid, and
  * the numbers Genie SAID in its narrative.
The narrative is what a banker actually reads, so an answer whose grid is right and whose prose is
wrong is not a pass. `matched_in` records which surface carried the match.

Tolerance is RELATIVE, with an absolute floor of 0.15 so that a percentage the space rounds to one
decimal place is not marked wrong for rounding. A tolerance of 0.0 therefore still means "exact"
for integer counts, which is what the count questions want.
"""
from __future__ import annotations

import re
from typing import Any

ABS_FLOOR = 0.15

# Matches 1234, 1,234.5, 12.34, -5 — the shapes a number takes in Genie's prose. The lookarounds
# keep it from biting a fragment out of an identifier like CM0008812 or a date like 2026-06-14.
_NUM = re.compile(r"(?<![\w.-])-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?![\w-])|(?<![\w.-])-?\d+(?:\.\d+)?(?![\w-])")


def as_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").rstrip("%")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def numbers_in_rows(rows: list[dict]) -> list[float]:
    out = []
    for r in rows:
        for v in r.values():
            f = as_float(v)
            if f is not None:
                out.append(f)
    return out


def numbers_in_text(text: str) -> list[float]:
    """Numbers Genie stated in prose. Crore is expanded, because the space instructions tell Genie to
    use crore above 1e7 and a grader that does not understand that unit marks a correct answer wrong."""
    if not text:
        return []
    out = []
    for m in _NUM.finditer(text):
        f = as_float(m.group(0))
        if f is None:
            continue
        tail = text[m.end():m.end() + 12].lower()
        out.append(f)
        if "crore" in tail:
            out.append(f * 10_000_000)
        elif "lakh" in tail:
            out.append(f * 100_000)
    return out


def close(actual: float, expected: float, rel_tol: float) -> bool:
    return abs(actual - expected) <= max(ABS_FLOOR, rel_tol * abs(expected))


def _match_scalar(expected: float, pool: list[float], rel_tol: float) -> bool:
    return any(close(a, expected, rel_tol) for a in pool)


def grade(case: dict, expected_rows: list[dict], actual_rows: list[dict], narrative: str) -> dict:
    """Return {passed, matched_in, detail, expected, missing}."""
    rel = float(case.get("tolerance", 0.0))
    grade_type = case["grade"]
    row_pool = numbers_in_rows(actual_rows)
    txt_pool = numbers_in_text(narrative)

    if not expected_rows:
        return {"passed": False, "matched_in": None,
                "detail": "golden SQL returned no rows — the benchmark case is broken, not the agent",
                "expected": None, "missing": []}

    if grade_type == "scalar":
        exp = as_float(list(expected_rows[0].values())[0])
        in_rows = _match_scalar(exp, row_pool, rel)
        in_text = _match_scalar(exp, txt_pool, rel)
        passed = in_rows and in_text if narrative else in_rows
        where = "rows+narrative" if (in_rows and in_text) else "rows" if in_rows else "narrative" if in_text else None
        return {"passed": bool(passed), "matched_in": where, "expected": exp,
                "missing": [] if passed else [exp],
                "detail": f"expected {exp}; found in rows={in_rows}, in narrative={in_text}"}

    if grade_type == "set":
        kcol, vcol = case["key"], case["value"]
        # Some keys are real data — a region, a product code, an RBI ground — and the answer must name
        # them. Others are a LABEL THE BENCHMARK INVENTED for a band the question only describes in
        # words ("split by whether the mix score is below 0.50"). Requiring the agent to guess the
        # benchmark's private label for such a band grades wording, not correctness: RM-03 returned
        # both averages exactly right under the headings "Weak mix (<0.50)" and "Healthy mix (>=0.50)"
        # and was marked wrong. `key_aliases` lets a case say which spellings count.
        # Aliases are REGEXES, not literals. Enumerating phrasings turned into whack-a-mole: the case
        # accepted ">=0.50" and "at or above" and then met "0.50 or above". One pattern per band states
        # the intent — "this is the high-mix group, however you word it" — instead of a growing list.
        aliases = {k: [re.compile(a, re.IGNORECASE) for a in v]
                   for k, v in (case.get("key_aliases") or {}).items()}
        missing, hit_rows, hit_text = [], 0, 0
        for er in expected_rows:
            k, ev = str(er[kcol]), as_float(er[vcol])
            pats = [re.compile(re.escape(k), re.IGNORECASE)] + aliases.get(k, [])
            hay_rows = [" ".join(str(v) for v in ar.values()) for ar in actual_rows]
            key_seen = any(any(p.search(h) for p in pats) for h in hay_rows) \
                or any(p.search(narrative or "") for p in pats)
            v_rows = _match_scalar(ev, row_pool, rel)
            v_text = _match_scalar(ev, txt_pool, rel)
            if key_seen and v_rows:
                hit_rows += 1
            if key_seen and v_text:
                hit_text += 1
            if not (key_seen and (v_rows or v_text)):
                missing.append({"key": k, "expected": ev, "key_seen": key_seen})
        n = len(expected_rows)
        passed = hit_rows == n
        return {"passed": passed, "matched_in": "rows" if hit_rows == n else ("narrative" if hit_text == n else None),
                "expected": n, "missing": missing,
                "detail": f"{hit_rows}/{n} key-value pairs matched in rows, {hit_text}/{n} in narrative"}

    if grade_type == "topk":
        kcol = case["key"]
        top = str(expected_rows[0][kcol])
        first_row_txt = " ".join(str(v) for v in actual_rows[0].values()).lower() if actual_rows else ""
        in_rows = top.lower() in first_row_txt
        # The narrative must NAME the winner. "Indore leads" passes; a grid that happens to be sorted
        # correctly while the prose names a different city does not.
        in_text = top.lower() in (narrative or "").lower()
        passed = in_rows or in_text
        return {"passed": passed, "matched_in": "rows" if in_rows else ("narrative" if in_text else None),
                "expected": top, "missing": [] if passed else [top],
                "detail": f"expected top {kcol}={top!r}; first row match={in_rows}, named in narrative={in_text}"}

    raise ValueError(f"unknown grade type {grade_type!r}")
