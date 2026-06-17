#!/usr/bin/env python3
"""
书童全文获取 — 通过书童图书馆代理访问 CNKI/万方/维普获取全文。

策略（按序尝试）:
  1. CNKI KNS8  — 精确匹配，但易触发反爬
  2. 万方数据    — 反爬较轻，全文 HTML 嵌入
  3. 维普资讯    — PDF 后备

用法:
  python3 fetch_shutong_fulltext.py                         # 批量
  python3 fetch_shutong_fulltext.py --news-only             # news.db 只
  python3 fetch_shutong_fulltext.py --aam-only              # aam.db 只
  python3 fetch_shutong_fulltext.py --limit 3               # 限 N 篇
  python3 fetch_shutong_fulltext.py --test-title "标题"     # 单篇测试
  python3 fetch_shutong_fulltext.py --debug-entry wanfang   # 探测入口
"""
import asyncio
import json
import logging
import re
import random
import sqlite3
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("shutong")

sys.path.insert(0, str(BASE))
import config
from monitor import update_article_content

# ── Constants ────────────────────────────────────────────────────────────────

SHUTONG_MAIN = "http://3.shutong2.com/"
SHUTONG_ZHONGWENKU = "http://3.shutong2.com/zhongwenku/"
SHUTONG_ENTRY3 = "http://3.shutong2.com/api33.php"         # CNKI 入口3
SHUTONG_CQVIP = "http://3.shutong2.com/cqvip.php"          # 维普入口1
WANFANG_ENTRY2 = "https://yiigle.wenxian.shop/wf_auth"     # 万方入口2
KNS8_BASE = "https://kns-cnki-net-443.wvpn.sjlib.cn"

MIN_CONTENT_LEN = 500
DELAY_MIN = getattr(config, "CNKI_FETCH_DELAY_MIN", 3)
DELAY_MAX = getattr(config, "CNKI_FETCH_DELAY_MAX", 10)

# ── Cookie / Session ─────────────────────────────────────────────────────────

def load_shutong_cookies() -> dict[str, str]:
    """从 .shutong_cookies.json 加载书童会话 cookies."""
    jar = config.SHUTONG_COOKIE_JAR
    if not jar.exists():
        log.error(f"Cookie file not found: {jar}")
        return {}
    try:
        data = json.loads(jar.read_text())
        cookies = data.get("cookies", {})
        log.info(f"Loaded {len(cookies)} 书童 cookies")
        return cookies
    except Exception as e:
        log.error(f"Failed to load shutong cookies: {e}")
        return {}


async def set_cookies_in_context(ctx: BrowserContext, cookie_dict: dict[str, str]):
    """Set cookies in a Playwright context for all relevant shutong domains."""
    domains = [
        "3.shutong2.com",
        ".shutong2.com",
        "kns-cnki-net-443.wvpn.sjlib.cn",
        "yiigle.wenxian.shop",
        "wf.xue66.net",
    ]
    for name, value in cookie_dict.items():
        for domain in domains:
            try:
                await ctx.add_cookies([{
                    "name": name, "value": value,
                    "domain": domain, "path": "/",
                }])
            except Exception:
                pass


