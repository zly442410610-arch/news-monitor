#!/usr/bin/env python3
"""
Backfill patent articles for both themes (NEWS/AAM).

Fetches FreePatentsOnline RSS feeds with relaxed SSL (older TLS needed),
runs keyword matching, and saves to the per-theme database.

Usage:
    MONITOR_THEME=news python3 backfill_patents.py
    MONITOR_THEME=aam python3 backfill_patents.py
"""
import logging
import os
import time
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
import ssl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("patent-backfill")

os.environ.setdefault("MONITOR_THEME", "news")

import config
from monitor import (
    init_db, article_exists, keyword_match, save_article,
    make_article_id, _normalize_url,
)

PATENT_SOURCES = {
    "FPO Patents - Power Plants": "https://www.freepatentsonline.com/rssfeed/rsspat060.xml",
    "FPO Patents - Aeronautics": "https://www.freepatentsonline.com/rssfeed/rsspat244.xml",
    "FPO Patents - Ammunition": "https://www.freepatentsonline.com/rssfeed/rsspat102.xml",
    "FPO Patents - Propellant Compositions": "https://www.freepatentsonline.com/rssfeed/rsspat149.xml",
}


class RelaxedSSLAdapter(HTTPAdapter):
    """Adapter that uses a non-validating SSL context (some patent sites have older TLS)."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def send(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        return super().send(*args, **kwargs)


def fetch_fpo_rss(url: str) -> list[dict]:
    """Fetch an FPO RSS feed with relaxed SSL settings."""
    entries = []
    session = requests.Session()
    session.mount("https://", RelaxedSSLAdapter())
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    try:
        resp = session.get(url, timeout=30, headers={"User-Agent": ua})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            log.warning(f"Feed parse error: {feed.bozo_exception}")
            return entries
        for entry in feed.entries:
            if len(entries) >= 30:
                break
            author = ""
            if hasattr(entry, "author") and entry.author:
                author = entry.author.strip()
            elif hasattr(entry, "authors") and entry.authors:
                author = ", ".join(a.get("name", "") for a in entry.authors if a.get("name"))
            e = {
                "title": (entry.get("title") or "").strip(),
                "url": (entry.get("link") or "").strip(),
                "summary": (entry.get("summary") or entry.get("description") or "").strip(),
                "published": entry.get("published") or entry.get("updated", ""),
                "source": url,
                "author": author,
            }
            if e["summary"]:
                e["summary"] = BeautifulSoup(e["summary"], "lxml").get_text(
                    separator=" ", strip=True
                )[:2000]
            entries.append(e)
        log.info(f"  Fetched {len(entries)} entries: {url.split('/')[-1]}")
    except Exception as e:
        log.error(f"  Fetch failed: {e}")
    finally:
        session.close()
    return entries


def main():
    theme = os.environ.get("MONITOR_THEME", "news")
    log.info(f"Starting patent backfill for theme: {theme}")
    log.info(f"DB path: {config.DB_PATH}")

    conn = init_db()
    new_count = 0
    seen_urls: set[str] = set()

    for source_name, rss_url in PATENT_SOURCES.items():
        log.info(f"\n--- {source_name} ---")
        entries = fetch_fpo_rss(rss_url)
        if not entries:
            continue

        for entry in entries:
            # Normalize URL for dedup
            norm_url = _normalize_url(entry["url"])
            if norm_url in seen_urls:
                continue

            # Article ID + dedup
            article_id = make_article_id(entry["url"], entry["title"])
            if article_exists(conn, article_id):
                continue

            # Keyword match
            text = f"{entry['title']} {entry.get('summary', '') or ''}"
            matched_kw = keyword_match(text)

            # Relevance
            relevance = 50
            if matched_kw:
                relevance = min(100, 50 + len(matched_kw) * 10)

            article = {
                "id": article_id,
                "title": entry["title"],
                "url": entry["url"],
                "source": source_name,
                "published": entry.get("published", ""),
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "summary": entry.get("summary", "")[:2000],
                "matched_kw": ", ".join(matched_kw) if matched_kw else "",
                "relevance": relevance,
                "article_type": "patent",
                "author": entry.get("author", ""),
                "affiliation": "",
                "event_group": "",
                "event_title": "",
                "translated_title": "",
                "translated_summary": "",
                "translated_content": "",
                "image_url": "",
                "content": "",
            }

            if save_article(conn, article):
                new_count += 1
                log.info(f"  [{new_count}] {entry['title'][:70]}")

        conn.commit()
        time.sleep(1)

    log.info(f"\nDone. Saved {new_count} new patent articles for theme '{theme}'.")
    conn.close()


if __name__ == "__main__":
    main()
