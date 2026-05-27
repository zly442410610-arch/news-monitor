#!/usr/bin/env python3
"""
Google Patents collector — search for new patents matching keywords via
the Google Patents internal API (/xhr/query), then run keyword/LLM filtering
and save to the per-theme database.

Usage:
    MONITOR_THEME=news python3 collect_patents.py
    MONITOR_THEME=aam  python3 collect_patents.py
"""
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("patents")

os.environ.setdefault("MONITOR_THEME", "news")

import config
from monitor import (
    init_db, article_exists, keyword_match, save_article,
    make_article_id, llm_filter, translate_article, _needs_proxy,
)
from translator import contains_chinese

RESULTS_PER_QUERY = 30
MAX_ARTICLES_PER_RUN = 60

# Grouped searches: broader queries that cover multiple keywords each
SEARCH_GROUPS = {
    "sfrj": [
        "solid rocket motor OR solid propellant OR solid rocket booster",
        "ramjet OR scramjet OR ducted rocket OR supersonic combustion",
        "hypersonic propulsion OR hypersonic vehicle",
        "rocket nozzle OR thrust chamber OR thrust vector control",
        "rocket propulsion system OR liquid rocket engine",
    ],
    "aam": [
        "air-to-air missile OR air combat missile OR beyond visual range missile",
        "missile guidance OR missile seeker OR infrared seeker OR radar homing",
        "missile control system OR missile propulsion OR thrust vector control missile",
        "missile warhead OR proximity fuze OR missile launch system",
        "air defense missile OR surface-to-air missile OR anti-aircraft missile",
    ],
}


def get_proxies():
    """Return proxy dict if proxy is available."""
    try:
        from monitor import _check_proxy, PROXY
        if _check_proxy():
            return {"https": PROXY}
    except Exception:
        pass
    return None


_patent_session = None


def _get_patent_session(force=False):
    """Get a requests.Session warmed up with Google Patents cookies.

    Google /xhr/query requires session cookies from the homepage first.
    If force=True, creates a new session (for recovering from 503).
    """
    global _patent_session
    if _patent_session is not None and not force:
        return _patent_session

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    proxies = get_proxies()
    # Must visit google.com first to get NID cookie, otherwise patents subdomain returns 503
    for warm_url in ("https://www.google.com/", "https://patents.google.com/"):
        try:
            s.get(warm_url, proxies=proxies, timeout=15)
        except Exception:
            pass
    _patent_session = s
    return s


def search_patents(query: str, num: int = RESULTS_PER_QUERY) -> list[dict]:
    """Search Google Patents via internal API. Returns list of patent dicts.

    Retries once with fresh session on 503 rate-limit.
    """
    params = urllib.parse.urlencode({
        "q": query,
        "num": num,
        "sort": "new",
    })
    api_url = f"https://patents.google.com/xhr/query?url={urllib.parse.quote(params)}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://patents.google.com/",
    }
    proxies = get_proxies()

    for attempt in range(2):
        try:
            s = _get_patent_session(force=(attempt > 0))
            r = s.get(api_url, headers=headers, proxies=proxies, timeout=20)
            if r.status_code == 503 and attempt == 0:
                log.info("Got 503, re-warming session...")
                time.sleep(3)
                continue
            r.raise_for_status()
            data = r.json()
            clusters = data.get("results", {}).get("cluster", [])
            patents = []
            for cluster in clusters:
                for result in cluster.get("result", []):
                    patent = result.get("patent", {})
                    if patent.get("publication_number"):
                        patents.append(patent)
            return patents
        except Exception as e:
            if attempt == 0:
                log.info(f"Retry after error: {e}")
                time.sleep(3)
                continue
            log.warning(f"Search failed for '{query}': {e}")
            return []
    return []


