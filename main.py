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
    python3 main.py backfill-keywords      Re-scan articles with updated keyword rules
    python3 main.py backup                Safely backup both databases
    python3 main.py backfill-clean-content  Re-clean existing content with updated rules

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
    _start_cnki_session()
    from dashboard import run
    run()


def _start_cnki_session():
    """Start background CNKI session refresher if proxy is configured."""
    if config.CNKI_PROXY_TOKEN:
        try:
            from cnki_session import start_session_refresher
            start_session_refresher()
        except Exception as e:
            log.warning(f"CNKI session refresher not started: {e}")
    else:
        log.debug("CNKI proxy not configured, skipping session refresher")


def cmd_daemon():
    from monitor import run

    _start_cnki_session()

    log.info(f"Daemon mode: polling every {config.POLL_INTERVAL_MINUTES} minutes")
    while True:
        try:
            run(dry_run=False)
        except Exception as e:
            log.error(f"Poll cycle failed: {e}", exc_info=True)

        # Auto-backup databases once per day
        try:
            from monitor import backup_database
            today = time.strftime("%Y%m%d")
            backup_dir = config.BACKUP_DIR
            if backup_dir.exists():
                todays_backups = list(backup_dir.glob(f"*-{today}.db"))
                if not todays_backups:
                    backup_database()
            else:
                backup_database()
        except Exception as e:
            log.warning(f"Auto-backup failed: {e}")

        log.info(f"Sleeping for {config.POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(config.POLL_INTERVAL_MINUTES * 60)


def cmd_backfill_images():
    """Backfill image_url for articles that are missing them."""
    from monitor import init_db, fetch_article_content
    import json
    conn = init_db()
    rows = conn.execute("SELECT id, url FROM articles WHERE image_url IS NULL OR image_url = ''").fetchall()
    print(f"Found {len(rows)} articles without images")
    fixed = 0
    for rid, rurl in rows:
        content = fetch_article_content(rurl)
        if content and content.get("image_url"):
            images_json = json.dumps(content.get("images", []))
            conn.execute(
                "UPDATE articles SET image_url = ?, content_images = ? WHERE id = ?",
                (content["image_url"], images_json, rid),
            )
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


def cmd_backfill_clean_content():
    """Re-clean existing article content with updated clean_content rules (CJK space cleanup)."""
    from monitor import init_db, clean_content

    conn = init_db()
    rows = conn.execute(
        "SELECT id, title, content FROM articles "
        "WHERE content IS NOT NULL AND content != ''"
    ).fetchall()
    total = len(rows)
    print(f"Found {total} articles with content to re-clean")
    fixed = 0
    for rid, title, content in rows:
        cleaned = clean_content(content)
        if cleaned != content:
            conn.execute("UPDATE articles SET content = ? WHERE id = ?", (cleaned, rid))
            conn.commit()
            fixed += 1
            print(f"  ✓ {title[:50]}... ({len(content)}→{len(cleaned)} chars)")
    print(f"Cleaned {fixed}/{total} articles")
    conn.close()


def cmd_backfill_content():
    """Backfill content for articles that are missing it, then translate."""
    from monitor import init_db, fetch_article_content, save_snapshot, update_article_content
    from translator import contains_chinese

    conn = init_db()
    rows = conn.execute(
        "SELECT id, url, content, translated_content FROM articles "
        "WHERE (content IS NULL OR content = '') AND translated_content = ''"
    ).fetchall()
    total = len(rows)
    print(f"Found {total} articles without content")
    fixed = 0
    for rid, rurl, old_content, old_trans in rows:
        result = fetch_article_content(rurl)
        if result and result.get("text"):
            text = result["text"][:50000]
            # Updates content + auto-translates if non-Chinese
            update_article_content(conn, rid, text,
                                   doi=result.get("doi", ""),
                                   image_url=result.get("image_url", ""))
            save_snapshot(rid, text)
            fixed += 1
            print(f"  [{fixed}/{total}] ✓ content saved ({len(text)} chars)")
        else:
            print(f"  [{fixed+1}/{total}] × no content fetched")
    print(f"Updated {fixed} articles with content")
    conn.close()


def cmd_backfill_keywords():
    """Re-scan articles from May 1 with updated keyword matching rules (+/! syntax)."""
    import sqlite3
    import theme as theme_mod
    from datetime import datetime, timezone

    for theme_name in ("news", "aam"):
        db_path = config.BASE_DIR / "data" / f"{theme_name}.db"
        if not db_path.exists():
            print(f"[{theme_name}] DB not found, skipping")
            continue

        # Build full keyword list for this theme (theme defaults + DB custom)
        theme_kw = getattr(theme_mod, theme_name.upper()).keywords
        all_kws = sorted(set(kw for group in theme_kw.values() for kw in group))

        # Load custom keywords from DB
        try:
            conn = sqlite3.connect(str(db_path))
            custom = conn.execute("SELECT keyword FROM keywords").fetchall()
            for row in custom:
                kw = row[0].strip()
                if kw and kw not in all_kws:
                    all_kws.append(kw)
        except Exception:
            pass
        finally:
            conn.close()

        # We need to temporarily override config.ALL_KEYWORDS for this theme
        # Save original and restore after
        orig_kw = config.ALL_KEYWORDS
        config.ALL_KEYWORDS = all_kws

        from monitor import keyword_match, relevance_score
        import monitor as monitor_mod

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        rows = conn.execute(
            "SELECT id, title, summary, matched_kw, relevance, published FROM articles "
            "WHERE published >= '2026-05-01' OR (published IS NULL OR published = '')"
        ).fetchall()
        total = len(rows)
        print(f"[{theme_name}] Found {total} articles to re-scan (since 2026-05-01)")

        updated = 0
        for rid, title, summary, old_kw, old_rel, pub in rows:
            text = f"{title} {summary or ''}"
            new_matched = keyword_match(text)
            if not new_matched:
                new_matched = []

            new_kw_str = ", ".join(new_matched)
            new_rel = relevance_score(new_matched, title, summary or "")

            if new_kw_str != (old_kw or "") or new_rel != (old_rel or 0):
                conn.execute(
                    "UPDATE articles SET matched_kw=?, relevance=? WHERE id=?",
                    (new_kw_str, new_rel, rid),
                )
                updated += 1

            if updated % 200 == 0 and updated > 0:
                conn.commit()

        conn.commit()
        conn.close()
        config.ALL_KEYWORDS = orig_kw

        changed_pct = updated / total * 100 if total else 0
        print(f"[{theme_name}] Updated {updated}/{total} articles ({changed_pct:.0f}%)")

    print("Backfill complete.")


def cmd_backup():
    """Backup both databases safely."""
    from monitor import backup_database
    result = backup_database()
    for r in result:
        print(f"  {r}")
    print("Backup complete.")


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
    print(f"  Last 24h:        {last_24h}")
    print(f"  Translated:      {translated}")
    print(f"\n  Latest articles:")
    for r in recent:
        flag = " [中]" if r[4] else ""
        print(f"    [{r[3]:>3}] {r[0][:65]}...{flag}")
        print(f"          {r[1]} · {r[2][:16]}")
    print(f"{'='*50}\n")
    conn.close()


def cmd_patent():
    """Collect patents from Google Patents."""
    import collect_patents
    collect_patents.main()


def cmd_mcp():
    """Run MCP server for AI client integration (stdio or SSE)."""
    from mcp_server import main as mcp_main
    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp_main(transport=transport)


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
    elif cmd == "backfill-keywords":
        cmd_backfill_keywords()
    elif cmd == "backup":
        cmd_backup()
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
    elif cmd == "backfill-clean-content":
        cmd_backfill_clean_content()
    elif cmd == "patent":
        cmd_patent()
    elif cmd == "mcp":
        cmd_mcp()
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
