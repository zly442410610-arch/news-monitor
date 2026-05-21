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


def cmd_poll(dry_run=False, skip_llm=False, source_type=None):
    from monitor import run
    run(dry_run=dry_run, skip_llm=skip_llm, source_type=source_type)


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


def cmd_backfill_content_translation():
    """Backfill translated_content for articles where content exists but translation is missing."""
    from monitor import init_db
    from translator import translate_content, is_predominantly_chinese

    conn = init_db()

    # Drop FTS triggers to avoid constraint errors on bulk UPDATE
    for t in ["articles_au", "articles_ai", "articles_ad"]:
        try:
            conn.execute(f"DROP TRIGGER IF EXISTS {t}")
        except Exception:
            pass

    rows = conn.execute(
        "SELECT id, title, content FROM articles "
        "WHERE content != '' AND content IS NOT NULL AND length(content) > 500 "
        "AND (translated_content IS NULL OR translated_content = '')"
    ).fetchall()
    total = len(rows)
    print(f"Found {total} articles needing content translation")
    fixed = 0
    for rid, title, content in rows:
        if is_predominantly_chinese(content):
            conn.execute("UPDATE articles SET translated_content = content WHERE id = ?", (rid,))
            conn.commit()
            fixed += 1
            print(f"  [{fixed}/{total}] ✓ already Chinese: {title[:50]}...")
            continue
        result = translate_content(content)
        if result:
            conn.execute("UPDATE articles SET translated_content = ? WHERE id = ?", (result, rid))
            conn.commit()
            fixed += 1
            print(f"  [{fixed}/{total}] ✓ {len(result)} chars: {title[:50]}...")
        else:
            print(f"  [{fixed+1}/{total}] × failed: {title[:50]}...")

    # Recreate FTS triggers (only if FTS table exists)
    try:
        conn.execute("SELECT 1 FROM articles_fts LIMIT 1")
        for ddl in [
            "CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN "
            "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
            "CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN "
            "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); END;",
            "CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN "
            "INSERT INTO articles_fts(articles_fts, rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES ('delete', old.rowid, old.title, old.summary, old.content, old.translated_title, old.translated_summary, old.translated_content); "
            "INSERT INTO articles_fts(rowid, title, summary, content, translated_title, translated_summary, translated_content) "
            "VALUES (new.rowid, new.title, new.summary, new.content, new.translated_title, new.translated_summary, new.translated_content); END;",
        ]:
            conn.execute(ddl)
        conn.commit()
        # Rebuild FTS to sync
        conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass

    print(f"\nDone. Translated {fixed}/{total} articles")
    conn.close()


def cmd_backfill_affiliations():
    """Backfill missing author affiliations using LLM inference."""
    from monitor import backfill_affiliations
    backfill_affiliations()


def cmd_backfill_content():
    """Backfill content for articles that are missing it, then translate."""
    from monitor import init_db, fetch_article_content, save_snapshot
    from translator import translate_content, is_predominantly_chinese

    conn = init_db()
    rows = conn.execute(
        "SELECT id, url, content, translated_content FROM articles "
        "WHERE (content IS NULL OR content = '') AND translated_content = ''"
    ).fetchall()
    total = len(rows)
    print(f"Found {total} articles without content")
    fixed = 0
    translated = 0
    for rid, rurl, old_content, old_trans in rows:
        result = fetch_article_content(rurl)
        if result and result.get("text"):
            text = result["text"][:50000]
            conn.execute("UPDATE articles SET content = ? WHERE id = ?", (text, rid))
            conn.commit()
            save_snapshot(rid, text)
            fixed += 1
            print(f"  [{fixed}/{total}] ✓ content: {text[:60]}...")

            # Translate content if not Chinese
            if len(text) > 500 and not contains_chinese(text):
                translated_text = translate_content(text)
                if translated_text:
                    conn.execute(
                        "UPDATE articles SET translated_content = ? WHERE id = ?",
                        (translated_text, rid),
                    )
                    conn.commit()
                    translated += 1
                    print(f"         → translated ({len(translated_text)} chars)")
        else:
            print(f"  [{fixed+1}/{total}] × no content fetched")
    print(f"Updated {fixed} articles with content, translated {translated}")
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
    source_type = None
    for i, arg in enumerate(sys.argv):
        if arg == "--source-type" and i + 1 < len(sys.argv):
            source_type = sys.argv[i + 1]

    if cmd == "poll":
        cmd_poll(dry_run=dry_run, skip_llm=skip_llm, source_type=source_type)
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
    elif cmd == "backfill-content":
        cmd_backfill_content()
    elif cmd == "backfill-affiliations":
        cmd_backfill_affiliations()
    elif cmd == "backfill-content-translation":
        cmd_backfill_content_translation()
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
