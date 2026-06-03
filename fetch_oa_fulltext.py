#!/usr/bin/env python3
"""
Fetch OA full text for CNKI articles using journal websites (Playwright).

Currently supports:
  - 航空学报 (hkxb.buaa.edu.cn) — OA full text via RichHTML
  - 弹箭与制导学报 (www.prgjournal.cn) — OA full text embedded in article page

Usage:
    python3 fetch_oa_fulltext.py                     # both databases
    python3 fetch_oa_fulltext.py --news-only         # news.db only
    python3 fetch_oa_fulltext.py --aam-only          # aam.db only
    python3 fetch_oa_fulltext.py --limit 3           # limit articles
"""
import asyncio
import json
import logging
import re
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("oa_fulltext")

sys.path.insert(0, str(BASE))
import config


# ── Journal registry ──────────────────────────────────────────────────────────

# Mapping: CNKI RSS source name → journal info
JOURNAL_REGISTRY = {
    "航空学报": {
        "website": "https://hkxb.buaa.edu.cn",
        "oa": True,
        "fetch_func": "_fetch_hkxb",
    },
    "弹箭与制导学报": {
        "website": "http://www.prgjournal.cn",
        "oa": True,
        "fetch_func": "_fetch_prgjournal",
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_shutong_cookies() -> dict:
    """Load shutong cookies for potential proxy use."""
    jar = config.BASE_DIR / ".shutong_cookies.json"
    if jar.exists():
        try:
            data = json.loads(jar.read_text())
            return data.get("cookies", {})
        except Exception:
            pass
    return {}


def get_articles_without_content(conn: sqlite3.Connection, journal_name: str = None, limit: int = None) -> list[dict]:
    """Get CNKI articles missing content, optionally filtered by journal."""
    query = """
        SELECT id, title, url, source, published, author,
               length(content) as content_len, doi
        FROM articles
        WHERE url LIKE '%cnki.net%'
          AND (content IS NULL OR length(content) < 300)
    """
    params = []
    if journal_name:
        query += " AND source = ?"
        params.append(f"CNKI - {journal_name}")
    query += " ORDER BY published DESC"
    if limit:
        query += f" LIMIT {limit}"
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(query, params)]


def extract_doi_from_article_page(text: str) -> str:
    """Extract DOI from journal article page HTML."""
    m = re.search(r'doi[\s:]*["\']?(10\.\d{4,}/[^"\'\s<>]+)', text, re.IGNORECASE)
    return m.group(1) if m else ""


# ── 航空学报 fetcher ────────────────────────────────────────────────────────────

async def _fetch_hkxb(page, article: dict) -> dict:
    """Fetch full text from 航空学报 (hkxb.buaa.edu.cn).

    Strategy: Navigate archive → year → issue → find article by title → RichHTML.
    Returns {text, doi, pdf_url} or raises.
    """
    title = article["title"].strip()

    # Step 1: Go to archive page
    await page.goto(
        "https://hkxb.buaa.edu.cn/CN/article/showTenYearOldVolumn.do",
        wait_until="networkidle",
        timeout=20000,
    )

    # Step 2: Navigate to the year archive page
    year = _detect_year(title)
    await page.goto(
        f"https://hkxb.buaa.edu.cn/CN/article/showTenYearVolumnDetail.do?nian={year}",
        wait_until="networkidle",
        timeout=20000,
    )

    # Step 3: Find issue links on the year page
    issue_links = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('a[href*="volumn_"]'))
            .map(a => ({href: a.href, text: a.textContent.trim()}))
    """)
    if not issue_links:
        raise Exception("No issue links found on year page")

    # Step 4: Try each issue (newest first) to find the article by title
    for issue in issue_links:
        log.info(f"  Checking issue: {issue['text'][:40]}")
        await page.goto(issue["href"], wait_until="networkidle", timeout=20000)

        # Wait for article links to render (volumn page loads articles via JS)
        try:
            await page.wait_for_selector('a[href*="10.7527/"]', timeout=10000)
        except Exception:
            log.warning("  No DOI links found on this issue page (may be empty issue)")
            continue

        await asyncio.sleep(1)  # extra settling for any dynamic content

        # Find article links on the issue page (DOI links)
        article_url = await page.evaluate(f"""() => {{
            let links = Array.from(document.querySelectorAll('a[href*="10.7527/"]'));
            for (let a of links) {{
                let text = (a.textContent || '').trim().toLowerCase();
                if (text.includes('{title[:30].lower()}')) return a.href;
            }}
            return null;
        }}""")

        if article_url:
            log.info(f"  Found article: {article_url[:80]}")
            # Step 5: Click article link and get RichHTML full text
            result = await _open_article_and_get_richhtml(page, article_url, title)
            return result

    # Step 5: Fallback — search 最新录用 (Online First) page for the article title
    log.info("  Not found in issues, checking 最新录用 (Online First)...")
    try:
        result = await _search_hkxb_online_first(page, title)
        return result
    except Exception as e:
        raise Exception(f"Article not found: {e}")


async def _search_hkxb_online_first(page, title: str) -> dict:
    """Search 航空学报 最新录用 (Online First) page by article title.

    Online First articles are not yet assigned to an issue, so they only
    appear on the showNewArticle.do listing.
    """
    await page.goto(
        "https://hkxb.buaa.edu.cn/CN/article/showNewArticle.do",
        wait_until="networkidle",
        timeout=20000,
    )
    await asyncio.sleep(2)

    # Try up to 3 pages of results (20 articles per page)
    for page_num in range(1, 4):
        if page_num > 1:
            await page.goto(
                f"https://hkxb.buaa.edu.cn/CN/article/showNewArticle.do?pager={page_num}",
                wait_until="networkidle",
                timeout=20000,
            )
            await asyncio.sleep(2)

        # Find article link matching title
        article_url = await page.evaluate(f"""() => {{
            let links = Array.from(document.querySelectorAll('a[href*="/CN/10.7527/"]'));
            let seen = new Set();
            for (let a of links) {{
                let href = a.href;
                if (href.includes('#') || href.includes('doi.org') || seen.has(href)) continue;
                seen.add(href);
                let text = (a.textContent || '').trim().toLowerCase();
                if (text.includes('{title[:30].lower()}')) return href;
            }}
            return null;
        }}""")

        if article_url:
            log.info(f"  Found online first article: {article_url[:80]}")
            return await _open_article_and_get_richhtml(page, article_url, title)

        log.info(f"  Page {page_num}: not found")

    raise Exception(f"Article not found on 最新录用 page: {title[:40]}")


def _detect_year(title: str) -> str:
    """Try to determine publication year from article URL or guess."""
    return "2026"


# ── 弹箭与制导学报 fetcher ─────────────────────────────────────────────────────

PRG_DOI_PREFIX = "10.15892/"


async def _fetch_prgjournal(page, article: dict) -> dict:
    """Fetch full text from 弹箭与制导学报 (www.prgjournal.cn).

    Magtech platform: article page already embeds full text HTML.
    Strategy: Navigate archive → year → issue → find article by title → read page text.
    """
    title = article["title"].strip()
    year = _detect_year(title)

    # Step 1: Go to archive page for the year
    await page.goto(
        f"http://www.prgjournal.cn/CN/archive/{year}",
        wait_until="networkidle",
        timeout=20000,
    )
    await asyncio.sleep(1)

    # Step 2: Find issue links
    issue_links = await page.evaluate(f"""() =>
        Array.from(document.querySelectorAll('a[href*="/CN/Y{year}/V"]'))
            .map(a => ({{href: a.href, text: a.textContent.trim()}}))
    """)
    if not issue_links:
        raise Exception("No issue links found on archive page")

    # Step 3: Try each issue (newest first) to find article by title
    for issue in issue_links:
        log.info(f"  Checking issue: {issue['text'][:40]}")
        await page.goto(issue["href"], wait_until="networkidle", timeout=20000)
        await asyncio.sleep(1)

        # Find article DOI matching the title on the issue page
        # DOI links point to doi.org, we extract the DOI and construct article URL
        article_doi = await page.evaluate(f"""() => {{
            let links = Array.from(document.querySelectorAll('a[href*="{PRG_DOI_PREFIX}"]'));
            let seen = new Set();
            for (let a of links) {{
                let href = a.href;
                if (href.includes('#') || seen.has(href)) continue;
                seen.add(href);
                let parentText = (a.closest('tr, div, li') || a.parentElement || a).textContent || '';
                if (parentText.toLowerCase().includes('{title[:30].lower()}')) return href;
            }}
            return null;
        }}""")

        if article_doi:
            log.info(f"  Found DOI link: {article_doi[:80]}")
            # Extract DOI value from the href (which may be doi.org URL or prgjournal URL)
            doi_match = re.search(r'(10\.15892/\S+)', article_doi)
            if not doi_match:
                continue
            doi = doi_match.group(1).rstrip('/')
            article_url = f"http://www.prgjournal.cn/CN/{doi}"
            return await _extract_prgjournal_fulltext(page, article_url, title)

    raise Exception(f"Article not found in any issue of {year}")


async def _extract_prgjournal_fulltext(page, article_url: str, title: str) -> dict:
    """Open article page on prgjournal.cn and extract full text.

    Unlike 航空学报, the full text is already embedded in the article HTML
    (Magtech platform renders all sections + references inline).
    """
    await page.goto(article_url, wait_until="networkidle", timeout=20000)
    await asyncio.sleep(1)

    # Extract DOI from page
    page_text = await page.evaluate("document.body.innerText")
    doi = extract_doi_from_article_page(page_text)

    # Check that full text is present (article body + references)
    if len(page_text) < 500:
        # Fallback: try PDF download
        log.info("  Article page too short, trying PDF download...")
        return await _get_article_via_pdf(page, article_url, title)

    text = _clean_prgjournal_text(page_text)
    log.info(f"  Full text length: {len(text)} chars")

    if len(text) < 500:
        raise Exception(f"Extracted content too short: {len(text)} chars")

    return {"text": text, "doi": doi, "pdf_url": article_url}


def _clean_prgjournal_text(text: str) -> str:
    """Clean navigation/footer boilerplate from 弹箭与制导学报 article page."""
    lines = text.split("\n")
    content_start = 0
    content_end = len(lines)

    # Find start of main content: look for DOI, ISSN, or abstract
    for i, line in enumerate(lines):
        l = line.strip()
        if l.startswith("DOI:") or l.startswith("doi:"):
            # Content starts a few lines after DOI
            content_start = max(0, i + 1)
            break

    # Find end: stop at 陕ICP备 or copyright
    for i in range(content_start, len(lines)):
        l = lines[i].strip()
        if "陕ICP备" in l or "版权所有" in l or "地址：" in l:
            content_end = i
            break

    core = "\n".join(lines[content_start:content_end])
    # Remove navigation menu lines that appear as single short words
    nav_keywords = ["高级检索", "首页", "期刊介绍", "编委会", "期刊在线", "投稿指南",
                    "征稿简则", "开放获取", "出版伦理", "联系我们", "English",
                    "当期目录", "过刊浏览", "阅读排行", "下载排行", "E-mail Alert"]
    cleaned_lines = []
    for line in core.split("\n"):
        stripped = line.strip()
        if stripped in nav_keywords:
            # Only skip if it's a standalone nav item (short, no other context)
            continue
        if stripped == "摘要" or stripped == "Abstract":
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


async def _open_article_and_get_richhtml(page, article_url: str, title: str) -> dict:
    """Open article page, click RichHTML link, wait for full text page, extract text."""
    # Navigate to article DOI page
    await page.goto(article_url, wait_until="networkidle", timeout=20000)
    page_text = await page.evaluate("document.body.innerText")

    # Extract DOI from page
    doi = extract_doi_from_article_page(page_text)

    # Click RichHTML link — this opens a new page in the same tab
    rich_link = await page.query_selector("a.black-bg.btn-menu:has-text('RichHTML')")
    if not rich_link:
        log.info("  No RichHTML link, trying PDF download instead...")
        return await _get_article_via_pdf(page, article_url, title)

    # Get the target URL from onclick handler
    onclick = await rich_link.get_attribute("onclick") or ""
    # The onclick calls lsdy1('RICH_HTML', id, baseUrl, year, issn)
    # The RichHTML URL pattern: {baseUrl}/article/{year}/{issn}
    m = re.search(r"lsdy1\('RICH_HTML','(\d+)','([^']+)','(\d+)','([^']+)'", onclick)
    if m:
        article_id, base_url, yr, issn_path = m.group(1), m.group(2), m.group(3), m.group(4)
        log.info(f"  RichHTML: id={article_id}, base={base_url}, issn={issn_path[:40]}")
        # The RichHTML URL format from observation:
        rich_url = f"{base_url}/article/{yr}/{issn_path}"
        log.info(f"  RichHTML URL: {rich_url}")
        await page.goto(rich_url, wait_until="networkidle", timeout=20000)
    else:
        # Fallback: try clicking
        async with page.expect_navigation(wait_until="networkidle", timeout=15000):
            await rich_link.click()
        # May have opened a new page
        pages = page.context.pages
        if len(pages) > 1:
            page = pages[-1]

    await asyncio.sleep(2)

    # Extract full text from RichHTML page
    rich_text = await page.evaluate("document.body.innerText")
    log.info(f"  RichHTML text length: {len(rich_text)}")

    if len(rich_text) < 500:
        raise Exception(f"RichHTML content too short: {len(rich_text)} chars")

    # Clean up: remove header/footer boilerplate
    text = _clean_richhtml_text(rich_text)

    # Try to find PDF link
    pdf_url = await page.evaluate("""() => {
        let links = Array.from(document.querySelectorAll('a[href*=".pdf"]'));
        return links.length > 0 ? links[0].href : '';
    }""")

    return {"text": text, "doi": doi, "pdf_url": pdf_url}


async def _get_article_via_pdf(page, article_url: str, title: str) -> dict:
    """Download article PDF and extract text using PyMuPDF.

    Used for online-first articles that don't have RichHTML view.
    """
    import fitz  # PyMuPDF

    # Ensure the page is on the article page
    if page.url != article_url:
        await page.goto(article_url, wait_until="networkidle", timeout=20000)

    page_text = await page.evaluate("document.body.innerText")
    doi = extract_doi_from_article_page(page_text)

    # Find the PDF button's article ID from onclick
    article_id = await page.evaluate("""() => {
        let links = Array.from(document.querySelectorAll('a.black-bg.btn-menu'));
        for (let a of links) {
            let oc = a.getAttribute('onclick') || '';
            let m = oc.match(/lsdy1\\('PDF','(\\d+)'/);
            if (m) return m[1];
        }
        return null;
    }""")

    if not article_id:
        raise Exception("No PDF article ID found on page")

    log.info(f"  Downloading PDF for article ID {article_id}...")

    # Trigger PDF download via lsdy1 and capture it
    async with page.expect_download(timeout=30000) as download_info:
        await page.evaluate(
            f"lsdy1('PDF','{article_id}','https://hkxb.buaa.edu.cn','0','0')"
        )

    download = await download_info.value
    pdf_path = await download.path()
    log.info(f"  PDF downloaded to: {pdf_path} ({download.suggested_filename})")

    # Extract text from PDF using PyMuPDF
    doc = fitz.open(pdf_path)
    pdf_text = ""
    for page_num in range(doc.page_count):
        pdf_text += doc[page_num].get_text()
    doc.close()

    if len(pdf_text) < 500:
        raise Exception(f"PDF text too short: {len(pdf_text)} chars")

    log.info(f"  PDF text length: {len(pdf_text)} chars")
    return {"text": pdf_text.strip(), "doi": doi, "pdf_url": article_url}


def _clean_richhtml_text(text: str) -> str:
    """Remove navigation headers, footers, and sidebar from RichHTML page."""
    lines = text.split("\n")
    # Find the start of actual article content — usually after author affiliations
    # and before references or footer
    content_start = 0
    content_end = len(lines)

    for i, line in enumerate(lines):
        line = line.strip()
        # Article content typically starts with the main text (after abstract)
        # Look for the first paragraph that isn't navigation
        if line and len(line) > 40 and not any(
            kw in line
            for kw in ["联系我们", "关于我们", "编委会", "封面文章", "友情链接", "版权所有", "地址：", "邮政编码"]
        ):
            if content_start == 0:
                content_start = i
        # Stop at copyright/footer
        if "版权所有" in line or "地址：" in line:
            content_end = i
            break

    core_text = "\n".join(lines[content_start:content_end])
    core_text = core_text.strip()
    return core_text


# ── Main logic ─────────────────────────────────────────────────────────────────

async def fetch_article_fulltext(article: dict) -> dict:
    """Fetch full text for a single CNKI article using journal-specific fetcher."""
    source = article.get("source", "")
    journal_name = source.replace("CNKI - ", "").strip()
    journal_info = JOURNAL_REGISTRY.get(journal_name)

    if not journal_info or not journal_info.get("oa"):
        return {"text": ""}

    func_name = journal_info["fetch_func"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="zh-CN",
        )
        page = await ctx.new_page()
        try:
            if func_name == "_fetch_hkxb":
                result = await _fetch_hkxb(page, article)
            elif func_name == "_fetch_prgjournal":
                result = await _fetch_prgjournal(page, article)
            else:
                return {"text": ""}
            return result
        except Exception as e:
            log.error(f"  {func_name} error: {e}")
            import traceback
            traceback.print_exc()
            return {"text": ""}
        finally:
            await browser.close()


def save_content_to_db(db_path: Path, article_id: str, text: str, doi: str = "", pdf_url: str = ""):
    """Update article content in database."""
    conn = sqlite3.connect(str(db_path))
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE articles SET content = ?, doi = ?, image_url = ?, fetched_at = ? WHERE id = ?",
            (text, doi, pdf_url, now, article_id),
        )
        conn.commit()
        log.info(f"  ✓ DB updated: {len(text)} chars")
    except Exception as e:
        log.error(f"  DB update error: {e}")
    finally:
        conn.close()


def process_database(db_path: Path, theme: str, limit: int = None) -> dict:
    """Process all CNKI articles in one database that need full text."""
    stats = {}

    conn = sqlite3.connect(str(db_path))
    try:
        for journal_name, journal_info in JOURNAL_REGISTRY.items():
            if not journal_info.get("oa"):
                continue

            articles = get_articles_without_content(conn, journal_name=journal_name, limit=limit)
            stats[journal_name] = {"found": len(articles), "fetched": 0, "failed": 0}

            log.info(f"[{theme}] {journal_name} articles: {len(articles)}")

            for i, article in enumerate(articles):
                log.info(
                    f"[{theme}] [{i + 1}/{len(articles)}] {article['title'][:50]}..."
                )

                # Rate limit
                delay = random.uniform(5, 12)
                log.info(f"  Delay {delay:.1f}s...")
                time.sleep(delay)

                try:
                    result = asyncio.run(fetch_article_fulltext(article))
                    if result.get("text") and len(result["text"]) > 500:
                        save_content_to_db(
                            db_path,
                            article["id"],
                            result["text"],
                            doi=result.get("doi", ""),
                            pdf_url=result.get("pdf_url", ""),
                        )
                        stats[journal_name]["fetched"] += 1
                    else:
                        log.warning(f"  No full text fetched")
                        stats[journal_name]["failed"] += 1
                except Exception as e:
                    log.error(f"  Fetch error: {e}")
                    stats[journal_name]["failed"] += 1

    finally:
        conn.close()

    return stats


def main():
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    limit = None
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    dbs = []
    if not aam_only:
        dbs.append((config.BASE_DIR / "data" / "news.db", "news"))
    if not news_only:
        dbs.append((config.BASE_DIR / "data" / "aam.db", "aam"))

    log.info("=" * 60)
    log.info("CNKI OA Full Text Fetcher")
    log.info(f"Supported journals: {list(JOURNAL_REGISTRY.keys())}")
    log.info(f"Databases: {[d[1] for d in dbs]}")
    if limit:
        log.info(f"Limit: {limit} articles per DB")
    log.info("=" * 60)

    all_stats = {}
    for db_path, theme in dbs:
        if not db_path.exists():
            log.warning(f"Database not found: {db_path}")
            continue

        log.info(f"\n{'='*60}")
        log.info(f"Processing {theme} ({db_path.name})")
        log.info(f"{'='*60}")

        stats = process_database(db_path, theme, limit=limit)
        all_stats[theme] = stats

        log.info(f"\n[{theme}] Results:")
        for jname, jstats in stats.items():
            log.info(f"  {jname}: found={jstats['found']} fetched={jstats['fetched']} failed={jstats['failed']}")

    log.info("\n" + "=" * 60)
    log.info("OA Full Text Fetch Complete")
    for theme, s in all_stats.items():
        total_fetched = sum(j["fetched"] for j in s.values())
        log.info(f"  {theme}: {total_fetched} full texts fetched")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
