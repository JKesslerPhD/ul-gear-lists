#!/usr/bin/env python3
"""Do the two collection routes (thread crawl vs public archive) describe the same population?  Base weight + Big 4."""
import random
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
conn = sqlite3.connect(ROOT / "data" / "ul_flair_lists.db")
rng = random.Random(1)
base = {c: [r[0] for r in conn.execute("SELECT base_weight_g FROM lists WHERE cohort=? AND base_weight_g>0", (c,))] for c in ("thread", "archive")}
for c, v in base.items():
    m = sorted(st.median(rng.choices(v, k=len(v))) for _ in range(2000))
    print(f"{c:8s} n={len(v):3d}  median base {st.median(v):6.0f} g  (95% CI {m[50]:.0f}-{m[1949]:.0f})")
d = sorted(st.median(rng.choices(base['thread'], k=len(base['thread']))) - st.median(rng.choices(base['archive'], k=len(base['archive']))) for _ in range(4000))
print(f"difference of medians (thread - archive): {st.median(base['thread']) - st.median(base['archive']):.0f} g, bootstrap 95% CI {d[100]:.0f} to {d[3899]:.0f}")
for role in ("pack", "shelter", "quilt", "pad"):
    out = []
    for c in ("thread", "archive"):
        w = [r[0] for r in conn.execute("""SELECT MAX(i.total_g) FROM items i JOIN lists l ON l.id=i.list_id
                                           WHERE l.cohort=? AND i.core_role=? AND i.consumable=0 GROUP BY i.list_id""", (c, role))]
        out.append(st.median(w))
    print(f"{role:8s} median  thread {out[0]:.0f} g | archive {out[1]:.0f} g")
