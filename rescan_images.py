"""Re-scan article images using the improved image extraction strategy.
Scans articles with missing or poor images and updates image_url + content_images."""
import sys
import os
import json
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rescan_images")


def rescan(db_path: str, label: str):
    os.environ["MONITOR_THEME"] = label  # Ensure correct theme config
    # Force reimport of config module (it reads MONITOR_THEME at import time)
    import config
    import importlib
    importlib.reload(config)

    from monitor import fetch_article_content

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 30000")

    rows = conn.execute(
        "SELECT id, url, image_url FROM articles WHERE image_url IS NULL OR image_url = '' ORDER BY fetched_at DESC"
    ).fetchall()
    log.info(f"[{label}] {len(rows)} articles without images to scan")

    fixed = 0
    failed = 0

    for i, (rid, rurl, old_img) in enumerate(rows):
        if not rurl:
            continue

        log.info(f"[{label}] [{i+1}/{len(rows)}] {rurl[:80]}")
        try:
            content = fetch_article_content(rurl, timeout=10)
            if content:
                new_image = (content.get("image_url") or "").replace("//", "https://") if content.get("image_url", "").startswith("//") else (content.get("image_url") or "")
                new_images = json.dumps(content.get("images", []))
                if new_image or new_images not in ("[]", ""):
                    conn.execute(
                        "UPDATE articles SET image_url=?, content_images=? WHERE id=?",
                        (new_image, new_images, rid),
                    )
                    conn.commit()
                    fixed += 1
                    if new_image:
                        log.info(f"  ✓ {new_image[:60]}")
                    else:
                        log.info(f"  ✓ images only")
                else:
                    log.info(f"  - no image found")
            else:
                failed += 1
                log.info(f"  ✗ fetch failed")
        except Exception as e:
            failed += 1
            log.info(f"  ✗ error: {e}")

    conn.close()
    log.info(f"[{label}] Done: {fixed} updated, {failed} failed")


if __name__ == "__main__":
    db_paths = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg == "news":
                db_paths.append(("/root/news-monitor/data/news.db", "news"))
            elif arg == "aam":
                db_paths.append(("/root/news-monitor/data/aam.db", "aam"))
            else:
                db_paths.append((arg, os.path.basename(arg)))
    else:
        db_paths = [
            ("/root/news-monitor/data/news.db", "news"),
            ("/root/news-monitor/data/aam.db", "aam"),
        ]

    for db_path, label in db_paths:
        rescan(db_path, label)
