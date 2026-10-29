"""Land the held-back period into the landing volume, the way a source system would: data files first,
the manifest last. The manifest arriving is what fires the cycle job's file-arrival trigger, so the run
starts only once the drop is complete.

    land_next_period.py --holdback /Volumes/<c>/<s>/holdback --landing /Volumes/<c>/<s>/landing

Copying an already-landed file again is harmless: Auto Loader ingests each path once.
"""
from __future__ import annotations

import argparse
import os
import shutil


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holdback", required=True)
    ap.add_argument("--landing", required=True)
    a = ap.parse_args()
    files = [os.path.relpath(os.path.join(d, f), a.holdback)
             for d, _, names in os.walk(a.holdback) for f in names]
    manifests = sorted(f for f in files if f.startswith("_manifests/"))
    data = sorted(f for f in files if not f.startswith("_manifests/"))
    if not manifests:
        raise SystemExit(f"nothing held back under {a.holdback}")
    for rel in data + manifests:
        dst = os.path.join(a.landing, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(a.holdback, rel), dst)
    print(f"landed {len(data)} data files, then {len(manifests)} manifest(s): {', '.join(manifests)}")


if __name__ == "__main__":
    main()
