#!/usr/bin/env python3
"""
News Monitor — multi-theme news monitoring system.

Usage:
    python3 main.py poll              Run one poll cycle (fetch → filter → translate → notify)
    python3 main.py poll --dry-run    Test polling without saving/notifying
    python3 main.py poll --skip-llm   Skip LLM filter (keyword match only)
    python3 main.py daemon            Poll continuously (every N minutes)
    python3 main.py serve             Start web dashboard
    python3 main.py briefing          Generate weekly briefing
    python3 main.py stats             Show article statistics

Set MONITOR_THEME=news (default) or MONITOR_THEME=aam for different monitor themes.
"""
import logging
import sys
import time

import config

log = logging.getLogger(config.LOGGER_NAME)


def cmd_poll(dry_run=False, skip_llm=False):
    from monitor import run
    run(dry_run=dry_run, skip_llm=skip_llm)


def cmd_serve():
    from dashboard import run
    run()


def cmd_daemon():
    from monitor import run
    log.info(f"Daemon mode: polling every {config.POLL_INTERVAL_MINUTES} minutes")
    while True:
        try:
            run(dry_run=False)
        except Exception as e:
            log.error(f"Poll cycle failed: {e}", exc_info=True)
        log.info(f"Sleeping for {config.POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(config.POLL_INTERVAL_MINUTES * 60)


def cmd_backfill_images():
    """Backfill image_url for articles that are missing them."""
    from monitor import init_db, fetch_article_content
    conn = init_db()
    rows = conn.execute("SELECT id, url FROM articles WHERE image_url IS NULL OR image_url = ''").fetchall()
    print(f"Found {len(rows)} articles without images")
    fixed = 0
    for rid, rurl in rows:
        content = fetch_article_content(rurl)
        if content and content.get("image_url"):
            conn.execute("UPDATE articles SET image_url = ? WHERE id = ?", (content["image_url"], rid))
            conn.commit()
            fixed += 1
            print(f"  ✓ {content['image_url'][:60]}")
    print(f"Fixed {fixed} articles")
    conn.close()


def cmd_briefing(days=7):
    """Generate and save weekly briefing."""
    from briefing import run as briefing_run
    text = briefing_run(days=days)
    print(f"\n{'='*60}")
    print("Weekly Briefing Generated")
    print(f"{'='*60}")
    print(text[:2000])  # Show preview
    print(f"\n{'='*60}")
    return text


def cmd_stats():
    from monitor import init_db
    conn = init_db()
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=0").fetchone()[0]
    last_24h = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    translated = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE is_translated=1"
    ).fetchone()[0]
    recent = conn.execute(
        "SELECT title, source, published, relevance, is_translated FROM articles "
        "ORDER BY published DESC LIMIT 10"
    ).fetchall()

    print(f"\n{'='*50}")
    print(f"  {config.STATS_TITLE} - Statistics")
    print(f"{'='*50}")
    print(f"  Total articles:  {total}")
    print(f"  Unread:          {unread}")
    print(f"  Last 24h:        {last_24h}")
    print(f"  Translated:      {translated}")
    print(f"\n  Latest articles:")
    for r in recent:
        flag = " [中]" if r[4] else ""
        print(f"    [{r[3]:>3}] {r[0][:65]}...{flag}")
        print(f"          {r[1]} · {r[2][:16]}")
    print(f"{'='*50}\n")
    conn.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    skip_llm = "--skip-llm" in sys.argv

    if cmd == "poll":
        cmd_poll(dry_run=dry_run, skip_llm=skip_llm)
    elif cmd == "serve":
        cmd_serve()
    elif cmd == "daemon":
        cmd_daemon()
    elif cmd == "briefing":
        cmd_briefing()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "backfill-images":
        cmd_backfill_images()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
