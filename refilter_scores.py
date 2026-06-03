#!/usr/bin/env python3
"""
Run LLM filter on unscored articles in the database.
Updates llm_relevance in-place, then shows combined-score distribution.
"""
import os
import sys
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("refilter")

BASE_DIR = Path(__file__).parent

os.environ["MONITOR_THEME"] = sys.argv[1] if len(sys.argv) > 1 else "aam"
DB_PATH = BASE_DIR / "data" / f"{os.environ['MONITOR_THEME']}.db"

sys.path.insert(0, str(BASE_DIR))
import config
from monitor import batch_llm_filter, relevance_score


def main():
    if not config.USE_LLM_FILTER or not config.LLM_API_KEY:
        log.error("LLM filter not configured — check USE_LLM_FILTER and LLM_API_KEY")
        sys.exit(1)

    theme = os.environ["MONITOR_THEME"]

    # Fetch articles that need LLM scoring (briefly)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    rows = conn.execute(
        "SELECT id, title, summary, matched_kw, relevance FROM articles WHERE llm_relevance = 0"
    ).fetchall()
    conn.close()
    log.info(f"{theme}: {len(rows)} articles with llm_relevance=0")

    if not rows:
        log.info("No articles need LLM filtering.")
        return

    # Prepare entries for LLM batch filter
    entries = [{"title": r[2], "summary": r[3] or ""} for r in rows]

    log.info(f"Running LLM filter on {len(entries)} articles...")
    results = batch_llm_filter(entries, batch_size=20)

    # Update DB (fresh connection with timeout for safety)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    updated = 0
    for (art_id, title, summary, matched_kw, old_score), (accepted, llm_score) in zip(rows, results):
        llm_val = int(llm_score * 10)  # 0-100
        if not accepted:
            llm_val = 10  # low score for rejected
            log.info(f"LLM rejected: {title[:60]}...")
        conn.execute(
            "UPDATE articles SET llm_relevance = ? WHERE id = ?",
            (llm_val, art_id)
        )
        updated += 1

    conn.commit()
    conn.close()
    log.info(f"Updated {updated} articles in {theme}.db")

    # Re-open for analysis
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    all_rows = conn.execute(
        "SELECT title, matched_kw, relevance, llm_relevance FROM articles"
    ).fetchall()

    # Get original keywords from config for title gate
    all_kw_original = set()
    for group_kws in config.KEYWORDS.values():
        for kw in group_kws:
            all_kw_original.add(kw.lower().strip())

    buckets = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
    low_score_articles = []

    for title, matched_kw_str, kw_score, llm_rel in all_rows:
        # Title gate: check if any original keyword is in the title
        title_lower = title.lower()
        orig_in_title = any(kw in title_lower for kw in all_kw_original)

        # Parse matched keywords from DB
        matched_kws = [kw.strip() for kw in matched_kw_str.split(",")] if matched_kw_str else []

        if orig_in_title:
            score_kws = matched_kws  # all keywords
        else:
            # Use only keywords that are in original config
            score_kws = [kw for kw in matched_kws if kw.lower().strip() in all_kw_original]

        if not score_kws:
            score_kws = matched_kws  # fallback

        kw_score_computed = relevance_score(score_kws, title, "")

        llm_normalized = llm_rel  # already 0-100
        combined = int(kw_score_computed * 0.4 + llm_normalized * 0.6)
        final = max(kw_score_computed, combined)

        bucket = "80-100"
        if final < 20: bucket = "0-19"
        elif final < 40: bucket = "20-39"
        elif final < 60: bucket = "40-59"
        elif final < 80: bucket = "60-79"
        buckets[bucket] += 1

        if final < config.MIN_RELEVANCE_SCORE:
            low_score_articles.append((final, title, kw_score_computed, llm_normalized, orig_in_title))

    log.info(f"Combined score distribution ({theme}): {dict(sorted(buckets.items()))}")
    log.info(f"Articles below MIN_RELEVANCE_SCORE={config.MIN_RELEVANCE_SCORE}: {len(low_score_articles)}")

    if low_score_articles:
        low_score_articles.sort(key=lambda x: x[0])
        print(f"\n{'='*80}")
        print(f"Articles BELOW threshold ({config.MIN_RELEVANCE_SCORE}):")
        print(f"{'='*80}")
        for score, title, kw_s, llm_s, orig_in_title in low_score_articles:
            orig_flag = "✓" if orig_in_title else "✗"
            print(f"  [{score:3d}] (kw={kw_s:3d}, llm={llm_s:3d}, orig_in_title={orig_flag}) {title[:80]}")

    print(f"\n{'='*80}")
    print(f"All articles by score:")
    print(f"{'='*80}")
    for bucket_name in ["0-19", "20-39", "40-59", "60-79", "80-100"]:
        print(f"  {bucket_name}: {buckets[bucket_name]} articles")
    print(f"  Below threshold ({config.MIN_RELEVANCE_SCORE}): {len(low_score_articles)} articles")

    conn.close()


if __name__ == "__main__":
    main()