def patent_to_article(patent: dict) -> dict:
    """Convert Google Patents API result to article dict."""
    title = patent.get("title", "").replace("&hellip;", "…").replace("&amp;", "&")
    pub_num = patent.get("publication_number", "")
    pub_date = patent.get("publication_date", "")
    snippet = patent.get("snippet", "").replace("&hellip;", "…").replace("&amp;", "&")
    inventor = patent.get("inventor", "") or ""
    assignee = patent.get("assignee", "") or ""
    author = inventor
    affiliation = assignee

    # Build the patent URL
    patent_url = f"https://patents.google.com/patent/{pub_num}/"

    # Use snippet as summary (it's the abstract with search term highlights)
    summary = snippet

    # Build source name
    country = pub_num[:2] if len(pub_num) >= 2 else "US"
    kind = pub_num[-2:] if len(pub_num) >= 2 else ""
    source = f"Google Patents - {country} ({kind})"

    article_id = make_article_id(patent_url, title)

    return {
        "id": article_id,
        "title": title,
        "url": patent_url,
        "source": source,
        "published": pub_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary[:2000],
        "matched_kw": "",
        "relevance": 0,
        "article_type": "patent",
        "author": author,
        "affiliation": affiliation,
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
    group_key = "aam" if theme == "aam" else "sfrj"
    queries = SEARCH_GROUPS.get(group_key, SEARCH_GROUPS["sfrj"])

    log.info(f"Starting Google Patents collection for theme '{theme}' ({group_key})")
    log.info(f"DB path: {config.DB_PATH}")

    try:
        conn = init_db()
    except Exception as e:
        log.error(f"Database init failed: {e}")
        return

    new_count = 0
    new_articles: list[dict] = []
    seen_urls: set[str] = set()
    total_skipped = 0

    for query in queries:
        if new_count >= MAX_ARTICLES_PER_RUN:
            log.info(f"Reached max {MAX_ARTICLES_PER_RUN} new articles per run")
            break

        log.info(f"\n--- Searching: {query} ---")
        patents = search_patents(query)
        if not patents:
            log.info(f"  No results")
            continue
        log.info(f"  Got {len(patents)} results")

        for patent in patents:
            if new_count >= MAX_ARTICLES_PER_RUN:
                break

            article = patent_to_article(patent)
            norm_url = article["url"]

            if norm_url in seen_urls:
                total_skipped += 1
                continue

            # Dedup by article ID
            if article_exists(conn, article["id"]):
                total_skipped += 1
                continue

            # Keyword matching
            text = f"{article['title']} {article.get('summary', '')}"
            matched_kw = keyword_match(text)
            if not matched_kw:
                total_skipped += 1
                continue

            # Filter out generic/short keyword matches that cause false positives
            meaningful_kw = [kw for kw in matched_kw if len(kw) >= 4
                             and kw not in ("patent", "USPTO", "fuse")]
            if not meaningful_kw:
                total_skipped += 1
                continue

            article["matched_kw"] = ", ".join(meaningful_kw)
            article["relevance"] = min(100, 50 + len(meaningful_kw) * 10)

            # Exclusion filter: reject known false-positive categories
            patent_text = f"{article['title']} {article.get('summary', '')}".lower()
            if any(p.lower() in patent_text for p in config.EXCLUDE_PATTERNS):
                log.info(f"  Excluded by pattern: {article['title'][:60]}")
                total_skipped += 1
                continue

            # LLM filter for all patents (full-text search brings many false positives)
            if not llm_filter(article):
                log.info(f"  LLM filtered: {article['title'][:60]}")
                total_skipped += 1
                continue

            seen_urls.add(norm_url)

            # Translate to Chinese (matching RSS pipeline behavior)
            if config.TRANSLATE_TO_CHINESE:
                article = translate_article(article)
                if article and not article.get("translated_title") and contains_chinese(article.get("title", "")):
                    article["translated_title"] = article["title"]
                    article["translated_summary"] = article.get("summary", "")

            if save_article(conn, article):
                new_count += 1
                new_articles.append(article)
                log.info(f"  [{new_count}] {article['title'][:70]}")
                log.info(f"           {article['url']}")

        conn.commit()
        time.sleep(2)  # Be nice to the API

    log.info(f"\nDone. Saved {new_count} new patents. Skipped {total_skipped} (duplicates/no match).")

    # Notify for newly collected patents (matching RSS pipeline behavior)
    if new_count > 0:
        try:
            from notifier import notify_batch
            notify_batch(new_articles)
        except Exception as e:
            log.warning(f"Patent notification failed: {e}")

    conn.close()


if __name__ == "__main__":
    main()
