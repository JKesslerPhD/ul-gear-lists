#!/usr/bin/env python3
"""
Modal kit and top 5 per category, from out/slot_models.json (written by analysis/report.py).

Modal kit : for every slot carried by >= --min-share of lists, the most common NAMED product and its median weight.
Top 5     : per category, the five most common named products (share of all lists, median weight).
Writes out/modal_kit.csv and out/top5_by_category.csv.
"""
import csv
import json
import statistics as st
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "out"
GENERIC = {"(generic name)", "Merino (generic)", "Synthetic tee", "Fleece/liner gloves", "Wired earbuds", "Paper map", "Sunglasses",
           "Trucker/ball cap", "Beanie", "Wind pants", "Rain kilt / skirt", "Short-handle toothbrush", "Toothpaste tabs", "Chapstick",
           "ExOfficio / generic", "Wet wipes", "Alcohol stove", "Generic tarp / flat tarp", "Hammock (any)", "Borah / bivy-based",
           "Shamwow / pack towel", "Bandana", "Ibuprofen", "Benadryl", "DEET/picaridin", "Flip flops", "Merino tee"}
BIG = {"pack": "Pack", "shelter": "Shelter", "quilt": "Quilt / sleeping bag", "pad": "Sleeping pad"}
GROUP_NAMES = {"Cook": "Cooking", "Sleep": "Sleep & shelter extras", "Shelter": "Sleep & shelter extras"}


def modal(models, min_n=3):
    named = {m: v for m, v in models.items() if m not in GENERIC}
    if not named:
        return None
    m, v = max(named.items(), key=lambda x: x[1][0])
    return (m, v[0], v[1]) if v[0] >= min_n else None


def main():
    min_share = float(sys.argv[sys.argv.index("--min-share") + 1]) if "--min-share" in sys.argv else 0.5
    J = json.load(open(OUT / "slot_models.json"))
    N = J["n"]
    rows = []
    for role, label in BIG.items():
        b = J["big4"][role]
        mo = modal(b["models"])
        rows.append(dict(group="Big 4", slot=label, product=mo[0] if mo else "", lists=mo[1] if mo else "", share=round(b["n"] / N, 3),
                         weight_g=round(mo[2] if mo else b["median_g"]), worn=False))
    for name, s in J["slots"].items():
        if s["share"] < min_share:
            continue
        mo = modal(s["models"])
        rows.append(dict(group=s["group"], slot=name, product=mo[0] if mo else "", lists=mo[1] if mo else "", share=round(s["share"], 3),
                         weight_g=round(mo[2] if mo else s["median_g"]), worn=s["worn"]))
    with open(OUT / "modal_kit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    base = sum(r["weight_g"] for r in rows if not r["worn"])
    print(f"modal kit: {len(rows)} slots, {base:,} g ({base / 453.592:.1f} lb) excluding worn items")

    groups = {}
    for role, label in BIG.items():
        groups[label] = [(m, v[0], v[1]) for m, v in J["big4"][role]["models"].items() if m not in GENERIC]
    for g in ("Water", "Cook", "Electronics", "Clothing", "Health & hygiene", "Misc", "Sleep", "Shelter"):
        acc = {}
        for name, s in J["slots"].items():
            if s["group"] == g:
                for m, v in s["models"].items():
                    if m not in GENERIC:
                        a = acc.setdefault(m, [0, []])
                        a[0] += v[0]
                        a[1].append(v[1])
        key = GROUP_NAMES.get(g, g)
        groups.setdefault(key, []).extend((m, v[0], st.median(v[1])) for m, v in acc.items())
    with open(OUT / "top5_by_category.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "rank", "product", "lists", "share_of_all_lists", "median_weight_g"])
        for cat, items in groups.items():
            for rank, (m, n, g) in enumerate(sorted(items, key=lambda x: -x[1])[:5], 1):
                w.writerow([cat, rank, m, n, round(n / N, 3), round(g)])
    print(f"top 5 for {len(groups)} categories -> out/top5_by_category.csv")


if __name__ == "__main__":
    main()
