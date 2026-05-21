#!/usr/bin/env python3
"""
Backfill keyword annotations for existing articles.
Re-runs keyword_match() on articles published since 2026-05-01
and updates matched_kw with any newly matching keywords (e.g. detonation engine terms).
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

import config
from monitor import init_db, keyword_match

conn = init_db()
rows = conn.execute(
    "SELECT id, title, summary, matched_kw FROM articles WHERE published >= '2026-05-01'"
).fetchall()
print(f"Found {len(rows)} articles since 2026-05-01")

updated = 0
for rid, title, summary, matched_kw in rows:
    new_matches = keyword_match(f"{title} {summary or ''}")
    if not new_matches:
        continue
    old_kw = [kw.strip() for kw in (matched_kw or "").split(",") if kw.strip()]
    combined = list(dict.fromkeys(old_kw + new_matches))  # merge + dedup
    new_kw_str = ", ".join(combined)
    if new_kw_str != matched_kw:
        conn.execute("UPDATE articles SET matched_kw = ? WHERE id = ?", (new_kw_str, rid))
        updated += 1
        if updated <= 5 or (updated <= 20 and updated % 5 == 0):
            print(f"  [{updated}] {title[:50]}... → kw updated")
        elif updated % 50 == 0:
            print(f"  [{updated}] ...")

conn.commit()
print(f"\nDone. Updated {updated} articles with new keywords.")
conn.close()
