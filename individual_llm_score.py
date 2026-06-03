#!/usr/bin/env python3
"""
Score unscored AAM articles through LLM individually (but concurrently).
Fixes the batch-mode where LLM responses don't match the expected regex format.
"""
import os
import re
import sys
import sqlite3
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("refilter")

BASE_DIR = Path(__file__).parent

os.environ["MONITOR_THEME"] = sys.argv[1] if len(sys.argv) > 1 else "aam"
DB_PATH = BASE_DIR / "data" / f"{os.environ['MONITOR_THEME']}.db"

sys.path.insert(0, str(BASE_DIR))
import config
from llm_client import create_completion

# Get the base filter prompt without the per-article template
FULL_PROMPT = config.LLM_FILTER_PROMPT
cut = FULL_PROMPT.find("Article title:")
PROMPT_TEMPLATE = FULL_PROMPT[:cut].strip() if cut > 0 else FULL_PROMPT
# Remove any trailing "Reply with ONLY" instruction since we control the output format
PROMPT_TEMPLATE = re.sub(r'\n+Reply with ONLY.*$', '', PROMPT_TEMPLATE, flags=re.DOTALL).strip()
PROMPT_TEMPLATE += """

Reply with "YES SCORE: N" or "NO SCORE: N" where N is relevance 0-10.
"""


def score_one(art_id: str, title: str, summary: str) -> tuple[str, bool, float]:
    """Score a single article. Returns (art_id, accepted, score_0_10)."""
    prompt = PROMPT_TEMPLATE + f"\nTitle: {title}\nSummary: {(summary or '')[:500]}"
    try:
        answer = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
        ).strip()
    except Exception as e:
        log.warning(f"LLM failed for {title[:40]}: {e}")
        return art_id, True, 5.0

    answer_upper = answer.upper()
    m = re.search(r"(YES|NO)\s+SCORE\s*[:：]\s*([\d.]+)", answer_upper)
    if m:
        accepted = m.group(1) == "YES"
        score = min(10.0, max(0.0, float(m.group(2))))
        return art_id, accepted, score

    # Fallback: simple YES/NO
    if "YES" in answer_upper and "NO" not in answer_upper:
        return art_id, True, 8.0
    if "NO" in answer_upper and "YES" not in answer_upper:
        return art_id, False, 2.0

    log.warning(f"Unparseable response for {title[:40]}: {answer[:80]}")
    return art_id, True, 5.0


def main():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    theme = os.environ["MONITOR_THEME"]

    rows = conn.execute(
        "SELECT id, title, summary FROM articles WHERE llm_relevance = 0 OR llm_relevance = 50"
    ).fetchall()
    conn.close()

    log.info(f"{theme}: scoring {len(rows)} articles individually...")

    if not rows:
        log.info("No articles need LLM filtering.")
        return

    results: dict[str, tuple[bool, float]] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(score_one, r[0], r[1], r[2]) for r in rows]
        for i, f in enumerate(as_completed(futures), 1):
            art_id, accepted, score = f.result()
            results[art_id] = (accepted, score)
            if i % 10 == 0:
                log.info(f"Progress: {i}/{len(rows)}")

    # Update DB
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    updated = 0
    rejected = 0
    for art_id, title, summary, _ in rows:
        accepted, score = results[art_id]
        llm_val = int(score * 10)
        if not accepted:
            llm_val = 10
            rejected += 1
            log.info(f"Rejected: {title[:60]}...")
        conn.execute(
            "UPDATE articles SET llm_relevance = ? WHERE id = ?",
            (llm_val, art_id)
        )
        updated += 1

    conn.commit()
    conn.close()
    log.info(f"Done: {updated} updated ({rejected} rejected)")

    # Show distribution
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    dist = conn.execute("SELECT llm_relevance, COUNT(*) FROM articles GROUP BY llm_relevance ORDER BY llm_relevance").fetchall()
    conn.close()
    log.info(f"LLM score distribution: {dict(dist)}")


if __name__ == "__main__":
    main()
