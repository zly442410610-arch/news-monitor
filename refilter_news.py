#!/usr/bin/env python3
"""Re-filter all existing news articles through LLM and delete irrelevant ones."""
import os
import re
import sqlite3
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["MONITOR_THEME"] = "news"

import config
from llm_client import create_completion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refilter")


def main():
    db_path = config.DB_PATH
    log.info("Database: %s", db_path)
    conn = sqlite3.connect(db_path)

    # Get articles without LLM filter (llm_relevance IS NULL or 0)
    cur = conn.execute(
        "SELECT id, title, summary, matched_kw FROM articles "
        "WHERE llm_relevance IS NULL OR llm_relevance = 0"
    )
    rows = cur.fetchall()
    log.info("未过滤文章: %d 篇", len(rows))

    if not rows:
        log.info("没有需要过滤的文章")
        return

    # Get the news filter prompt
    from theme import get_theme
    theme = get_theme()
    filter_prompt = theme.llm_filter_prompt

    # Extract rules (before "Article title:")
    cut = filter_prompt.find("Article title:")
    rules = filter_prompt[:cut].strip() if cut > 0 else filter_prompt

    batch_size = 20
    total_deleted = 0
    total_kept = 0
    total_batches = (len(rows) + batch_size - 1) // batch_size

    for bstart in range(0, len(rows), batch_size):
        batch = rows[bstart : bstart + batch_size]

        items = []
        for i, art in enumerate(batch, 1):
            title = (art[1] or "").replace("{", "{{").replace("}", "}}")
            summary = (art[2] or "")[:500].replace("{", "{{").replace("}", "}}")
            items.append(f"{i}. Title: {title}\n   Summary: {summary}")

        prompt = f"""{rules}

For EACH article above, reply with exactly one line in the format "INDEX: YES/NO SCORE: N" where N is relevance 0-10.
Reply ONLY with these lines.

{chr(10).join(items)}"""

        batch_num = bstart // batch_size + 1
        log.info(
            "Batch %d/%d (%d articles, deleted so far: %d)...",
            batch_num,
            total_batches,
            len(batch),
            total_deleted,
        )

        try:
            answer = create_completion(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50 + len(batch) * 15,
            ).strip()
        except Exception as e:
            log.warning("Batch %d failed: %s", batch_num, e)
            continue

        if not answer:
            log.warning("Empty response for batch %d, skipping", batch_num)
            continue

        batch_deleted = 0
        for line in answer.split("\n"):
            line = line.strip()
            m = re.match(
                r"(\d+)\s*[.。、:：]?\s*(?:INDEX\s*[:：]\s*)?(YES|NO)\s+SCORE\s*[:：]\s*([\d.]+)",
                line,
                re.IGNORECASE,
            )
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(batch):
                    art_id = batch[idx][0]
                    accepted = m.group(2).upper() == "YES"
                    score = min(10.0, max(0.0, float(m.group(3))))

                    if accepted:
                        conn.execute(
                            "UPDATE articles SET llm_relevance = ? WHERE id = ?",
                            (int(score * 10), art_id),
                        )
                        total_kept += 1
                    else:
                        conn.execute(
                            "DELETE FROM articles WHERE id = ?", (art_id,)
                        )
                        total_deleted += 1
                        batch_deleted += 1

        conn.commit()
        log.info(
            "  → 本批删除 %d, 累计删除 %d, 保留 %d",
            batch_deleted,
            total_deleted,
            total_kept,
        )

    conn.close()
    log.info("=== 完成！删除 %d 篇, 保留 %d 篇 ===", total_deleted, total_kept)


if __name__ == "__main__":
    main()