async def verify_shutong_session(page: Page) -> bool:
    """Verify 书童 VIP session is still valid."""
    try:
        await page.goto(SHUTONG_MAIN, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        body = await page.inner_text("body")
        if "VIP" in body or "书童" in body:
            log.info("  ✓ 书童 session valid")
            return True
        if "登录" in body[:2000] or "过期" in body[:2000]:
            log.error("✗ 书童 session expired! Re-import cookies.")
            return False
        log.warning("  书童 session state ambiguous, continuing anyway")
        return True
    except Exception as e:
        log.error(f"Session verification error: {e}")
        return False


# ── Content Extraction ───────────────────────────────────────────────────────

async def extract_article_text(page: Page) -> str:
    """Extract article text using multiple strategies, returns empty str on failure."""
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(3)

    text = ""

    # Strategy 1: Common content selectors
    for selector in [
        ".readtext", ".detail-body", ".journal-content", ".article-content",
        ".content-area", "#article-content", ".main-content", ".article-detail",
        ".fulltext-content", ".text-content", ".full-text", "#fulltext",
        "[class*='fulltext']", "[class*='FullText']",
    ]:
        try:
            el = await page.query_selector(selector)
            if el:
                t = await el.inner_text()
                if len(t) > MIN_CONTENT_LEN:
                    log.info(f"  Strategy1 ({selector}): {len(t)} chars")
                    return t
        except Exception:
            continue

    # Strategy 2: JS evaluation — strip nav/footer/script
    try:
        t = await page.evaluate("""() => {
            const selectors = [
                '.article-main', '.articleContent', '.cnki-content',
                '[class*="content"]', '[class*="detail"]', '[class*="fulltext"]',
                '.mainContent', '#mainContent', '.article-body',
                '.wrapper', '.main', 'article', 'main'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) { const t = el.innerText.trim(); if (t.length > 500) return t; }
            }
            const body = document.body.cloneNode(true);
            body.querySelectorAll('script,style,nav,footer,header,iframe,.nav,.header,.footer,.sidebar,.ad').forEach(e=>e.remove());
            return body.innerText.trim();
        }""")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  Strategy2 (evaluate): {len(t)} chars")
            return t
        if t:
            text = t
    except Exception:
        pass

    # Strategy 3: body.inner_text
    try:
        t = await page.inner_text("body")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  Strategy3 (body): {len(t)} chars")
            return t
        if t and len(t) > len(text):
            text = t
    except Exception:
        pass

    # Strategy 4: Paragraph aggregation
    try:
        t = await page.evaluate("""() => {
            const ps = document.querySelectorAll('p');
            let r = '';
            for (const p of ps) {
                const t = p.innerText.trim();
                if (t.length > 30) r += t + '\\n';
            }
            return r.length > 500 ? r : '';
        }""")
        if t:
            log.info(f"  Strategy4 (paragraphs): {len(t)} chars")
            return t
    except Exception:
        pass

    return text


async def extract_doi(page: Page) -> str:
    """Extract DOI from page meta or body text."""
    try:
        doi = await page.evaluate("""() => {
            const m = document.querySelector('meta[name="citation_doi"]');
            if (m) return m.getAttribute('content')||'';
            const body = document.body.innerText;
            const r = body.match(/10\\.\\d{4,}[\\/][\\w\\.\\-]+/);
            return r ? r[0] : '';
        }""")
        return doi or ""
    except Exception:
        return ""


async def extract_images(page: Page) -> tuple[str, list[str]]:
    """Extract representative image + content images."""
    try:
        img = await page.evaluate("""() => {
            for (const img of document.querySelectorAll('img')) {
                const s = img.src||'';
                const a = (img.alt||'').toLowerCase();
                if (s && !s.includes('logo')&&!s.includes('icon')&&!s.includes('banner')
                    && !s.includes('avatar')&&!s.includes('btn'))
                    return s;
            }
            return '';
        }""")
        imgs = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('img')).map(i=>i.src)
                .filter(s => s && !s.includes('logo')&&!s.includes('icon')
                    &&!s.includes('banner')&&!s.includes('avatar'))
                .slice(0,20)
        """)
        return (img or "", imgs or [])
    except Exception:
        return ("", [])


# ── Database ─────────────────────────────────────────────────────────────────

def get_cnki_articles_without_content(conn: sqlite3.Connection,
                                       limit: int = 0) -> list[dict]:
    """Get CNKI articles missing content from DB."""
    rows = conn.execute(
        "SELECT id, title, url, source, author, published, doi "
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


def update_article_db(conn: sqlite3.Connection, article_id: str,
                      text: str, doi: str = "",
                      image_url: str = "", images: list[str] = None):
    """Save article content to DB using monitor's update_article_content."""
    if not text or len(text) < MIN_CONTENT_LEN:
        return False
    if len(text) > config.MAX_CONTENT_LENGTH:
        text = text[:config.MAX_CONTENT_LENGTH]
    try:
        update_article_content(conn, article_id, text,
                               title="", images=images or [], doi=doi)
        if image_url:
            conn.execute("UPDATE articles SET image_url=? WHERE id=?",
                         (image_url, article_id))
            conn.commit()
        log.info(f"  ✓ DB updated: {len(text)} chars" +
                 (f", doi={doi}" if doi else ""))
        return True
    except Exception as e:
        log.error(f"  DB update error: {e}")
        return False


