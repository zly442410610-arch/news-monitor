#!/usr/bin/env python3
"""
Fetch CNKI article full text using Playwright + 书童 proxy (入口3).

Uses a headless Chromium browser to:
1. Go through 书童 api33.php → validated KNS8 proxy
2. Search for article by title
3. Open detail page and extract full text

Usage:
    python3 fetch_cnki_playwright.py                        # batch process all
    python3 fetch_cnki_playwright.py --news-only            # news.db only
    python3 fetch_cnki_playwright.py --aam-only             # aam.db only
    python3 fetch_cnki_playwright.py --limit 5              # max 5 articles
    python3 fetch_cnki_playwright.py --test-title "标题"     # single article test
"""
import json
import logging
import re
import sqlite3
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pw_cnki")

sys.path.insert(0, str(BASE))
import config
from monitor import update_article_content

# ── Constants ──────────────────────────────────────────────────────────────

SHUTONG_COOKIE_JAR = BASE / ".shutong_cookies.json"
SHUTONG_MAIN = "http://3.shutong2.com/"
SHUTONG_ZHONGWENKU = "http://3.shutong2.com/zhongwenku/"
SHUTONG_ENTRY3 = "http://3.shutong2.com/api33.php"
KNS8_BASE = "https://kns-cnki-net-443.wvpn.sjlib.cn"

# Minimum content length to consider successful
MIN_CONTENT_LEN = 500

# Delay range between articles (seconds)
DELAY_MIN = 5
DELAY_MAX = 15

# Login/vip expiry indicators (Chinese)
EXPIRY_INDICATORS = ["登录", "过期", "剩余天数", "请重新登录", "会员已过期"]


# ── Cookie Loader ──────────────────────────────────────────────────────────

def load_shutong_cookies() -> dict[str, str]:
    """Load 书童 cookies from persistent file."""
    if not SHUTONG_COOKIE_JAR.exists():
        log.error(f"书童 cookie file not found: {SHUTONG_COOKIE_JAR}")
        return {}
    try:
        data = json.loads(SHUTONG_COOKIE_JAR.read_text())
        cookies = data.get("cookies", {})
        log.info(f"Loaded {len(cookies)} 书童 cookies")
        return cookies
    except Exception as e:
        log.error(f"Failed to load 书童 cookies: {e}")
        return {}


def set_cookies_in_context(ctx: BrowserContext, cookies_dict: dict[str, str],
                           domain: str = "3.shutong2.com"):
    """Set cookies in a Playwright browser context."""
    for name, value in cookies_dict.items():
        ctx.add_cookies([{
            "name": name,
            "value": value,
            "domain": domain,
            "path": "/",
        }])

    # Also add for sjlib.cn if they exist
    for name, value in cookies_dict.items():
        ctx.add_cookies([{
            "name": name,
            "value": value,
            "domain": "kns-cnki-net-443.wvpn.sjlib.cn",
            "path": "/",
        }])


# ── Content Extraction ─────────────────────────────────────────────────────

