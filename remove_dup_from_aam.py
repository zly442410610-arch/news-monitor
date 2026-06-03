#!/usr/bin/env python3
"""
Remove from aam.db articles that already exist in news.db (by exact title match).

Usage:
    python3 remove_dup_from_aam.py               # dry-run (preview)
    python3 remove_dup_from_aam.py --execute     # actually delete
"""
import logging
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("remove_dup")

NEWS_DB = BASE / "data" / "news.db"
AAM_DB = BASE / "data" / "aam.db"


def main():
    execute = "--execute" in sys.argv

    if not NEWS_DB.exists():
        log.error(f"news.db not found: {NEWS_DB}")
        sys.exit(1)
    if not AAM_DB.exists():
        log.error(f"aam.db not found: {AAM_DB}")
        sys.exit(1)

    # Load news titles
    n_conn = sqlite3.connect(str(NEWS_DB))
    news_titles = {
        r[0].lower().strip()
        for r in n_conn.execute("SELECT title FROM articles WHERE title IS NOT NULL")
    }
    log.info(f"news.db: {len(news_titles)} articles")

    # Find AAM articles by matching news titles
    a_conn = sqlite3.connect(str(AAM_DB))
    a_conn.row_factory = sqlite3.Row
    a_all = a_conn.execute(
        "SELECT id, title, url, source FROM articles ORDER BY fetched_at DESC"
    ).fetchall()
    log.info(f"aam.db: {len(a_all)} articles")

    to_delete = []
    for row in a_all:
        if row["title"] and row["title"].lower().strip() in news_titles:
            to_delete.append(row)

    if not to_delete:
        log.info("No duplicate articles found.")
        return

    log.info(f"\nFound {len(to_delete)} duplicate articles in aam.db:")
    for row in to_delete:
        log.info(f"  {row['id']} | {row['title'][:55]} | {row['source']}")

    if not execute:
        log.info(f"\nDry-run: {len(to_delete)} articles would be deleted.")
        log.info("Run with --execute to actually delete.")
        return

    # Execute deletion
    ids = [row["id"] for row in to_delete]
    placeholders = ",".join("?" for _ in ids)
    a_conn.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", ids)
    a_conn.commit()
    log.info(f"\nDeleted {len(to_delete)} articles from aam.db.")

    # Verify
    remaining = a_conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    log.info(f"Remaining in aam.db: {remaining}")

    n_conn.close()
    a_conn.close()


if __name__ == "__main__":
    main()
