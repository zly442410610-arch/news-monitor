"""
Batch re-translate all articles using NVIDIA model with parallel processing.
Run after changing translation model/prompt to upgrade existing translations.
"""
import logging
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch_translate")

sys.path.insert(0, ".")
from translator import translate_content, is_predominantly_chinese
from translator_glossary import apply_glossary


def re_translate(args):
    """Translate a single article. Returns (rid, success, msg)."""
    rid, title, content = args
    if not content or len(content.strip()) < 100:
        return rid, False, "内容太短"
    if is_predominantly_chinese(content):
        return rid, True, "已是中文"  # mark as done, but no need to save translation

    try:
        result = translate_content(content)
        if result and len(result) > 50:
            result = apply_glossary(result, "news")  # apply shared + news glossary
            result = apply_glossary(result, "aam")   # also apply aam glossary
            return rid, True, f"✓ {len(result)}字"
        return rid, False, "翻译返回空"
    except Exception as e:
        return rid, False, str(e)[:60]


def main():
    db_paths = {
        "news": "data/news.db",
        "aam": "data/aam.db",
    }

    for theme, db_path in db_paths.items():
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT id, title, content FROM articles "
            "WHERE content != '' AND content IS NOT NULL AND length(content) > 100"
        ).fetchall()
        conn.close()

        total = len(rows)
        log.info(f"[{theme}] 共 {total} 篇需要重新翻译")

        batch = rows
        success = 0
        failed = 0
        skipped = 0

        with ThreadPoolExecutor(max_workers=8) as executor:
            fut_map = {executor.submit(re_translate, (rid, title, content)): (rid, title) for rid, title, content in batch}
            done = 0
            for fut in as_completed(fut_map):
                rid, title = fut_map[fut]
                done += 1
                try:
                    rid2, ok, msg = fut.result()
                    if ok and msg == "已是中文":
                        skipped += 1
                    elif ok:
                        success += 1
                        # Save to DB
                        conn2 = sqlite3.connect(db_path)
                        conn2.execute("UPDATE articles SET translated_content = ?, is_translated = 1 WHERE id = ?", (rid2, rid2))
                        conn2.commit()
                        conn2.close()
                        log.info(f"  [{done}/{total}] ✓ {title[:40]} — {msg}")
                    else:
                        failed += 1
                        log.warning(f"  [{done}/{total}] ✗ {title[:30]} — {msg}")
                except Exception as e:
                    failed += 1
                    log.warning(f"  [{done}/{total}] ✗ {title[:30]} — {str(e)[:50]}")

        log.info(f"[{theme}] 完成: 翻译{success}, 跳过{skipped}, 失败{failed}")

    log.info("全部完成！")


if __name__ == "__main__":
    main()