def extract_article_text(page: Page) -> str:
    """Extract article text from a CNKI detail page using multiple strategies."""
    page.wait_for_load_state("networkidle", timeout=30000)

    # Allow extra time for JS rendering
    time.sleep(3)

    text = ""

    # Strategy 1: CNKI read area
    for selector in [
        ".readtext",
        ".detail-body",
        ".journal-content",
        ".article-content",
        ".content-area",
        "#article-content",
        ".main-content",
        ".article-detail",
        ".fulltext-content",
        ".text-content",
    ]:
        try:
            el = page.query_selector(selector)
            if el:
                t = el.inner_text()
                if len(t) > MIN_CONTENT_LEN:
                    log.info(f"  Strategy 1 ({selector}): {len(t)} chars")
                    return t
        except Exception:
            continue

    # Strategy 2: Try evaluation-based extraction for SPA pages
    try:
        t = page.evaluate("""() => {
            // Common CNKI detail page content containers
            const selectors = [
                '.article-main', '.articleContent', '.cnki-content',
                '[class*="content"]', '[class*="detail"]', '[class*="fulltext"]',
                '.mainContent', '#mainContent', '.article-body',
                '.wrapper', '.main', 'article', 'main'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const text = el.innerText.trim();
                    if (text.length > 500) return text;
                }
            }
            // Fallback: body text minus scripts/styles
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, nav, footer, header, iframe, .nav, .header, .footer, .sidebar').forEach(el => el.remove());
            return clone.innerText.trim();
        }""")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  Strategy 2 (evaluate): {len(t)} chars")
            return t
        if t:
            text = t
    except Exception:
        pass

    # Strategy 3: Plain body text
    try:
        t = page.inner_text("body")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  Strategy 3 (body text): {len(t)} chars")
            return t
        if t and len(t) > len(text):
            text = t
    except Exception:
        pass

    # Strategy 4: Readability-like via JS
    try:
        t = page.evaluate("""() => {
            const article = document.querySelector('article') || document.querySelector('[role="main"]');
            if (article) return article.innerText.trim();
            // Get all paragraphs
            const ps = document.querySelectorAll('p');
            let text = '';
            for (const p of ps) {
                const t = p.innerText.trim();
                if (t.length > 30) text += t + '\\n';
            }
            if (text.length > 500) return text;
            return '';
        }""")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  Strategy 4 (paragraphs): {len(t)} chars")
            return t
        if t and len(t) > len(text):
            text = t
    except Exception:
        pass

    return text


def extract_doi_from_page(page: Page) -> str:
    """Try to extract DOI from the detail page."""
    try:
        doi = page.evaluate("""() => {
            const meta = document.querySelector('meta[name="citation_doi"]');
            if (meta) return meta.getAttribute('content') || '';
            // Also check for DOI in text
            const body = document.body.innerText;
            const m = body.match(/10\\.\\d{4,}[\\/][\\w\\.\\-]+/);
            return m ? m[0] : '';
        }""")
        return doi or ""
    except Exception:
        return ""


def extract_image_from_page(page: Page) -> str:
    """Try to extract a representative image from the detail page."""
    try:
        img = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            for (const img of imgs) {
                const src = img.src || '';
                const alt = (img.alt || '').toLowerCase();
                if (src && !src.includes('logo') && !src.includes('icon')
                    && !src.includes('banner') && !src.includes('avatar')
                    && (alt.includes('article') || alt.includes('figure')
                        || alt.includes('图') || alt.includes('figure'))) {
                    return src;
                }
            }
            // Fallback: first content image
            for (const img of imgs) {
                const src = img.src || '';
                const w = img.naturalWidth || 0;
                if (src && !src.includes('logo') && !src.includes('icon') && w > 100) {
                    return src;
                }
            }
            return '';
        }""")
        return img or ""
    except Exception:
        return ""


def extract_content_images(page: Page) -> list[str]:
    """Extract all content images from the page."""
    try:
        imgs = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            const results = [];
            for (const img of imgs) {
                const src = img.src || '';
                if (src && !src.includes('logo') && !src.includes('icon')
                    && !src.includes('banner') && !src.includes('avatar')) {
                    results.push(src);
                }
            }
            return results.slice(0, 20);
        }""")
        return imgs or []
    except Exception:
        return []


# ── Login/Expiry Check ─────────────────────────────────────────────────────

def is_login_page(page: Page) -> bool:
    """Check if the current page indicates login/expiry."""
    try:
        html = page.content()
        # Check expiry indicators
        for ind in EXPIRY_INDICATORS:
            if ind in html[:5000]:
                # Check more carefully - are we really on a login page?
                text = page.inner_text("body")[:2000].lower()
                login_words = ["登录", "密码", "验证码", "会员"]
                count = sum(1 for w in login_words if w in text)
                if count >= 2:
                    return True
        return False
    except Exception:
        return False


