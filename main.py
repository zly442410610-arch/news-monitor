#!/usr/bin/env python3
"""
News Monitor — multi-theme news monitoring system.

Usage:
    python3 main.py poll              Run one poll cycle (fetch → filter → translate → notify)
    python3 main.py poll --dry-run    Test polling without saving/notifying
    python3 main.py poll --skip-llm   Skip LLM filter (keyword match only)
    python3 main.py daemon            Poll continuously (every N minutes)
    python3 main.py serve             Start web dashboard
    python3 main.py stats             Show article statistics
    python3 main.py backfill-keywords      Re-scan articles with updated keyword rules
    python3 main.py backup                Safely backup both databases
    python3 main.py backfill-clean-content  Re-clean existing content with updated rules
    python3 main.py dedup                  Deduplicate similar articles across all themes
    python3 main.py backfill-reimages [--dry-run] [--theme news|aam|dw] [--strategy smart|full]
                                         Re-extract images for articles with bad/headshot images

Set MONITOR_THEME=news (default) or MONITOR_THEME=aam for different monitor themes.
"""
import logging
import sys
import time
from datetime import datetime, timedelta

import config

log = logging.getLogger(config.LOGGER_NAME)


def cmd_poll(dry_run=False, skip_llm=False, skip_content=False, source_type=None):
    from monitor import run
    run(dry_run=dry_run, skip_llm=skip_llm, skip_content=skip_content, source_type=source_type)


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


