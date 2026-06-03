#!/usr/bin/env python3
"""
Backfill CNKI article full text and images for both themes.

Connects to news.db and aam.db, iterates all CNKI articles,
fetches full content through the Zhejiang Library proxy,
and updates the database with content + images.

Usage:
    python3 backfill_cnki_fulltext.py                 # backfill both databases
    python3 backfill_cnki_fulltext.py --news-only     # news.db only
    python3 backfill_cnki_fulltext.py --aam-only      # aam.db only
"""
import json
import logging
import sqlite3
import sys
import time
import random
from pathlib import Path

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("backfill_cnki")

EXPIRED_MARKERS = ["登录已过期", "token校验失败", "404 -"]

# Import monitor functions after path setup
sys.path.insert(0, str(BASE))
import config
from monitor import fetch_article_content, update_article_content


def count_cnki_articles(conn: sqlite3.Connection) -> dict:
    """Return stats about CNKI articles in the database."""
    total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE url LIKE '%cnki.net%'"
    ).fetchone()[0]
    with_content = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE url LIKE '%cnki.net%' "
        "AND content IS NOT NULL AND length(content) > 300"
    ).fetchone()[0]
    with_images = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE url LIKE '%cnki.net%' "
        "AND image_url IS NOT NULL AND image_url != ''"
    ).fetchone()[0]
    return {"total": total, "with_content": with_content, "with_images": with_images}


def is_expired_response(text: str) -> bool:
    """Check if response indicates an expired/unauthorized session."""
    for marker in EXPIRED_MARKERS:
        if marker in text:
            return True
    return False


def _quick_proxy_check(url: str) -> bool:
    """Quick check if a CNKI article URL is accessible through proxy.
    Returns True (expired/skip) if URL is no longer valid.
    """
    # Use 书童 cookies if available
    shutong_cookies = {}
    _shutong_mode = config.SHUTONG_ENABLED
    if _shutong_mode and config.SHUTONG_COOKIE_JAR.exists():
        try:
            import json
            shutong_data = json.loads(config.SHUTONG_COOKIE_JAR.read_text())
            shutong_cookies = shutong_data.get("cookies", {})
        except Exception:
            pass

    if _shutong_mode and shutong_cookies:
        cookies = shutong_cookies
        import re
        proxied = url
        for domain, proxy_domain in (
            ("kns.cnki.net", "kns-cnki-net-443.wvpn.sjlib.cn"),
            ("www.cnki.net", "www-cnki-net-443.wvpn.sjlib.cn"),
            ("navi.cnki.net", "navi-cnki-net-443.wvpn.sjlib.cn"),
        ):
            if domain in url:
                proxied = url.replace(domain, proxy_domain)
                break
    else:
        from cnki_session import load_cnki_cookies
        cookies = load_cnki_cookies()
        if not cookies:
            return False

        proxied = url
        for domain in ("kns.cnki.net", "www.cnki.net", "navi.cnki.net"):
            marker = f"https://{domain}"
            if marker in url:
                path = url[len(marker):]
                if config.CNKI_PROXY_KEY:
                    proxied = f"{config.CNKI_PROXY_BASE}/{config.CNKI_PROXY_TOKEN}/e/{config.CNKI_PROXY_KEY}{path}"
                else:
                    proxied = f"{config.CNKI_PROXY_BASE}/{config.CNKI_PROXY_TOKEN}{path}"
                break

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        import requests as req
        r = req.get(proxied, headers=headers, cookies=cookies, timeout=10, allow_redirects=True)
        if r.status_code == 404:
            return True
        if r.status_code == 200 and is_expired_response(r.text):
            return True
        return False  # might be OK
    except Exception:
        return False  # can't determine, let the full fetch try