def is_captcha_page(page: Page) -> bool:
    """Check if the page shows a CAPTCHA challenge."""
    try:
        html = page.content()
        captcha_indicators = ["captcha", "验证码", "滑块", "slide", "verify",
                              "security", "安全验证"]
        for ind in captcha_indicators:
            if ind in html[:10000]:
                return True
        return False
    except Exception:
        return False


# ── Main Fetch Function ────────────────────────────────────────────────────

def fetch_article_by_playwright(url: str, title: str,
                                 shutong_cookies: dict[str, str],
                                 playwright_context) -> Optional[dict]:
    """
    Try to fetch CNKI article content using Playwright.

    Strategy 1: Direct proxied URL access
    Strategy 2: KNS8 search by title

    Returns dict with keys: text, doi, image_url, images
    or None if failed.
    """
    browser, ctx = playwright_context

    # ── Strategy 1: Direct URL access ──
    # Rewrite URL through shutong proxy
    from monitor import _proxy_cnki_via_shutong
    proxied_url, extra_cookies = _proxy_cnki_via_shutong(url)

    log.info(f"  Strategy 1: Direct proxied URL")
    log.info(f"    Proxied: {proxied_url[:100]}")

    page = ctx.new_page()

    # Set extra cookies from proxy
    if extra_cookies:
        for name, value in extra_cookies.items():
            try:
                # Determine domain from proxied URL
                import urllib.parse
                domain = urllib.parse.urlparse(proxied_url).hostname
                page.context.add_cookies([{
                    "name": name, "value": value,
                    "domain": domain, "path": "/",
                }])
            except Exception:
                pass

    try:
        # Navigate with timeout - allow redirects
        resp = page.goto(proxied_url, wait_until="domcontentloaded",
                         timeout=45000, referer=SHUTONG_ZHONGWENKU)
        if resp:
            log.info(f"    Status: {resp.status}, URL: {page.url[:80]}")

        # Wait for JS rendering
        time.sleep(5)

        # Check for login/captcha
        if is_login_page(page):
            log.warning("    Login page detected - session expired")
            page.close()
            return None

        if is_captcha_page(page):
            log.warning("    CAPTCHA detected, skipping")
            page.close()
            return None

        # Extract text
        text = extract_article_text(page)
        if len(text) >= MIN_CONTENT_LEN:
            log.info(f"  ✓ Strategy 1 OK: {len(text)} chars")
            doi = extract_doi_from_page(page)
            image_url = extract_image_from_page(page)
            images = extract_content_images(page)
            page.close()
            return {"text": text, "doi": doi,
                    "image_url": image_url, "images": images}

        log.info(f"    Strategy 1: only {len(text)} chars, trying search...")
    except Exception as e:
        log.warning(f"    Strategy 1 error: {e}")
    finally:
        page.close()

    # ── Strategy 2: KNS8 Search by Title ──
    log.info(f"  Strategy 2: KNS8 search by title")
    page = ctx.new_page()

    try:
        # Step 1: Go through shutong entry3 to establish validated session
        log.info(f"    Step 1: api33.php entry...")
        resp = page.goto(SHUTONG_ENTRY3, wait_until="domcontentloaded",
                         timeout=45000, referer=SHUTONG_ZHONGWENKU)

        # Wait for redirect chain to complete and JS to render
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)
        log.info(f"    Final URL: {page.url[:100]}")
        log.info(f"    Page title: {page.title()}")

        # Step 2: Check we're on KNS8 search page
        current_url = page.url
        if "wvpn.sjlib.cn" not in current_url or "kns8" not in current_url.lower():
            # The validate-token page might redirect further - wait more
            log.info(f"    Waiting for KNS8 redirect...")
            try:
                page.wait_for_url("**kns8**", timeout=15000)
                log.info(f"    Now at: {page.url[:100]}")
            except Exception:
                log.warning(f"    Not on KNS8 page, trying to navigate directly")
                try:
                    page.goto(f"{KNS8_BASE}/kns8s/DefaultResult/Index",
                              wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                except Exception:
                    pass

        # Check for expired session
        if is_login_page(page):
            log.warning("    Session expired on KNS8")
            page.close()
            return None

        # Step 3: Search by title
        log.info(f"    Step 3: Searching for '{title[:60]}'...")

        # Try multiple approaches to fill and submit the search
        search_success = False

        # Approach A: Fill #txt_search and press Enter
        try:
            search_input = page.wait_for_selector("#txt_search", timeout=10000)
            if search_input:
                search_input.fill("")
                search_input.type(title, delay=50)
                time.sleep(1)
                page.keyboard.press("Enter")
                log.info(f"    Submitted search via Enter")
                search_success = True
        except Exception as e:
            log.warning(f"    Search approach A failed: {e}")

        # Approach B: Try clicking a search button
        if not search_success:
            try:
                search_input = page.query_selector("#txt_search")
                if search_input:
                    search_input.fill(title)
                    time.sleep(0.5)
                    # Look for search button
                    btn = page.query_selector("button[type='submit'], .search-btn, #search-btn, [class*='search'] button")
                    if btn:
                        btn.click()
                        log.info(f"    Submitted search via button click")
                        search_success = True
            except Exception:
                pass

        # Approach C: Navigate to search URL directly
        if not search_success:
            log.warning(f"    Search input not found, trying URL-based search")
            # KNS8 might support GET search parameters
            from urllib.parse import quote
            search_url = f"{KNS8_BASE}/kns8s/DefaultResult/Index?kwd={quote(title)}&dbcode=CJFD"
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                search_success = True
            except Exception:
                pass

        # Step 4: Wait for results and click the first link
        if search_success:
            log.info(f"    Waiting for search results...")
            time.sleep(5)

            # Wait for network to settle
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass

            # Check for captcha
            if is_captcha_page(page):
                log.warning("    CAPTCHA on search results, skipping")
                page.close()
                return None

            # Try to find and click the first result link
            result_clicked = False

            # Look for result links in various formats
            result_selectors = [
                "a[href*='Detail']",
                "a[href*='detail']",
                "a[href*='FileName']",
                ".result-title a",
                ".title a",
                "table a",
                "[class*='result'] a",
                "[class*='title'] a",
                "a[target='_blank']",
            ]

            for selector in result_selectors:
                try:
                    links = page.query_selector_all(selector)
                    # Filter to likely article links (not "下一页" etc.)
                    for link in links[:10]:
                        href = link.get_attribute("href") or ""
                        link_text = link.inner_text().strip()
                        if (link_text and len(link_text) > 5
                                and "上一页" not in link_text
                                and "next" not in link_text.lower()
                                and "page" not in link_text.lower()):
                            log.info(f"    Clicking result: {link_text[:50]}...")
                            try:
                                link.click(timeout=10000)
                                result_clicked = True
                                break
                            except Exception:
                                continue
                except Exception:
                    continue
                if result_clicked:
                    break

            if result_clicked:
                # Wait for detail page to load
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                time.sleep(4)
                log.info(f"    Detail page URL: {page.url[:100]}")

                # Extract text from detail page
                text = extract_article_text(page)
                if len(text) >= MIN_CONTENT_LEN:
                    log.info(f"  ✓ Strategy 2 OK: {len(text)} chars")
                    doi = extract_doi_from_page(page)
                    image_url = extract_image_from_page(page)
                    images = extract_content_images(page)
                    page.close()
                    return {"text": text, "doi": doi,
                            "image_url": image_url, "images": images}
                else:
                    log.info(f"    Detail page: only {len(text)} chars")
            else:
                log.warning(f"    No search result links found")
        else:
            log.warning(f"    Search submission failed")

    except Exception as e:
        log.warning(f"    Strategy 2 error: {e}")
    finally:
        page.close()

    return None


def init_playwright(shutong_cookies: dict[str, str]):
    """Initialize Playwright with shutong cookies."""
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox",
              "--disable-dev-shm-usage"],
    )
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
    )

    # Set shutong cookies
    set_cookies_in_context(ctx, shutong_cookies)

    # First verify: go to shutong main page to establish session
    log.info("Verifying 书童 session...")
    page = ctx.new_page()

    try:
        page.goto(SHUTONG_MAIN, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Check for VIP info (confirms login)
        body_text = page.inner_text("body")[:1000]
        if "VIP" in body_text or "书童" in body_text:
            log.info("  ✓ 书童 session validated")
        else:
            log.warning("  书童 session may be expired")

        # Check expiry indicators
        if is_login_page(page):
            log.error("✗ 书童 session has expired! Please re-import cookies.")
            page.close()
            ctx.close()
            browser.close()
            p.stop()
            return None, None, None

    except Exception as e:
        log.error(f"书童 session verification failed: {e}")
        try:
            page.close()
            ctx.close()
            browser.close()
            p.stop()
        except Exception:
            pass
        return None, None, None
    finally:
        page.close()

    return p, browser, ctx


# ── Database Operations ────────────────────────────────────────────────────

def get_articles_without_content(conn: sqlite3.Connection, limit: int = 0) -> list[dict]:
    """Get CNKI articles that need content fetched."""
    rows = conn.execute(
        "SELECT id, title, url, length(coalesce(content,'')) as content_len "
        "FROM articles "
        "WHERE url LIKE '%cnki.net%' "
        "AND (content IS NULL OR length(content) < ?) "
        "ORDER BY published DESC",
        (MIN_CONTENT_LEN,)
    ).fetchall()

    articles = [dict(r) for r in rows]
    if limit > 0:
        articles = articles[:limit]
    return articles


def save_content_to_db(conn: sqlite3.Connection, article_id: str,
                       title: str, result: dict):
    """Save fetched content to database."""
    text = result.get("text", "")
    doi = result.get("doi", "")
    images = result.get("images", [])
    image_url = result.get("image_url", "")

    if not text or len(text) < MIN_CONTENT_LEN:
        log.warning(f"    Content too short ({len(text)} chars), not saving")
        return False

    # Trim to reasonable length
    if len(text) > config.MAX_CONTENT_LENGTH:
        text = text[:config.MAX_CONTENT_LENGTH]

    # Update via monitor function (handles translation + commit)
    try:
        update_article_content(conn, article_id, text,
                               title=title,
                               images=images,
                               doi=doi)
        log.info(f"    ✓ DB updated: {len(text)} chars" +
                 (f", doi={doi}" if doi else ""))

        # Update image_url separately
        if image_url:
            conn.execute(
                "UPDATE articles SET image_url = ? WHERE id = ?",
                (image_url, article_id)
            )
            conn.commit()

        return True
    except Exception as e:
        log.error(f"    DB update error: {e}")
        return False


# ── Single Article Test ────────────────────────────────────────────────────

def test_single_article(title: str):
    """Test fetching a single article by title."""
    shutong_cookies = load_shutong_cookies()
    if not shutong_cookies:
        log.error("No shutong cookies")
        return

    p_obj, browser, ctx = init_playwright(shutong_cookies)
    if not browser:
        return

    try:
        # Create a dummy KCMS2 URL
        dummy_url = "https://kns.cnki.net/kcms2/article/abstract?v=test"
        pw_ctx = (browser, ctx)
        result = fetch_article_by_playwright(dummy_url, title, shutong_cookies,
                                              pw_ctx)
        if result:
            log.info(f"\n✓ SUCCESS: {len(result['text'])} chars")
            log.info(f"  First 300 chars: {result['text'][:300]}")
            if result.get("doi"):
                log.info(f"  DOI: {result['doi']}")
            if result.get("image_url"):
                log.info(f"  Image: {result['image_url'][:60]}")
            if result.get("images"):
                log.info(f"  Images: {len(result['images'])}")
        else:
            log.error(f"\n✗ FAILED: Could not fetch content for '{title}'")
    finally:
        browser.close()
        p_obj.stop()


# ── Batch Processing ───────────────────────────────────────────────────────

def process_database(db_path: Path, theme: str, shutong_cookies: dict[str, str],
                     limit: int = 0) -> dict:
    """Process all CNKI articles in one database."""
    stats = {"total": 0, "fetched": 0, "failed": 0, "skipped": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")

    articles = get_articles_without_content(conn, limit)
    stats["total"] = len(articles)
    log.info(f"[{theme}] {len(articles)} CNKI articles need content")

    if not articles:
        conn.close()
        return stats

    # Initialize Playwright
    p_obj, browser, ctx = init_playwright(shutong_cookies)
    if not browser:
        conn.close()
        return stats

    pw_ctx = (browser, ctx)

    try:
        for i, article in enumerate(articles):
            aid = article["id"]
            title = article["title"]
            url = article["url"]
            content_len = article["content_len"]

            log.info(f"\n[{theme}] [{i + 1}/{len(articles)}] {title[:55]}... "
                     f"(content={content_len}b)")

            # Rate limit
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            log.info(f"  Delay {delay:.1f}s...")
            time.sleep(delay)

            # Fetch content
            result = fetch_article_by_playwright(
                url, title, shutong_cookies, pw_ctx
            )

            if result and result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
                if save_content_to_db(conn, aid, title, result):
                    stats["fetched"] += 1
                    log.info(f"  ✓ [{theme}] Content saved")
                else:
                    stats["failed"] += 1
            else:
                stats["failed"] += 1
                log.warning(f"  ✗ [{theme}] No content retrieved")

    finally:
        browser.close()
        p_obj.stop()
        conn.close()

    return stats


def main():
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    test_title = None

    # Parse --test-title
    if "--test-title" in sys.argv:
        idx = sys.argv.index("--test-title")
        if idx + 1 < len(sys.argv):
            test_title = sys.argv[idx + 1]

    # Parse --limit
    limit = 0
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[idx + 1])
            except ValueError:
                pass

    # ── Test Mode ──
    if test_title:
        log.info("=" * 60)
        log.info(f"Testing single article: {test_title}")
        log.info("=" * 60)
        test_single_article(test_title)
        return

    # ── Batch Mode ──
    shutong_cookies = load_shutong_cookies()
    if not shutong_cookies:
        log.error("书童 cookies not available. Run import_shutong_cookies.py first.")
        sys.exit(1)

    dbs = []
    if not aam_only:
        dbs.append((config.BASE_DIR / "data" / "news.db", "news"))
    if not news_only:
        dbs.append((config.BASE_DIR / "data" / "aam.db", "aam"))

    log.info("=" * 60)
    log.info("CNKI Playwright Full Text Fetcher")
    log.info(f"Databases: {[d[1] for d in dbs]}")
    if limit:
        log.info(f"Limit: {limit} articles per DB")
    log.info("=" * 60)

    all_stats = {}
    for db_path, theme in dbs:
        if not db_path.exists():
            log.warning(f"Database not found: {db_path}")
            continue

        log.info(f"\n{'=' * 60}")
        log.info(f"Processing {theme} ({db_path.name})")
        log.info(f"{'=' * 60}")

        stats = process_database(db_path, theme, shutong_cookies, limit)
        all_stats[theme] = stats

        log.info(f"\n[{theme}] Results:")
        log.info(f"  Total:      {stats['total']}")
        log.info(f"  Fetched:    {stats['fetched']}")
        log.info(f"  Failed:     {stats['failed']}")
        log.info(f"  Skipped:    {stats['skipped']}")

    log.info("\n" + "=" * 60)
    log.info("Done!")
    for theme, s in all_stats.items():
        log.info(f"  {theme}: {s['fetched']}/{s['total']} OK")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
