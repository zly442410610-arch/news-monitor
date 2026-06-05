#!/usr/bin/env python3
"""
One-time patent backfill — fetch recent patents for both themes
via Google Patents API with relaxed filtering (skip LLM filter).

Usage:
    MONITOR_THEME=news python3 backfill_patents.py
    MONITOR_THEME=aam python3 backfill_patents.py
"""
import logging
import os
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

os.environ.setdefault("MONITOR_THEME", "news")

import config
from monitor import init_db, article_exists, save_article, make_article_id, translate_article
from collect_patents import search_patents, SEARCH_GROUPS
from translator import contains_chinese

RESULTS_PER_QUERY = 50


def patent_to_article(patent: dict, query_terms: list[str]) -> dict | None:
    title = patent.get("title", "").replace("&hellip;", "…").replace("&amp;", "&")
    pub_num = patent.get("publication_number", "")
    pub_date = patent.get("publication_date", "")
    snippet = patent.get("snippet", "").replace("&hellip;", "…").replace("&amp;", "&")
    inventor = patent.get("inventor", "") or ""
    assignee = patent.get("assignee", "") or ""

    if not pub_num or not title:
        return None

    patent_url = f"https://patents.google.com/patent/{pub_num}/"

    return {
        "id": make_article_id(patent_url, title),
        "title": title,
        "url": patent_url,
        "source": f"Google Patents - {pub_num[:2]} ({pub_num[-2:]})",
        "published": pub_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": snippet[:2000],
        "matched_kw": ", ".join(query_terms[:5]),
        "relevance": 80,
        "article_type": "patent",
        "author": inventor,
        "affiliation": assignee,
        "event_group": "",
        "event_title": "",
        "translated_title": "",
        "translated_summary": "",
        "translated_content": "",
        "image_url": "",
        "content": "",
    }


def main():
    theme = os.environ.get("MONITOR_THEME", "news")
    group_key = {"aam": "aam", "dw": "dw"}.get(theme, "sfrj")
    queries = SEARCH_GROUPS[group_key]

    log = logging.getLogger("backfill")
    log.info(f"Starting patent backfill for theme '{theme}'")
    log.info(f"DB: {config.DB_PATH}")

    conn = init_db()
    new_count = 0
    total_skipped = 0
    seen_urls: set[str] = set()

    for query in queries:
        log.info(f"\n--- {query[:80]}... ---")

        patents = search_patents(query, num=RESULTS_PER_QUERY)
        if not patents:
            log.info("  No results")
            continue
        log.info(f"  Got {len(patents)} results")

        terms = [p.strip().strip('"') for p in query.split(" OR ")]

        for patent in patents:
            article = patent_to_article(patent, terms)
            if not article:
                total_skipped += 1
                continue

            if article["url"] in seen_urls:
                total_skipped += 1
                continue

            if article_exists(conn, article["id"]):
                total_skipped += 1
                continue

            seen_urls.add(article["url"])

            # Skip translation for backfill speed; will translate via cron later

            if article and save_article(conn, article):
                new_count += 1
                log.info(f"  [{new_count}] {article['title'][:70]}")
                log.info(f"           {article['url']}")

        conn.commit()
        time.sleep(2)

    log.info(f"\nDone. Saved {new_count} patents. Skipped {total_skipped}.")
    conn.close()


if __name__ == "__main__":
    main()