# ── Rate Limiting ────────────────────────────────────────────────────────────

async def rate_delay():
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    log.info(f"  Delay {delay:.1f}s...")
    await asyncio.sleep(delay)


# ── Strategy Pattern ─────────────────────────────────────────────────────────

class ShutongStrategy(ABC):
    """Base class for shutong-proxied database strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def navigate_to_source(self, page: Page) -> bool:
        """Navigate to the database through shutong portal. Returns False if session dead."""
        ...

    @abstractmethod
    async def search_by_title(self, page: Page, title: str) -> Optional[str]:
        """Search for article, return detail page URL or None."""
        ...

    @abstractmethod
    async def extract_fulltext(self, page: Page) -> dict:
        """Extract full text from current detail page.
        Returns {text: str, doi: str, image_url: str, images: list[str]}.
        """
        ...


class CnkiStrategy(ShutongStrategy):
    """CNKI KNS8 — via shutong api33.php → wvpn.sjlib.cn."""

    @property
    def name(self) -> str:
        return "cnki"

    async def navigate_to_source(self, page: Page) -> bool:
        log.info("    CNKI: api33.php with referer...")
        try:
            # First visit zhongwenku to establish session context
            await page.goto(SHUTONG_ZHONGWENKU, wait_until="domcontentloaded",
                            timeout=30000, referer=SHUTONG_MAIN)
            await asyncio.sleep(2)

            # Navigate to api33.php WITH Referer header (required for redirect)
            resp = await page.goto(SHUTONG_ENTRY3, wait_until="domcontentloaded",
                                   timeout=45000, referer=SHUTONG_ZHONGWENKU)
            if resp:
                log.info(f"    api33.php status: {resp.status}")

            # Wait for redirect chain to complete
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(5)
            log.info(f"    URL: {page.url[:120]}")
            log.info(f"    Title: {await page.title()}")

            # If not on KNS8 yet, wait for redirect
            if "wvpn" not in page.url and "kns8" not in page.url.lower():
                log.info("    Waiting for KNS8 redirect...")
                try:
                    await page.wait_for_url("**kns8**", timeout=20000)
                    await asyncio.sleep(3)
                except Exception:
                    pass

            log.info(f"    Final URL: {page.url[:120]}")
            return "wvpn" in page.url or "kns8" in page.url.lower()
        except Exception as e:
            log.warning(f"    CNKI nav failed: {e}")
            return False

    async def search_by_title(self, page: Page, title: str) -> Optional[str]:
        log.info(f"    Searching CNKI for '{title[:60]}'...")
        search_success = False

        # Approach A: Fill #txt_search and press Enter
        try:
            inp = await page.wait_for_selector("#txt_search", timeout=10000)
            if inp:
                await inp.fill("")
                await inp.type(title, delay=50)
                await asyncio.sleep(1)
                await page.keyboard.press("Enter")
                search_success = True
                log.info("    Search submitted via Enter")
        except Exception as e:
            log.warning(f"    Search fill failed: {e}")

        # Approach B: URL-based search
        if not search_success:
            try:
                from urllib.parse import quote
                search_url = (f"{KNS8_BASE}/kns8s/DefaultResult/Index"
                              f"?kwd={quote(title)}&dbcode=CJFD")
                await page.goto(search_url, wait_until="domcontentloaded",
                                timeout=30000, referer=page.url)
                await asyncio.sleep(3)
                search_success = True
                log.info("    Search via URL")
            except Exception as e:
                log.warning(f"    URL search failed: {e}")

        if not search_success:
            return None

        # Wait for search results
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass

        # Try to CLICK the first matching result (click handler may trigger
        # proxy URL rewriting, which doesn't happen with href extraction)
        for selector in [
            "a[href*='Detail']", "a[href*='detail']",
            "a[href*='FileName']", ".result-title a",
            ".title a", "table a", "[class*='result'] a",
            "[class*='title'] a", "a[target='_blank']",
        ]:
            try:
                links = await page.query_selector_all(selector)
                for link in links[:10]:
                    href = await link.get_attribute("href") or ""
                    lt = (await link.inner_text()).strip()
                    if lt and len(lt) > 5 and "上一页" not in lt and "next" not in lt.lower():
                        try:
                            # Click the link to trigger proxy URL rewriting
                            await link.click(timeout=10000)
                            await page.wait_for_load_state("networkidle", timeout=20000)
                            await asyncio.sleep(3)
                            log.info(f"    Clicked result, URL: {page.url[:120]}")
                            # Check if we got to a detail page (not login)
                            body_text = await page.inner_text("body")
                            if "会员" not in body_text[:500] or len(body_text) > 1000:
                                return page.url
                            log.info("    Result went to login page, trying next...")
                        except Exception:
                            continue
            except Exception:
                continue

        # Fallback: try navigating with rewritten URL through proxy
        log.info("    Click approach failed, trying proxy-rewritten URL...")
        try:
            from monitor import _proxy_cnki_via_shutong
            detail_url = await page.evaluate(f"""() => {{
                let links = Array.from(document.querySelectorAll('a[href*="Detail"], a[href*="FileName"]'));
                for (let a of links) {{
                    let href = a.href;
                    if (href && href.includes('cnki.net')) return href;
                }}
                return null;
            }}""")
            if detail_url:
                proxied_url, _ = _proxy_cnki_via_shutong(detail_url)
                log.info(f"    Proxy-rewritten URL: {proxied_url[:100]}")
                await page.goto(proxied_url, wait_until="domcontentloaded",
                                timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                await asyncio.sleep(3)
                return page.url
        except Exception as e:
            log.warning(f"    Proxy rewrite failed: {e}")

        return None

    async def extract_fulltext(self, page: Page) -> dict:
        text = await extract_article_text(page)
        doi = await extract_doi(page)
        img_url, imgs = await extract_images(page)
        return {"text": text, "doi": doi, "image_url": img_url, "images": imgs}


class WanfangStrategy(ShutongStrategy):
    """万方数据 — 暂不可用。探测结果：
    书童上万方入口均已失效（401/404/仅手工操作信息页）。
    万方直连可搜索但全文需订阅。
    预留此策略以备未来恢复。
    """

    @property
    def name(self) -> str:
        return "wanfang"

    async def navigate_to_source(self, page: Page) -> bool:
        log.warning("    Wanfang: 书童入口不可用，跳过")
        return False

    async def search_by_title(self, page: Page, title: str) -> Optional[str]:
        return None

    async def extract_fulltext(self, page: Page) -> dict:
        return {"text": ""}


class WeipuStrategy(ShutongStrategy):
    """维普资讯 — 暂不可用。探测结果：
    书童上维普入口已失效（空页面/仅手工操作信息页）。
    维普直连返回 412 被拦截。
    预留此策略以备未来恢复。
    """

    @property
    def name(self) -> str:
        return "weipu"

    async def navigate_to_source(self, page: Page) -> bool:
        log.warning("    Weipu: 书童入口不可用，跳过")
        return False

    async def search_by_title(self, page: Page, title: str) -> Optional[str]:
        return None

    async def extract_fulltext(self, page: Page) -> dict:
        return {"text": ""}


# ── Debug / Probe Mode ───────────────────────────────────────────────────────

async def debug_entry(entry_name: str):
    """Probe a shutong entry to understand its access flow."""
    shutong_cookies = load_shutong_cookies()
    if not shutong_cookies:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True,
                                          args=["--no-sandbox", "--disable-setuid-sandbox"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        await set_cookies_in_context(ctx, shutong_cookies)
        page = await ctx.new_page()

        requests_log = []
        async def log_req(req):
            requests_log.append({"phase": "request", "url": req.url[:150],
                                 "method": req.method})
        async def log_resp(resp):
            requests_log.append({"phase": "response", "url": resp.url[:150],
                                 "status": resp.status})
        page.on("request", log_req)
        page.on("response", log_resp)

        # Step 1: Verify session on shutong main
        if not await verify_shutong_session(page):
            log.error("Session invalid, cannot probe")
            await browser.close()
            return

        # Step 2: Go to zhongwenku
        log.info(f"\n=== Probing entry: {entry_name} ===")
        await page.goto(SHUTONG_ZHONGWENKU, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Get the page HTML for analysis
        html_content = await page.content()
        debug_dir = BASE / "debug"
        debug_dir.mkdir(exist_ok=True)

        # Save page HTML
        (debug_dir / f"zhongwenku.html").write_text(html_content)

        # Step 3: Find entry links and try them
        if entry_name == "wanfang":
            # Try each 万方入口
            entry_links = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.textContent.includes('万方'))
                    .map(a => ({text: a.textContent.trim(), href: a.href}))
            """)
        elif entry_name == "weipu":
            entry_links = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.textContent.includes('维普'))
                    .map(a => ({text: a.textContent.trim(), href: a.href}))
            """)
        elif entry_name == "cnki":
            entry_links = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.textContent.includes('知网'))
                    .map(a => ({text: a.textContent.trim(), href: a.href}))
            """)
        else:
            entry_links = []

        log.info(f"\nFound {len(entry_links)} entry links:")
        for link in entry_links:
            log.info(f"  [{link['text']}] → {link['href']}")

        # Step 4: Try navigating directly to the first entry
        if entry_links:
            target = entry_links[0]
            log.info(f"\nTrying entry: {target['text']} → {target['href']}")

            # Clear request log
            requests_log.clear()

            try:
                await page.goto(target["href"], wait_until="domcontentloaded",
                                timeout=45000)
                await page.wait_for_load_state("networkidle", timeout=30000)
                await asyncio.sleep(5)
            except Exception as e:
                log.warning(f"Navigation timeout/ex: {e}")
                await asyncio.sleep(3)

            log.info(f"\nFinal URL: {page.url[:200]}")
            log.info(f"Page title: {await page.title()}")

            # Save final page
            (debug_dir / f"{entry_name}_final.html").write_text(await page.content())
            try:
                await page.screenshot(path=str(debug_dir / f"{entry_name}_final.png"))
            except Exception:
                pass

            # Print redirect chain (filter to unique URLs)
            seen_urls = set()
            log.info(f"\nRedirect chain ({len(requests_log)} events):")
            for r in requests_log:
                key = r["url"][:120]
                if key not in seen_urls:
                    seen_urls.add(key)
                    log.info(f"  [{r['phase']}] {r.get('status','')} {key}")

            # Step 5: Try searching for a test article
            log.info(f"\nTrying search for test article...")
            try:
                search_input = await page.query_selector(
                    "input[type='text'], input[name='q'], input[name='keyword'], "
                    "input[name='searchword'], input[class*='search'], "
                    "input[placeholder*='搜索'], input[placeholder*='search'], "
                    "input[id*='search'], input[id*='keyword'], #txt_search"
                )
                if search_input:
                    test_title = "冲压发动机"
                    await search_input.fill("")
                    await search_input.type(test_title, delay=30)
                    await asyncio.sleep(1)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(5)
                    log.info(f"Search result URL: {page.url[:200]}")
                    (debug_dir / f"{entry_name}_search.html").write_text(await page.content())
                    try:
                        await page.screenshot(path=str(debug_dir / f"{entry_name}_search.png"))
                    except Exception:
                        pass

                    # Check for results
                    result_links = await page.evaluate("""() =>
                        Array.from(document.querySelectorAll('a[href]'))
                            .filter(a => (a.textContent||'').trim().length > 10)
                            .slice(0, 10)
                            .map(a => ({text: (a.textContent||'').trim().slice(0,60), href: a.href}))
                    """)
                    log.info(f"Search result links ({len(result_links)}):")
                    for rl in result_links[:5]:
                        log.info(f"  [{rl['text'][:50]}] → {rl['href'][:100]}")
                else:
                    log.info("No search input found on page")
            except Exception as e:
                log.warning(f"Search test failed: {e}")

        log.info(f"\nDebug files saved to {debug_dir}/")
        await browser.close()


