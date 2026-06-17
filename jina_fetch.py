"""
Fetch article content via Jina AI reader (r.jina.ai) for articles
that couldn't be fetched by normal methods (Cloudflare, etc.).
"""
import logging
import re
import sqlite3
import sys

import requests

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("jina_fetch")

PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

ARTICLES_NEWS = [
    ("a393acd5506ca96a", "https://www.executivegov.com/articles/dow-pacsci-emc-investment-solid-rocket-motor-duffey"),
    ("ddef596a6fc5fa69", "https://www.war.gov/News/Releases/Release/Article/4493730/department-of-war-invests-191m-t"),
    ("9f50577fbaf63654", "https://indianexpress.com/article/upsc-current-affairs/upsc-essentials/knowledge-nugget-sc"),
    ("e6f6ee7ca2b33be5", "https://fathomjournal.org/28504b2dsmm/1b1a0a81-mv_Ye0tBDaQ.html"),
    ("29acc6af0d69354e", "https://www.eurasiareview.com/07052026-northrop-grummans-breakthroughs-in-solid-rocket-mot"),
    ("30212260bdec5c36", "https://www.metal-am.com/l3harris-plans-1-billion-virginia-solid-rocket-motor-expansion/"),
    ("12a5077e7d8d0f4f", "https://www.businesswire.com/news/home/20260414262031/en/L3Harris-Announces-Billion-Dollar"),
    ("b5e3d177d8b0dbc0", "https://www.mdpi.com/2226-4310/13/3/259"),
]

ARTICLES_AAM = [
    ("2b890f48c6581014", "https://militarnyi.com/en/news/saudi-arabia-first-to-integrate-iris-t-missile-on-f-15/"),
    ("62c850df543bfb0c", "https://www.navalnews.com/naval-news/2026/05/u-s-navys-first-carrier-operated-unmanned-tanker-cleared-f/"),
]

TARGET_SOURCES_NEWS = [
    "executivegov.com",
    "war.gov",
    "indianexpress.com",
    "fathomjournal.org",
    "eurasiareview.com",
    "metal-am.com",
    "businesswire.com",
    "mdpi.com",
]

TARGET_SOURCES_AAM = [
    "militarnyi.com",
    "navalnews.com",
    "defence-blog.com",  # we'll try defence-blog via jina too
]


def fetch_via_jina(url: str, timeout=30) -> dict | None:
    """Fetch article via Jina AI reader. Returns {'text':..., 'image_url':...} or None."""
    jina_url = f"https://r.jina.ai/{url}"
    try:
        r = requests.get(
            jina_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
            proxies=PROXIES,
        )
        if r.status_code != 200:
            log.warning(f"Jina AI returned {r.status_code} for {url[:60]}")
            return None

        raw = r.text
        # Extract markdown content block
        md_match = re.search(r"Markdown Content:\s*\n(.*)", raw, re.DOTALL)
        content = md_match.group(1) if md_match else raw

        # Extract title from markdown
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""

        # Find image from first image reference
        img_match = re.search(r"!\[.*?\]\(([^)]+)\)", content)
        image_url = img_match.group(1) if img_match else ""

        # Extract the article body — try to find the main content area
        # Strategy: find the first long paragraph and take everything from there
        lines = content.split("\n")
        body_start = 0
        for i, line in enumerate(lines):
            s = line.strip()
            # Skip navigation, headers, metadata
            if s.startswith("Skip to") or s.startswith("*   Skip"):
                continue
            if s.startswith("URL Source:") or s.startswith("Markdown Content:"):
                continue
            if len(s) > 100 and not s.startswith("!"):
                body_start = i
                break

        # Find end: search for common footer/sidebar markers
        body_lines = []
        footer_markers = [
            "Most Read", "Related Posts", "Posted in", "Tags:", "Share this:",
            "Free Satnews", "Subscribe", "Navigation", "Manage Profile",
            "View All in", "Submenu", "© ", "All Rights Reserved",
        ]
        for line in lines[body_start:]:
            s = line.strip()
            if any(s.startswith(m) or s == m for m in footer_markers):
                break
            body_lines.append(line)

        article = "\n".join(body_lines).strip()

        # Clean up markdown syntax
        article = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", article)  # links
        article = re.sub(r"!\[.*?\]\([^)]+\)", "", article)  # images
        article = re.sub(r"\*{1,3}", "", article)  # bold/italic
        article = re.sub(r"^#+\s*", "", article, flags=re.MULTILINE)  # headings
        article = re.sub(r"\n{4,}", "\n\n", article)
        article = article.strip()

        if len(article) < 200:
            # Try whole content without any filtering
            article = re.sub(r"\*{1,3}", "", content)
            article = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", article)
            article = re.sub(r"!\[.*?\]\([^)]+\)", "", article)
            article = re.sub(r"^#+\s*", "", article, flags=re.MULTILINE)
            article = re.sub(r"\n{4,}", "\n\n", article)
            article = article.strip()

        return {"text": article[:config.MAX_CONTENT_LENGTH], "image_url": image_url, "title": title}

    except Exception as e:
        log.warning(f"Jina AI failed for {url[:60]}: {e}")
        return None


def batch_fetch(db_path, articles):
    """Fetch articles and update DB."""
    conn = sqlite3.connect(db_path)
    total = len(articles)
    success = 0

    for i, (rid, url) in enumerate(articles, 1):
        # Check if article already has content
        existing = conn.execute("SELECT content FROM articles WHERE id = ?", (rid,)).fetchone()
        if existing and existing[0]:
            log.info(f"  [{i}/{total}] 已有内容，跳过: {url[:60]}")
            continue

        log.info(f"  [{i}/{total}] 正在获取: {url[:60]}...")
        result = fetch_via_jina(url)

        if result and result.get("text") and len(result["text"]) > 200:
            # Clean content
            from monitor import clean_content
            text = clean_content(result["text"][:config.MAX_CONTENT_LENGTH])

            conn.execute("UPDATE articles SET content = ? WHERE id = ?", (text, rid))
            if result.get("image_url"):
                conn.execute("UPDATE articles SET image_url = ? WHERE id = ?", (result["image_url"], rid))
            conn.commit()
            success += 1
            log.info(f"    ✓ {len(text)} chars, img={bool(result['image_url'])}")
        else:
            log.warning(f"    ✗ 无法获取内容")
            # Try with jina AI no proxy for some sites
            try:
                result2 = fetch_via_jina(url)
                if result2 and result2.get("text") and len(result2["text"]) > 200:
                    from monitor import clean_content
                    text = clean_content(result2["text"][:config.MAX_CONTENT_LENGTH])
                    conn.execute("UPDATE articles SET content = ? WHERE id = ?", (text, rid))
                    if result2.get("image_url"):
                        conn.execute("UPDATE articles SET image_url = ? WHERE id = ?", (result2["image_url"], rid))
                    conn.commit()
                    success += 1
                    log.info(f"    ✓ {len(text)} chars (no proxy)")
            except Exception:
                pass

    conn.close()
    return success


if __name__ == "__main__":
    log.info("批量 Jina AI 全文获取开始")

    log.info("\n--- News DB (8篇) ---")
    ok1 = batch_fetch("/root/news-monitor/data/news.db", ARTICLES_NEWS)

    log.info("\n--- AAM DB (2篇标注) ---")
    ok2 = batch_fetch("/root/news-monitor/data/aam.db", ARTICLES_AAM)

    log.info(f"\n完成！成功获取 {ok1 + ok2} 篇")
