#!/usr/bin/env python3
"""
Translate patent articles that were backfilled without translation.
- Articles with keyword matches: LLM translation
- Other articles: simple title pass-through (mark as translated without LLM cost)
Also runs affiliation backfill for articles with authors but no affiliation.

Usage:
    MONITOR_THEME=news python3 backfill_translate_patents.py
    MONITOR_THEME=aam python3 backfill_translate_patents.py
"""
import logging
import os
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("patent-translate")

os.environ.setdefault("MONITOR_THEME", "news")

import config
from monitor import init_db, translate_article
from translator import contains_chinese


def main():
    theme = os.environ.get("MONITOR_THEME", "news")
    log.info(f"Starting patent backfill: theme={theme}, db={config.DB_PATH}")

    conn = init_db()

    # ── Step 1: Translate patent articles ──
    rows = conn.execute(
        "SELECT id, title, summary, content, matched_kw FROM articles "
        "WHERE article_type='patent' AND translated_title = ''"
    ).fetchall()
    log.info(f"Patent articles to process: {len(rows)}")

    llm_count = 0
    pass_count = 0

    for rid, title, summary, content, matched_kw in rows:
        article = {
            "title": title,
            "summary": summary or "",
            "content": content or "",
        }

        # LLM translate only for articles matching keywords or with Chinese content
        if matched_kw or contains_chinese(title):
            result = translate_article(article)
            if result:
                t_title = result.get("translated_title", "")
                t_summary = result.get("translated_summary", "")
                conn.execute(
                    "UPDATE articles SET translated_title=?, translated_summary=?, is_translated=1 WHERE id=?",
                    (t_title or title, t_summary, rid),
                )
                llm_count += 1
                log.info(f"  [LLM] ✓ {title[:60]}")
            else:
                log.warning(f"  [LLM] × {title[:60]}")
            time.sleep(0.3)
        else:
            # Pass-through: use original title as translated title
            conn.execute(
                "UPDATE articles SET translated_title=title, is_translated=1 WHERE id=?",
                (rid,),
            )
            pass_count += 1

        if (llm_count + pass_count) % 20 == 0:
            conn.commit()

    conn.commit()
    log.info(f"Translated: {llm_count} LLM + {pass_count} pass-through = {llm_count + pass_count} total")

    # ── Step 2: Backfill affiliations ──
    need_affil = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE author != '' AND affiliation = ''"
    ).fetchone()[0]
    if need_affil > 0:
        from monitor import backfill_affiliations
        log.info(f"Running affiliation backfill for {need_affil} articles...")
        backfill_affiliations()
    else:
        log.info("No articles need affiliation backfill.")

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
