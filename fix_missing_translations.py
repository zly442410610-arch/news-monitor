"""
Fix missing title/summary translations for AAM theme.
Re-translates articles where translated_title is empty but title is non-Chinese.
"""
import logging
import sqlite3
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fix_translations")

sys.path.insert(0, ".")

import config
# Override theme to AAM
import os
os.environ["MONITOR_THEME"] = "aam"
# Re-import with correct theme
import importlib
config = importlib.reload(config)

from translator import translate_article, contains_chinese
from translator_glossary import apply_glossary


def main():
    theme = "aam"
    db_path = f"data/{theme}.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find articles with missing translation
    rows = conn.execute(
        "SELECT id, title, summary FROM articles "
        "WHERE (translated_title IS NULL OR translated_title = '') "
        "AND title NOT GLOB '*[一-鿿]*' "
        "ORDER BY published DESC"
    ).fetchall()

    total = len(rows)
    log.info(f"[{theme}] 找到 {total} 篇未翻译的文章")

    if total == 0:
        log.info("没有需要翻译的文章")
        return

    success = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        rid = row["id"]
        title = row["title"]
        summary = row["summary"] or ""

        # Double check not already translated
        existing = conn.execute(
            "SELECT translated_title FROM articles WHERE id = ?", (rid,)
        ).fetchone()
        if existing and existing["translated_title"]:
            skipped += 1
            log.info(f"  [{i}/{total}] 跳过（已有翻译）: {title[:50]}")
            continue

        try:
            result = translate_article(title, summary)
            if result and result.get("title") and contains_chinese(result["title"]):
                t_title = result["title"]
                t_summary = result.get("summary", "")
                conn.execute(
                    "UPDATE articles SET translated_title = ?, translated_summary = ?, is_translated = 1 WHERE id = ?",
                    (t_title, t_summary, rid)
                )
                conn.commit()
                success += 1
                log.info(f"  [{i}/{total}] ✓ {title[:50]} → {t_title[:40]}")
            else:
                failed += 1
                log.warning(f"  [{i}/{total}] ✗ {title[:50]} — 翻译返回不含中文")
        except Exception as e:
            failed += 1
            log.warning(f"  [{i}/{total}] ✗ {title[:50]} — {e}")

        # Small delay between individual translations
        time.sleep(1)

    conn.close()
    log.info(f"完成: 成功{success}, 跳过{skipped}, 失败{failed}")


if __name__ == "__main__":
    main()
