#!/usr/bin/env python3
"""Backfill arXiv articles: extract PDF text, first-page thumbnail, translation."""
import logging
import sqlite3
import sys
from pathlib import Path

# Ensure we can import from project root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from monitor import _extract_arxiv_pdf, _extract_arxiv_image, log
from translator import translate_content, is_predominantly_chinese

# Map database filenames to theme names
DB_THEME_MAP = {
    "news.db": ("news", config.BASE_DIR / "snapshots" / "news"),
    "aam.db": ("aam", config.BASE_DIR / "snapshots" / "aam"),
}


def get_arxiv_articles(db_path: Path) -> list[dict]:
    """Get arXiv articles with empty or short content."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """SELECT id, url, title, summary, content, translated_content
           FROM articles
           WHERE url LIKE '%arxiv.org%'
             AND (content IS NULL OR length(content) < 500)
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_article(db_path: Path, article_id: str, content: str,
                   translated_content: str, image_url: str):
    """Update article in database with new content, translation, and image."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE articles SET content=?, translated_content=?, image_url=? WHERE id=?",
        (content, translated_content, image_url, article_id),
    )
    conn.commit()
    conn.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for db_name, (theme, snap_dir) in DB_THEME_MAP.items():
        db_path = config.BASE_DIR / "data" / db_name
        if not db_path.exists():
            log.info(f"Database not found: {db_path}, skipping")
            continue

        articles = get_arxiv_articles(db_path)
        if not articles:
            log.info(f"{theme}: No arXiv articles needing backfill")
            continue

        log.info(f"{theme}: {len(articles)} arXiv articles to backfill")

        # Ensure images directory exists
        img_dir = snap_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        for i, art in enumerate(articles):
            art_id = art["id"]
            url = art["url"]
            title = art["title"]
            log.info(f"[{i+1}/{len(articles)}] {theme}: {title[:60]}...")

            # Step 1: Extract PDF text
            text = _extract_arxiv_pdf(url, timeout=60)
            if not text:
                log.warning(f"  PDF text extraction failed")
                # Still try image even if text fails
            else:
                log.info(f"  PDF text: {len(text)} chars")
                # Truncate to fit within reasonable limits
                text = text[:8000]

            # Step 2: Extract first-page thumbnail
            img_bytes = _extract_arxiv_image(url, timeout=30)
            img_url = ""
            if img_bytes:
                safe_id = art_id.replace("/", "_").replace(":", "_")
                img_filename = f"{safe_id}.png"
                img_path = img_dir / img_filename
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                img_url = f"/images/{img_filename}"
                log.info(f"  Thumbnail saved: {img_path} ({len(img_bytes)} bytes)")
            else:
                log.info(f"  No thumbnail extracted")

            # Step 3: Translate content (if English and text was extracted)
            translated = art.get("translated_content") or ""
            if text and len(text) > 500 and not is_predominantly_chinese(text):
                if not translated:
                    log.info(f"  Translating...")
                    translated = translate_content(text) or ""
                    if translated:
                        log.info(f"  Translation: {len(translated)} chars")
            elif text and is_predominantly_chinese(text):
                log.info(f"  Content is already Chinese, skipping translation")

            # Step 4: Update database
            if text or img_url or (translated and not art.get("translated_content")):
                update_article(db_path, art_id, text or art.get("content", ""),
                               translated, img_url)
                log.info(f"  Updated ✓")
            else:
                log.info(f"  No changes to save")

    log.info("Backfill complete")


if __name__ == "__main__":
    main()