# ── Orchestration ────────────────────────────────────────────────────────────

async def fetch_article_with_fallback(
    article: dict,
    strategies: list[ShutongStrategy],
    page: Page,
) -> dict:
    """Try each strategy in order, return first successful result."""
    for strategy in strategies:
        log.info(f"\n  → Trying {strategy.name}...")
        try:
            if not await strategy.navigate_to_source(page):
                log.warning(f"  {strategy.name}: navigation failed")
                continue

            await rate_delay()

            detail_url = await strategy.search_by_title(page, article["title"])
            if not detail_url:
                log.info(f"  {strategy.name}: article not found")
                # Search may have already navigated — try extracting from current page
                result = await strategy.extract_fulltext(page)
                if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
                    log.info(f"  ✓ {strategy.name} OK ({len(result['text'])} chars)")
                    return result
                continue

            log.info(f"  {strategy.name}: detail URL: {detail_url[:100]}")
            try:
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                await asyncio.sleep(3)
            except Exception:
                pass

            result = await strategy.extract_fulltext(page)
            if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
                log.info(f"  ✓ {strategy.name} OK ({len(result['text'])} chars)")
                return result
            else:
                log.info(f"  {strategy.name}: content too short ({len(result.get('text',''))})")
        except Exception as e:
            log.warning(f"  {strategy.name} error: {e}")
            continue

    return {"text": ""}


