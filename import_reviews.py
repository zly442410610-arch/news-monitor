"""
Import review papers into news monitor databases.
Run after polls complete to avoid DB lock conflicts.
"""
import hashlib
import sqlite3
import time
import logging
import sys
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("import_reviews")


def make_id(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:24]


def import_paper(db_path: str, theme: str, title: str, translated_title: str,
                  url: str, source: str, content: str, article_type: str = "paper",
                  published: str = "", author: str = "",
                  translated_content: str = ""):
    """Insert a review paper into the database."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 30000")
    cur = conn.cursor()

    aid = make_id(title)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("SELECT id FROM articles WHERE id = ?", (aid,))
    if cur.fetchone():
        log.warning(f"Article already exists, skipping: {title[:60]}")
        conn.close()
        return

    # Truncate summary to first 1000 chars
    summary = re.sub(r'\s+', ' ', content[:1500]).strip()[:1000]

    cur.execute("""
        INSERT INTO articles (id, title, url, source, published, fetched_at,
                              summary, relevance, is_read, is_archived,
                              translated_title, is_translated, author,
                              article_type, content, translated_content)
        VALUES (?, ?, ?, ?, ?, ?,
                ?, ?, 0, 0,
                ?, ?, ?,
                ?, ?, ?)
    """, (
        aid, title, url, source, published, now,
        summary, 100,  # relevance=100 for high-quality review
        translated_title, 1 if translated_content else 0, author,
        article_type, content, translated_content or ""
    ))

    conn.commit()
    conn.close()
    log.info(f"Imported: {translated_title[:60]} ({len(content)} chars)")


def main():
    # ── Read saved texts ──────────────────────────────────────────────
    texts = {}
    for key, path in [
        ("ramjet", "/tmp/ramjet_review_text.txt"),
        ("aam2025", "/tmp/aam_review_2025_text.txt"),
        ("rde_cn", "/tmp/rde_review_cn_text.txt"),
        ("sr_cn", "/tmp/sr_review_text.txt"),
    ]:
        with open(path) as f:
            texts[key] = f.read()

    # ── News DB (固体动力) ─────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Importing into NEWS database (固体动力)...")

    # 1. Ramjet combustion instabilities review (English)
    import_paper(
        db_path="/root/news-monitor/data/news.db", theme="news",
        title="Research and Development on Ramjet Combustion Instabilities",
        translated_title="冲压发动机燃烧不稳定性研究进展",
        url="https://link.springer.com/article/10.1007/s11630-025-2103-8",
        source="Journal of Thermal Science (Springer)",
        content=texts["ramjet"],
        published="2025",
        author="GUAN Yiheng, BECKER Sid, ZHAO Dan",
        article_type="paper",
    )

    # 2. 满装填固体火箭发动机研究现状及未来发展探析 (Chinese)
    import_paper(
        db_path="/root/news-monitor/data/news.db", theme="news",
        title="满装填固体火箭发动机研究现状及未来发展探析",
        translated_title="满装填固体火箭发动机研究现状及未来发展探析",
        url="https://pubs.cstam.org.cn/article/doi/10.7673/j.issn.1006-2793.2025.02.001",
        source="固体火箭技术",
        content=texts["sr_cn"],
        published="2025",
        author="郭运强",
        article_type="paper",
    )

    # 3. 连续旋转爆震发动机发展现状及使用前景 (Chinese)
    import_paper(
        db_path="/root/news-monitor/data/news.db", theme="news",
        title="连续旋转爆震发动机发展现状及使用前景",
        translated_title="连续旋转爆震发动机发展现状及使用前景",
        url="https://gthjjs.spacejournal.cn/article/id/c33efc18-89cd-449e-a3aa-4e8d0bd19ab1",
        source="空天防御",
        content=texts["rde_cn"],
        published="2025",
        author="陈铮, 李晓龙, 徐广川, 赵文文, 杜溢华, 殷玮, 马虎",
        article_type="paper",
    )

    # ── AAM DB ─────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Importing into AAM database...")

    # 4. 2025年国外空空导弹发展回顾 (Chinese)
    import_paper(
        db_path="/root/news-monitor/data/aam.db", theme="aam",
        title="2025年国外空空导弹发展回顾",
        translated_title="2025年国外空空导弹发展回顾",
        url="https://www.qk.sjtu.edu.cn/ktfy/EN/Y2026/V9/I2/105",
        source="空天防御",
        content=texts["aam2025"],
        published="2026",
        author="夏晓靖, 唐楚淳, 杨闯, 桑晨, 惠文智",
        article_type="paper",
    )

    log.info("=" * 60)
    log.info("All done!")


if __name__ == "__main__":
    main()
