#!/usr/bin/env python3
"""
Recollect all CNKI articles from scratch.

Deletes existing CNKI articles from both databases (news.db and aam.db),
then re-collects from CNKI RSS sources with fresh URLs and attempts
immediate full-text content fetch through the 书童 proxy.

Usage:
    python3 recollect_cnki.py                 # both databases
    python3 recollect_cnki.py --news-only     # news.db only
    python3 recollect_cnki.py --aam-only      # aam.db only
"""
import logging
import sqlite3
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("recollect_cnki")

sys.path.insert(0, str(BASE))
import config
from monitor import (
    fetch_rss,
    keyword_match,
    make_article_id,
    save_article,
    fetch_article_content,
    update_article_content,
    _normalize_date,
    relevance_score,
    article_type,
)


def delete_cnki_articles(conn: sqlite3.Connection, theme: str) -> int:
    """Delete all CNKI articles from DB. Returns count deleted."""
    cur = conn.execute("DELETE FROM articles WHERE url LIKE '%cnki.net%'")
    deleted = cur.rowcount
    conn.commit()
    log.info(f"[{theme}] Deleted {deleted} CNKI articles (FTS cleaned by trigger)")
    return deleted


def _published_since(entry_published: str, cutoff_date: str = "2026-05-01") -> bool:
    """Check if the article's published date is >= cutoff date."""
    if not entry_published:
        return False
    # Common RSS date formats to try
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(entry_published.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cutoff_dt = datetime.strptime(cutoff_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt >= cutoff_dt
        except ValueError:
            continue
    log.debug(f"Cannot parse date: {entry_published[:60]}")
    return False


def recollect_database(db_path: Path, theme: str, with_content: bool = True) -> dict:
    """Recollect CNKI articles for one database. Returns stats dict."""
    stats = {
        "rss_entries": 0,
        "after_date": 0,
        "keyword_matched": 0,
        "saved": 0,
        "content_fetched": 0,
    }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")

    # Step 1: Delete all existing CNKI articles
    delete_cnki_articles(conn, theme)

    # Step 2: Get CNKI RSS sources only
    cnki_sources = {
        name: url
        for name, url in config.RSS_SOURCES.items()
        if name.startswith("CNKI -")
    }
    log.info(f"[{theme}] Found {len(cnki_sources)} CNKI RSS sources")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for source_name, source_url in cnki_sources.items():
        log.info(f"[{theme}] Fetching RSS: {source_name}")
        entries = fetch_rss(source_url)
        stats["rss_entries"] += len(entries)
        log.info(f"[{theme}]   {len(entries)} entries from {source_name}")

        for entry in entries:
            title = (entry.get("title") or "").strip()
            url = (entry.get("url") or "").strip()
            if not title or not url:
                continue

            published_raw = entry.get("published", "")
            published_normalized = _normalize_date(published_raw)

            # Date filter: skip articles published before 2026-05-01
            if not _published_since(published_raw):
                continue
            stats["after_date"] += 1

            # Keyword match
            summary = (entry.get("summary") or "").strip()[:2000]
            match_text = f"{title} {summary}"
            matched_kws = keyword_match(match_text)
            if not matched_kws:
                continue
            stats["keyword_matched"] += 1

            # Classify (CNKI → "paper")
            a_type = article_type(source_name, url, entry.get("author", ""))

            # Relevance score
            rel = relevance_score(matched_kws, title, summary)

            # Build article dict (matches save_article's INSERT fields)
            article_id = make_article_id(url, title)
            article = {
                "id": article_id,
                "title": title,
                "url": url,
                "source": source_name,
                "published": published_normalized,
                "fetched_at": fetched_at,
                "summary": summary,
                "matched_kw": ", ".join(matched_kws),
                "relevance": rel,
                "translated_title": "",
                "translated_summary": "",
                "is_translated": 0,
                "author": entry.get("author", ""),
                "affiliation": "",
                "event_group": "",
                "event_title": "",
                "translated_content": "",
                "image_url": "",
                "content": "",
                "article_type": a_type,
                "content_images": "",
                "doi": "",
            }

            if save_article(conn, article):
                stats["saved"] += 1
                log.info(
                    f"  [{theme}] ✓ Saved: {title[:55]}... "
                    f"(kw={len(matched_kws)}, rel={rel})"
                )

                # Step 3: Immediately try to fetch full content through proxy
                if with_content:
                    delay = random.uniform(
                        config.CNKI_FETCH_DELAY_MIN,
                        config.CNKI_FETCH_DELAY_MAX,
                    )
                    log.info(f"    Content fetch delay {delay:.1f}s...")
                    time.sleep(delay)

                    try:
                        result = fetch_article_content(url, timeout=30)
                        if result and result.get("text"):
                            text = result["text"].strip()
                            if len(text) > 500:
                                new_images = result.get("images") or []
                                new_doi = result.get("doi") or ""
                                update_article_content(
                                    conn, article_id, text,
                                    title=title,
                                    images=new_images,
                                    doi=new_doi,
                                )
                                new_image_url = result.get("image_url") or ""
                                if new_image_url:
                                    conn.execute(
                                        "UPDATE articles SET image_url = ? WHERE id = ?",
                                        (new_image_url, article_id),
                                    )
                                    conn.commit()
                                stats["content_fetched"] += 1
                                log.info(f"    ✓ Content: {len(text)} chars")
                            else:
                                log.info(f"    - Content too short ({len(text)} chars)")
                        else:
                            log.info(f"    - No content returned")
                    except Exception as e:
                        log.warning(f"    - Content fetch error: {e}")
                else:
                    log.info(f"    (content fetch skipped)")
            else:
                log.debug(f"  [{theme}] - Skipped (already in DB): {title[:55]}")

    conn.commit()
    conn.close()
    return stats


def main():
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    no_content = "--no-content" in sys.argv

    dbs = []
    if not aam_only:
        dbs.append((config.BASE_DIR / "data" / "news.db", "news"))
    if not news_only:
        dbs.append((config.BASE_DIR / "data" / "aam.db", "aam"))

    log.info("=" * 60)
    log.info("CNKI Re-collection (May 2026+)")
    log.info(f"Databases: {[d[1] for d in dbs]}")
    if config.SHUTONG_ENABLED:
        log.info("书童 proxy: enabled")
    else:
        log.warning("书童 proxy: NOT configured — content fetch will fail")
    if no_content:
        log.info("Content fetch: disabled (--no-content)")
    log.info("=" * 60)

    all_stats = {}
    for db_path, theme in dbs:
        if not db_path.exists():
            log.warning(f"Database not found: {db_path}")
            continue

        log.info(f"\n{'='*60}")
        log.info(f"Processing {theme} ({db_path.name})")
        log.info(f"{'='*60}")

        stats = recollect_database(db_path, theme, with_content=not no_content)
        all_stats[theme] = stats

        log.info(f"\n[{theme}] Results:")
        log.info(f"  RSS entries scanned:   {stats['rss_entries']}")
        log.info(f"  After May 1 cutoff:    {stats['after_date']}")
        log.info(f"  Keyword matched:        {stats['keyword_matched']}")
        log.info(f"  Saved (new):            {stats['saved']}")
        log.info(f"  Content fetched:        {stats['content_fetched']}")

    log.info("\n" + "=" * 60)
    log.info("CNKI Re-collection complete")
    for theme, s in all_stats.items():
        log.info(f"  {theme}: {s['saved']} saved, {s['content_fetched']} with content")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