async def process_article(article: dict, strategies: list[ShutongStrategy],
                           page: Page):
    """Process a single article through all strategies."""
    log.info(f"\n{'='*60}")
    log.info(f"Article: {article['title'][:60]}...")
    log.info(f"Source: {article.get('source','')}")

    result = await fetch_article_with_fallback(article, strategies, page)

    if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
        return result

    log.warning(f"  ✗ All strategies failed for: {article['title'][:50]}")
    return None


# ── Browser / Playwright Lifecycle ──────────────────────────────────────────

async def create_browser_context(shutong_cookies: dict[str, str]):
    """Create Playwright browser context with shutong cookies."""
    p_obj = await async_playwright().start()
    browser = await p_obj.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    )
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
    )
    await set_cookies_in_context(ctx, shutong_cookies)
    return p_obj, browser, ctx


# ── Batch Processing ─────────────────────────────────────────────────────────

async def process_database(db_path: Path, theme: str,
                            strategies: list[ShutongStrategy],
                            limit: int = 0) -> dict:
    """Process all CNKI articles in one database."""
    stats = {"total": 0, "fetched": 0, "failed": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")

    articles = get_cnki_articles_without_content(conn, limit)
    stats["total"] = len(articles)
    log.info(f"[{theme}] {len(articles)} CNKI articles need content")

    if not articles:
        conn.close()
        return stats

    shutong_cookies = load_shutong_cookies()
    if not shutong_cookies:
        conn.close()
        return stats

    p_obj, browser, ctx = await create_browser_context(shutong_cookies)
    page = await ctx.new_page()

    # Verify session
    if not await verify_shutong_session(page):
        log.error("Session invalid, aborting")
        await browser.close()
        await p_obj.stop()
        conn.close()
        return stats

    try:
        for i, article in enumerate(articles):
            log.info(f"\n[{theme}] [{i+1}/{len(articles)}]")
            await rate_delay()

            result = await process_article(article, strategies, page)

            if result and result.get("text"):
                success = update_article_db(
                    conn, article["id"],
                    result["text"],
                    doi=result.get("doi", ""),
                    image_url=result.get("image_url", ""),
                    images=result.get("images", []),
                )
                if success:
                    stats["fetched"] += 1
                else:
                    stats["failed"] += 1
            else:
                stats["failed"] += 1

            # Periodic context cleanup
            if len((await ctx.pages)) > 5:
                for p in (await ctx.pages)[1:]:
                    await p.close()
                page = await ctx.new_page()

    finally:
        await browser.close()
        await p_obj.stop()
        conn.close()

    return stats


def run_batch():
    """Entry point for batch processing (sync wrapper)."""
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    limit = 0
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    strategies = [CnkiStrategy()]
    # WanfangStrategy 和 WeipuStrategy 暂不可用（书童入口已失效）
    # 如需恢复，取消下面注释：
    # strategies += [WanfangStrategy(), WeipuStrategy()]

    dbs = []
    if not aam_only:
        dbs.append((config.BASE_DIR / "data" / "news.db", "news"))
    if not news_only:
        dbs.append((config.BASE_DIR / "data" / "aam.db", "aam"))

    log.info("=" * 60)
    log.info("书童 Full Text Fetcher")
    log.info(f"Strategies: {[s.name for s in strategies]}")
    log.info(f"Databases: {[d[1] for d in dbs]}")
    if limit:
        log.info(f"Limit: {limit}")
    log.info("=" * 60)

    all_stats = {}
    for db_path, theme in dbs:
        if not db_path.exists():
            log.warning(f"DB not found: {db_path}")
            continue
        log.info(f"\n{'='*60}\nProcessing {theme}\n{'='*60}")
        stats = asyncio.run(process_database(db_path, theme, strategies, limit))
        all_stats[theme] = stats
        log.info(f"\n[{theme}] fetched={stats['fetched']}/{stats['total']} failed={stats['failed']}")

    log.info("\n" + "=" * 60)
    log.info("Done!")
    for theme, s in all_stats.items():
        log.info(f"  {theme}: {s['fetched']}/{s['total']} ok")
    log.info("=" * 60)


async def run_test_single(title: str):
    """Test fetching a single article by title."""
    shutong_cookies = load_shutong_cookies()
    if not shutong_cookies:
        return

    strategies = [CnkiStrategy(), WanfangStrategy(), WeipuStrategy()]

    p_obj, browser, ctx = await create_browser_context(shutong_cookies)
    page = await ctx.new_page()

    if not await verify_shutong_session(page):
        log.error("Session invalid")
        await browser.close()
        await p_obj.stop()
        return

    try:
        article = {"title": title, "source": "CNKI - test", "url": "", "author": "", "published": ""}
        result = await process_article(article, strategies, page)
        if result and result.get("text"):
            log.info(f"\n✓ SUCCESS: {len(result['text'])} chars")
            log.info(f"  DOI: {result.get('doi','')}")
            log.info(f"  First 300: {result['text'][:300]}")
        else:
            log.error(f"\n✗ FAILED for '{title}'")
    finally:
        await browser.close()
        await p_obj.stop()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if "--debug-entry" in sys.argv:
        idx = sys.argv.index("--debug-entry")
        entry = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "wanfang"
        asyncio.run(debug_entry(entry))
        return

    if "--test-title" in sys.argv:
        idx = sys.argv.index("--test-title")
        title = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if title:
            asyncio.run(run_test_single(title))
        return

    run_batch()


if __name__ == "__main__":
    main()