def _seconds_until_today(hour: int, minute: int = 0) -> float:
    """计算到今天指定时间的秒数（如果已过则到明天同一时间）"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _ensure_rsshub(start: bool):
    """Start or stop RSSHub service around polling cycles to save resources."""
    import subprocess
    action = "start" if start else "stop"
    result = subprocess.run(["systemctl", action, "rsshub"], capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"RSSHub {action} failed: {result.stderr.strip() or result.stdout.strip()}")
    elif start:
        # Wait for RSSHub to be ready before polling
        import socket
        for _ in range(10):
            try:
                s = socket.create_connection(("127.0.0.1", 1200), timeout=1)
                s.close()
                log.info("RSSHub 已就绪")
                return
            except OSError:
                time.sleep(1)
        log.warning("RSSHub 启动超时（10秒），继续采集")


def cmd_daemon():
    from monitor import run

    _start_cnki_session()

    run_hour = {"news": 3, "aam": 4, "dw": 5}.get(config.THEME_NAME, 4)
    run_minute = 0

    # 首次运行：如果当前时间已过运行时间，先跑一轮
    now = datetime.now()
    if now.hour >= run_hour and now.minute >= run_minute:
        log.info("首次启动，立即执行采集")
        _ensure_rsshub(True)
        try:
            run(dry_run=False)
        except Exception as e:
            log.error(f"首次采集失败: {e}", exc_info=True)
        finally:
            _ensure_rsshub(False)

    log.info(f"Daemon mode: scheduled daily at {run_hour:02d}:{run_minute:02d}")
    while True:
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

        sleep_secs = _seconds_until_today(run_hour, run_minute)
        log.info(f"下一次采集: 明天 {run_hour:02d}:{run_minute:02d} (等待 {int(sleep_secs // 3600)} 小时 {int((sleep_secs % 3600) // 60)} 分钟)")
        time.sleep(sleep_secs)

        _ensure_rsshub(True)
        try:
            run(dry_run=False)
        except Exception as e:
            log.error(f"采集失败: {e}", exc_info=True)
        finally:
            _ensure_rsshub(False)


def cmd_daemon_all():
    """Run all three themes sequentially, starting at 2am daily."""
    import os
    import subprocess

    _start_cnki_session()

    run_hour = 2
    run_minute = 0

    # 首次运行：如果当前时间已过 2:00，先跑一轮
    now = datetime.now()
    if now.hour >= run_hour and now.minute >= run_minute:
        log.info("首次启动，立即执行顺序采集")
        _run_all_themes()

    log.info(f"Daemon-all mode: sequential poll daily at {run_hour:02d}:{run_minute:02d}")
    while True:
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

        sleep_secs = _seconds_until_today(run_hour, run_minute)
        log.info(f"下一次采集: 明天 {run_hour:02d}:{run_minute:02d} (等待 {int(sleep_secs // 3600)} 小时 {int((sleep_secs % 3600) // 60)} 分钟)")
        time.sleep(sleep_secs)

        _run_all_themes()


def _run_all_themes():
    """Start RSSHub, run poll for all three themes sequentially, stop RSSHub."""
    import os
    import subprocess

    _ensure_rsshub(True)

    base_env = os.environ.copy()
    base_env.pop("MONITOR_THEME", None)

    for theme in ("news", "aam", "dw"):
        env = base_env.copy()
        env["MONITOR_THEME"] = theme
        log.info(f"──── [{theme}] 开始采集 ────")
        t_start = datetime.now()
        result = subprocess.run(
            [sys.executable, "main.py", "poll"],
            env=env,
        )
        elapsed = (datetime.now() - t_start).total_seconds()
        if result.returncode == 0:
            log.info(f"──── [{theme}] 采集完成，耗时 {int(elapsed)}s ────")
        else:
            log.error(f"──── [{theme}] 采集失败 (exit={result.returncode})，耗时 {int(elapsed)}s ────")

    _ensure_rsshub(False)

    # 全部采集完成后跨库去重 (优先级: 新闻 > AAM > DW)
    try:
        from monitor import deduplicate_across_themes
        removed = deduplicate_across_themes()
        log.info(f"跨库去重完成: {sum(removed.values())} 篇被移除")
    except Exception as e:
        log.warning(f"跨库去重失败: {e}")

    # 全库语义去重（合并同一事件的多篇报道）
    try:
        from monitor import dedup_all_databases
        dedup_all_databases()
    except Exception as e:
        log.warning(f"全库去重失败: {e}")

    # 全部采集完成后备份三个数据库
    try:
        from monitor import backup_database
        backup_database()
    except Exception as e:
        log.warning(f"采集后自动备份失败: {e}")

    # 自动生成论文精读（如本周尚未生成）
    try:
        _generate_digests()
    except Exception as e:
        log.warning(f"论文精读自动生成失败: {e}")



def _generate_digests():
    """Auto-generate paper digests for all 3 themes if none exist for current week."""
    import os
    import subprocess
    from pathlib import Path

    now = datetime.now()
    year = now.year
    week_num = now.isocalendar()[1]

    base_env = os.environ.copy()
    base_env.pop("MONITOR_THEME", None)

    for theme in ("news", "aam", "dw"):
        digest_glob = Path(__file__).parent / "briefings" / theme / f"paper-digest-{year}-week{week_num}-*.md"
        if list(digest_glob.parent.glob(digest_glob.name)):
            log.info(f"──── [{theme}] 本周论文精读已存在，跳过 ────")
            continue

        env = base_env.copy()
        env["MONITOR_THEME"] = theme
        log.info(f"──── [{theme}] 生成论文精读 ────")
        t_start = datetime.now()
        result = subprocess.run(
            [sys.executable, "main.py", "auto-digest"],
            env=env,
        )
        elapsed = (datetime.now() - t_start).total_seconds()
        if result.returncode == 0:
            log.info(f"──── [{theme}] 论文精读生成完成，耗时 {int(elapsed)}s ────")
        else:
            log.warning(f"──── [{theme}] 论文精读生成失败 (exit={result.returncode})，耗时 {int(elapsed)}s ────")


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


def cmd_backfill_reimages(dry_run=False, strategy="smart", theme=None):
    """Re-extract images for articles that likely have bad/irrelevant images
    (headshots, sidebar thumbnails). Only updates image_url and content_images
    — does NOT trigger re-translation of content."""
    from monitor import fetch_article_content
    import json, re, sqlite3
    from config import BASE_DIR

    themes = [theme] if theme else ("news", "aam", "dw")
    _BAD_PATTERN = re.compile(r"(headshot|avatar|gravatar|[-/]150x150[-.])", re.I)

    for theme_name in themes:
        db_path = BASE_DIR / "data" / f"{theme_name}.db"
        if not db_path.exists():
            print(f"[{theme_name}] DB not found at {db_path}, skipping")
            continue

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT id, url, image_url, content_images FROM articles"
        ).fetchall()
        print(f"\n[{theme_name}] {len(rows)} articles total")

        # Pass 1: identify articles likely having bad images (zero HTTP)
        needs_refetch = []
        for rid, rurl, current_img, current_imgs_json in rows:
            if not current_img:
                needs_refetch.append((rid, rurl))
                continue
            if _BAD_PATTERN.search(current_img):
                needs_refetch.append((rid, rurl))
                continue
            if current_imgs_json and _BAD_PATTERN.search(current_imgs_json):
                needs_refetch.append((rid, rurl))
                continue
            # WordPress thumbnail dimension in existing image_url
            if re.search(r"[-/]\d{2,3}x\d{1,3}\.", current_img):
                needs_refetch.append((rid, rurl))
                continue

        print(f"  Flagged for re-fetch: {len(needs_refetch)}")
        if not needs_refetch:
            conn.close()
            continue

        # Pass 2: re-fetch and update
        updated = 0
        skipped = 0
        for rid, rurl in needs_refetch:
            try:
                result = fetch_article_content(rurl, timeout=20)
            except Exception as e:
                print(f"  FAIL {rid[:8]}: {e}")
                skipped += 1
                continue
            if result and result.get("image_url"):
                new_img = result["image_url"]
                new_imgs = json.dumps(result.get("images", []))
                if dry_run:
                    print(f"  [DRY] {rid[:8]}: {new_img[:60]}")
                else:
                    conn.execute(
                        "UPDATE articles SET image_url = ?, content_images = ? WHERE id = ?",
                        (new_img, new_imgs, rid),
                    )
                    conn.commit()
                updated += 1
                print(f"  {'[DRY]' if dry_run else ''} ✓ {rid[:8]}: {new_img[:60]}")
            else:
                print(f"  - {rid[:8]}: no image returned (skipped)")
                skipped += 1

        print(f"[{theme_name}] {updated} updated, {skipped} skipped")
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
            text = result["text"][:config.MAX_CONTENT_LENGTH]
            # Updates content + auto-translates if non-Chinese
            update_article_content(conn, rid, text,
                                   images=result.get("images", []),
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

    for theme_name in ("news", "aam", "dw"):
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
        removed = 0
        for rid, title, summary, old_kw, old_rel, pub in rows:
            text = f"{title} {summary or ''}"
            new_matched = keyword_match(text)
            if not new_matched:
                new_matched = []

            new_kw_str = ", ".join(new_matched)
            new_rel = relevance_score(new_matched, title, summary or "")

            if new_rel < config.MIN_RELEVANCE_SCORE and not new_matched:
                # No keywords matched and score too low — delete from DB
                conn.execute("DELETE FROM articles WHERE id=?", (rid,))
                removed += 1
            elif new_kw_str != (old_kw or "") or new_rel != (old_rel or 0):
                conn.execute(
                    "UPDATE articles SET matched_kw=?, relevance=? WHERE id=?",
                    (new_kw_str, new_rel, rid),
                )
                updated += 1

            if (updated + removed) % 200 == 0 and (updated + removed) > 0:
                conn.commit()

        conn.commit()
        conn.close()
        config.ALL_KEYWORDS = orig_kw

        changed_pct = updated / total * 100 if total else 0
        print(f"[{theme_name}] Updated {updated}, removed {removed}/{total} articles ({changed_pct:.0f}% updated)")

    print("Backfill complete.")


def cmd_dedup():
    """全库语义去重：三个数据库依次扫描，移出相似度超过阈值的重复文章。"""
    from monitor import dedup_all_databases
    dedup_all_databases()


def cmd_backup():
    """Backup both databases safely."""
    from monitor import backup_database
    result = backup_database()
    for r in result:
        print(f"  {r}")
    print("Backup complete.")




def cmd_auto_digest():
    """Generate paper digest without notification (used by daemon-all)."""
    from monitor import init_db
    from briefing import generate_paper_digest
    conn = init_db()
    try:
        text = generate_paper_digest(conn, days=7, max_papers=10)
        log.info(f"论文精读生成完成: {len(text)} 字符")
        return text
    finally:
        conn.close()


def cmd_backfill_wewe_deep():
    """Deep backfill WeChat articles from 2026-01-01 with LLM filtering + dedup."""
    import backfill_wewe_deep
    backfill_wewe_deep.main()


def cmd_backfill_wewe_all():
    """Full backfill ALL WeChat articles from WeWe-RSS DB (2018–present).
    Supports --dry-run, --skip-llm, --pre-2025, --accounts, --start-id flags."""
    import backfill_wewe_deep
    backfill_wewe_deep.main()


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
    skip_content = "--skip-content" in sys.argv
    source_type = None
    for i, arg in enumerate(sys.argv):
        if arg == "--source-type" and i + 1 < len(sys.argv):
            source_type = sys.argv[i + 1]

    if cmd == "poll":
        cmd_poll(dry_run=dry_run, skip_llm=skip_llm, skip_content=skip_content, source_type=source_type)
    elif cmd == "serve":
        cmd_serve()
    elif cmd == "daemon":
        cmd_daemon()
    elif cmd == "daemon-all":
        cmd_daemon_all()
    elif cmd == "auto-digest":
        cmd_auto_digest()
    elif cmd == "backfill-keywords":
        cmd_backfill_keywords()
    elif cmd == "backup":
        cmd_backup()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "backfill-images":
        cmd_backfill_images()
    elif cmd == "backfill-reimages":
        dry_run = "--dry-run" in sys.argv
        theme = None
        for arg in sys.argv:
            if arg.startswith("--theme="):
                theme = arg.split("=", 1)[1]
        strategy = "smart"
        for arg in sys.argv:
            if arg.startswith("--strategy="):
                strategy = arg.split("=", 1)[1]
        cmd_backfill_reimages(dry_run=dry_run, strategy=strategy, theme=theme)
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
    elif cmd == "dedup":
        cmd_dedup()
    elif cmd == "backfill-wewe-deep":
        cmd_backfill_wewe_deep()
    elif cmd == "backfill-wewe-all":
        cmd_backfill_wewe_all()
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