def backfill_database(db_path: Path, theme_name: str) -> dict:
    """Backfill all CNKI articles in a single database. Returns stats dict."""
    stats = {
        "total": 0, "fetched": 0, "expired": 0, "empty": 0,
        "error": 0, "updated_content": 0, "updated_images": 0,
    }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")

    rows = conn.execute(
        "SELECT id, title, url, length(content) as content_len, "
        "image_url, content_images "
        "FROM articles WHERE url LIKE '%cnki.net%' "
        "ORDER BY fetched_at DESC"
    ).fetchall()

    stats["total"] = len(rows)
    log.info(f"[{theme_name}] Found {len(rows)} CNKI articles")

    for i, row in enumerate(rows):
        article_id = row["id"]
        title = row["title"]
        url = row["url"]
        old_content_len = row["content_len"]
        old_image_url = row["image_url"] or ""
        old_images = row["content_images"] or ""

        log.info(
            f"[{theme_name}] [{i + 1}/{len(rows)}] {title[:50]}... "
            f"(content={old_content_len}b, image={bool(old_image_url)})"
        )

        # Rate limit
        delay = random.uniform(config.CNKI_FETCH_DELAY_MIN, config.CNKI_FETCH_DELAY_MAX)
        log.info(f"  Delay {delay:.1f}s...")
        time.sleep(delay)

        # Quick pre-check: try proxy URL directly, skip if expired
        if _quick_proxy_check(url):
            log.info(f"  Skipping (expired URL, v param no longer valid)")
            stats["expired"] += 1
            continue

        # Fetch content through proxy
        try:
            result = fetch_article_content(url, timeout=30)
        except Exception as e:
            log.error(f"  Fetch error: {e}")
            stats["error"] += 1
            continue

        if not result or not result.get("text"):
            log.warning(f"  No content returned (empty result)")
            stats["empty"] += 1
            continue

        text = result["text"].strip()
        if not text or len(text) < 50:
            log.warning(f"  Content too short ({len(text) if text else 0} chars)")
            stats["empty"] += 1
            continue

        if is_expired_response(text):
            log.warning(f"  Session expired / token invalid")
            stats["expired"] += 1
            continue

        # Successful fetch
        stats["fetched"] += 1
        new_content_len = len(text)
        new_doi = result.get("doi") or ""

        log.info(f"  Got {new_content_len} chars, image_url={result.get('image_url','')[:40] or 'none'}" + (f", doi={new_doi}" if new_doi else ""))

        # Update content only if new content is meaningful (>300 chars) and longer than existing
        should_update = False
        if new_content_len > 300 and new_content_len > old_content_len:
            should_update = True

        # Update images if we got something new
        new_image_url = result.get("image_url") or ""
        new_images = result.get("images") or []

        if should_update or (new_image_url and new_image_url != old_image_url) or new_images:
            # Use direct sqlite3 connection for the update
            try:
                conn2 = sqlite3.connect(str(db_path))
                update_article_content(
                    conn2, article_id, text,
                    title=title,
                    images=new_images,
                    doi=new_doi,
                )
                # Also update image_url if we got a new one
                if new_image_url and new_image_url != old_image_url:
                    conn2.execute(
                        "UPDATE articles SET image_url = ? WHERE id = ?",
                        (new_image_url, article_id)
                    )
                    conn2.commit()
                conn2.close()

                if should_update:
                    stats["updated_content"] += 1
                    log.info(f"  ✓ Content updated ({old_content_len} → {new_content_len} chars)")
                if new_image_url and new_image_url != old_image_url:
                    stats["updated_images"] += 1
                    log.info(f"  ✓ Image updated: {new_image_url[:60]}")
            except Exception as e:
                log.error(f"  DB update error: {e}")
        else:
            log.info(f"  No meaningful update (content={new_content_len}b, no new images)")

    conn.close()
    return stats


def main():
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    shutong_mode = "--shutong" in sys.argv

    dbs = []
    if not aam_only:
        dbs.append((config.BASE_DIR / "data" / "news.db", "news"))
    if not news_only:
        dbs.append((config.BASE_DIR / "data" / "aam.db", "aam"))

    log.info("=" * 60)
    if shutong_mode:
        log.info("CNKI Full Text Backfill (书童 proxy mode)")
    else:
        log.info("CNKI Full Text Backfill")
    log.info(f"Databases: {[d[1] for d in dbs]}")
    log.info("=" * 60)

    if shutong_mode:
        # Load 书童 cookies and verify
        if not config.SHUTONG_COOKIE_JAR.exists():
            log.error("书童 cookie 文件不存在！请先运行 import_shutong_cookies.py 导入 cookie")
            sys.exit(1)
        try:
            import json
            raw = config.SHUTONG_COOKIE_JAR.read_text()
            data = json.loads(raw)
            cookies = data.get("cookies", {})
            if not cookies:
                log.error("书童 cookie 为空！请重新导出")
                sys.exit(1)
            log.info(f"Loaded {len(cookies)} 书童 cookies")
        except Exception as e:
            log.error(f"Failed to load 书童 cookies: {e}")
            sys.exit(1)
    else:
        # Ensure fresh CNKI session (old proxy)
        try:
            from cnki_session import load_cnki_cookies, refresh_cnki_session
            existing = load_cnki_cookies()
            if not existing:
                log.info("No cached CNKI cookies, refreshing session...")
                refresh_cnki_session()
            else:
                log.info(f"Found {len(existing)} cached CNKI cookies")
        except Exception as e:
            log.warning(f"CNKI session check failed: {e}")

    all_stats = {}
    for db_path, theme in dbs:
        if not db_path.exists():
            log.warning(f"Database not found: {db_path}")
            continue

        log.info(f"\n{'='*60}")
        log.info(f"Processing {theme} ({db_path.name})")
        log.info(f"{'='*60}")

        stats = backfill_database(db_path, theme)
        all_stats[theme] = stats

        log.info(f"\n[{theme}] Results:")
        log.info(f"  Total CNKI articles:   {stats['total']}")
        log.info(f"  Successfully fetched:  {stats['fetched']}")
        log.info(f"  Content updated:       {stats['updated_content']}")
        log.info(f"  Images updated:        {stats['updated_images']}")
        log.info(f"  Expired (v param):     {stats['expired']}")
        log.info(f"  Empty/too short:       {stats['empty']}")
        log.info(f"  Errors:                {stats['error']}")

    log.info("\n" + "=" * 60)
    log.info("Backfill complete")
    for theme, stats in all_stats.items():
        log.info(f"  {theme}: {stats['updated_content']} content + {stats['updated_images']} images updated")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
