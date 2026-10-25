#!/usr/bin/env python3
"""Regression test: the classifier must reproduce the hand-checked picks in tests/verified_core_gear.csv.

    python tests/test_classifier.py            # compare (exit 1 on any change)
    python tests/test_classifier.py --update   # rewrite the verified file AFTER reviewing the diff
"""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ulgear import classifier as g  # noqa: E402

VERIFIED = ROOT / "tests" / "verified_core_gear.csv"


def current():
    conn = sqlite3.connect(g.DB)
    out = {}
    for l in g.load(conn).values():
        g.classify_list(l["items"])
        for r in g.ROLES:
            picks = sorted((i for i in l["items"] if i["role"] == r), key=lambda i: -i["w"])
            top = picks[0] if picks else None
            out[(l["id"], r)] = (top["name"][:60] if top else "", str(round(top["w"])) if top else "", top["role_via"] if top else "")
    return out


def main():
    cur = current()
    if "--update" in sys.argv or not VERIFIED.exists():
        with open(VERIFIED, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["list_id", "role", "item", "weight_g", "via"])
            for (lid, role), v in sorted(cur.items()):
                w.writerow([lid, role, *v])
        print(f"wrote {len(cur)} picks to {VERIFIED.name}")
        return 0
    ver = {(int(r["list_id"]), r["role"]): (r["item"], r["weight_g"], r["via"]) for r in csv.DictReader(open(VERIFIED))}
    diffs = [k for k in sorted(set(ver) | set(cur)) if ver.get(k, ("", "", ""))[:2] != cur.get(k, ("", "", ""))[:2]]
    for k in diffs[:40]:
        print(f"CHANGED list-{k[0]} {k[1]}:  was {ver.get(k)}  now {cur.get(k)}")
    missing = {r: sum(1 for (lid, rr), v in cur.items() if rr == r and not v[0]) for r in g.ROLES}
    print(f"{len(cur) // 4} lists; lists with no item found: {missing}; changed picks: {len(diffs)}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
