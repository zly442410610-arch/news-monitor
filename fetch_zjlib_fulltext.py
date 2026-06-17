#!/usr/bin/env python3
"""
浙江图书馆 CNKI 全文获取 — 通过 erm.zjlib.cn 代理走 kns55 旧版接口。

注意：
  • 浙江图书馆 proxy 只路由 /kns55 路径，/kcms2 返回 404
  • 收录范围有限，部分 CNKI 文章可能不在浙江图书馆的订阅库中
  • 搜索策略：完整标题 → 逐步截断（20/15/10/8/6字）直到命中
  • 提取内容为详情页摘要+元数据（约 3000 字），非全文
  • 若 6 篇文章已成功回填全文（19k-35k 字），那是通过旧代理完成的

用法:
  python3 fetch_zjlib_fulltext.py                          # 批量（两个 db）
  python3 fetch_zjlib_fulltext.py --test-title "标题"      # 单篇测试
  python3 fetch_zjlib_fulltext.py --limit 3                # 限 N 篇
  python3 fetch_zjlib_fulltext.py --news-only              # news.db 只
  python3 fetch_zjlib_fulltext.py --aam-only               # aam.db 只
  python3 fetch_zjlib_fulltext.py --debug                  # 保存截图/HTML
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext

BASE = Path(__file__).parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("zjlib")

# ── 常量 ──────────────────────────────────────────────────────────────────────
# 直接定义必需常量，避免提前 import config（config → theme.py 有语法错误）

KNS55_BASE_PATH = "/kns55"

COOKIE_JAR = BASE / ".cnki_cookies.json"
SHUTONG_COOKIE_JAR = BASE / ".shutong_cookies.json"
PROXY_FILE = BASE / ".cnki_proxy"

MIN_CONTENT_LEN = 500
MAX_CONTENT_LEN = 2000000
DELAY_MIN = float(os.environ.get("CNKI_FETCH_DELAY_MIN", "3"))
DELAY_MAX = float(os.environ.get("CNKI_FETCH_DELAY_MAX", "10"))
CNKI_PROXY_BASE = os.environ.get("CNKI_PROXY_BASE", "https://erm.zjlib.cn/goto")

# 搜索框选择器（按优先级）
SEARCH_INPUT_SELECTORS = [
    "#txt_1_value1",       # 标准检索 — 篇名/关键词/摘要
    "#txt_search",         # 快速检索（可能在 kns55 不同版本中存在）
    "input[name='txt_1_value1']",
    "input[placeholder='输入检索词']",
]

# 搜索按钮选择器（按优先级）
SEARCH_BUTTON_SELECTORS = [
    "#btnSearch",
    "#btnResSearch",
    "input[value='检索']",
    "input[value='搜索']",
    "button:has-text('检索')",
    "button:has-text('搜索')",
    "a:has-text('检索')",
    "a:has-text('搜索')",
    "input[type='image']",
    "input[type='submit']",
]

# 结果链接选择器（按优先级）
RESULT_LINK_SELECTORS = [
    "a[href*='detail.aspx']",
    "a[href*='FileName=']",
    "a[href*='filename=']",
    "[class*='result'] a",
    "[class*='list'] a",
    "table a",
    "td a",
    "a[target='_blank']",
]

# 结果页 URL 模式
RESULT_URL_PATTERNS = [
    "brief",
    "result",
]

# ── 延迟 ──────────────────────────────────────────────────────────────────────


async def rate_delay():
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    log.info(f"  Delay {delay:.1f}s...")
    await asyncio.sleep(delay)


# ── Session / 配置 ────────────────────────────────────────────────────────────


def _load_env_proxy() -> tuple[str, str]:
    """从环境变量加载代理配置。返回 (token, key)."""
    token = os.environ.get("CNKI_PROXY_TOKEN", "")
    key = os.environ.get("CNKI_PROXY_KEY", "")
    if token and key:
        return token, key
    # CNKI_PROXY_BASE has the base URL; also check if token is in it
    return "", ""


def _load_file_proxy(filepath: Path) -> tuple[str, str]:
    """从 .cnki_proxy 文件加载代理配置。返回 (token, key)."""
    if not filepath.exists():
        return "", ""
    try:
        raw = filepath.read_text().strip()
        # Try JSON
        try:
            cfg = json.loads(raw)
            return cfg.get("token", ""), cfg.get("key", "")
        except (json.JSONDecodeError, Exception):
            pass
        # Legacy line format
        lines = raw.split("\n")
        token = lines[0].strip() if lines else ""
        return token, ""
    except Exception:
        return "", ""


def get_proxy_config() -> tuple[str, str]:
    """加载 CNKI 代理 token 和 key. 返回 (token, key)."""
    token, key = _load_env_proxy()
    if token and key:
        return token, key

    token, key = _load_file_proxy(PROXY_FILE)
    if token and key:
        return token, key

    raise ValueError(
        "未找到代理配置，请先运行 zjlib_cnki_login.py 登录一次，"
        "或设置环境变量 CNKI_PROXY_TOKEN 和 CNKI_PROXY_KEY"
    )


def get_cookie_dict() -> dict[str, str]:
    """加载 erm.zjlib.cn cookies."""
    if COOKIE_JAR.exists():
        try:
            data = json.loads(COOKIE_JAR.read_text())
            cookies = data.get("cookies", {})
            if cookies:
                log.info(f"已加载 {len(cookies)} 个 cookies")
                return cookies
        except Exception:
            pass
    return {}


def ensure_session():
    """确保 ZJLib session 有效，必要时重新登录。"""
    cookies = get_cookie_dict()
    if not cookies:
        log.info("未缓存 ZJLib cookies，正在登录...")
        try:
            sys.path.insert(0, str(BASE))
            from cnki_session import refresh_cnki_session
            refresh_cnki_session()
            log.info("  refresh_cnki_session() 完成")
        except Exception as e:
            log.warning(f"  session 刷新失败: {e}")
    else:
        log.info("ZJLib cookies 已缓存")


async def set_cookies_in_context(ctx: BrowserContext, cookie_dict: dict[str, str]):
    """在 Playwright context 中设置 erm.zjlib.cn cookies."""
    for name, value in cookie_dict.items():
        try:
            await ctx.add_cookies([{
                "name": name, "value": value,
                "domain": "erm.zjlib.cn", "path": "/",
            }])
        except Exception as e:
            log.warning(f"设置 cookie {name} 失败: {e}")


# ── DB 查询（直接实现，避免 import config） ────────────────────────────────────


def _get_db_path(theme: str) -> Path:
    """获取数据库路径。"""
    return BASE / "data" / f"{theme}.db"


def get_cnki_articles_without_content(conn: sqlite3.Connection,
                                       limit: int = 0) -> list[dict]:
    """获取数据库中缺少内容的 CNKI 文章。"""
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


def update_article_content(conn: sqlite3.Connection, article_id: str,
                           content: str, doi: str = "",
                           image_url: str = "", images: list[str] = None):
    """更新文章全文内容到数据库。"""
    if not content or len(content) < MIN_CONTENT_LEN:
        return False
    if len(content) > MAX_CONTENT_LEN:
        content = content[:MAX_CONTENT_LEN]

    try:
        # 尝试用 monitor 的 update_article_content（含翻译）
        sys.path.insert(0, str(BASE))
        from monitor import update_article_content as _monitor_update
        _monitor_update(conn, article_id, content,
                        title="", images=images or [], doi=doi)
    except Exception:
        # 兜底：直接更新
        import json as _json
        images_json = _json.dumps(images) if images else ""
        if doi:
            conn.execute(
                "UPDATE articles SET content=?, doi=?, content_images=? WHERE id=?",
                (content, doi, images_json, article_id)
            )
        else:
            conn.execute(
                "UPDATE articles SET content=?, content_images=? WHERE id=?",
                (content, images_json, article_id)
            )
        conn.commit()

    if image_url:
        try:
            conn.execute("UPDATE articles SET image_url=? WHERE id=?",
                         (image_url, article_id))
            conn.commit()
        except Exception:
            pass

    log.info(f"  ✓ DB 已更新: {len(content)} 字符" +
             (f", doi={doi}" if doi else ""))
    return True


# ── 工具函数 ─────────────────────────────────────────────────────────────────


def _char_overlap(a: str, b: str) -> float:
    """计算两个字符串的字符重叠率（基于 character bigram）。"""
    if not a or not b:
        return 0.0
    ab = set()
    for i in range(len(a) - 1):
        ab.add(a[i:i + 2])
    bb = set()
    for i in range(len(b) - 1):
        bb.add(b[i:i + 2])
    if not ab or not bb:
        return 0.0
    inter = ab & bb
    return 2.0 * len(inter) / (len(ab) + len(bb))


def _best_match(query: str, candidates: list[str]) -> tuple[int, str, float]:
    """在候选列表中找出与 query 最匹配的条目。"""
    best_idx = -1
    best_score = 0.0
    best_title = ""
    for i, c in enumerate(candidates):
        score = _char_overlap(query, c)
        if score > best_score:
            best_score = score
            best_idx = i
            best_title = c
    return best_idx, best_title, best_score


# ── kns55 搜索 ────────────────────────────────────────────────────────────────


def build_proxy_url(path: str) -> str:
    """构建经过 erm.zjlib.cn 代理的 URL。"""
    token, key = get_proxy_config()
    return f"{CNKI_PROXY_BASE}/{token}/e/{key}{path}"


async def _extract_results(frame) -> list[dict]:
    """从 iframe 结果页提取所有标题和详情链接。"""
    raw = await frame.evaluate('''function(){
        var links=document.querySelectorAll("a");
        var res=[];
        for(var i=0;i<links.length;i++){
            var t=links[i].innerText.trim();
            var h=links[i].href;
            if(t.length>4&&h&&h.indexOf("detail.aspx")>=0)
                res.push({title:t,href:h});
        }
        return JSON.stringify(res);
    }''')
    import json as _json
    return _json.loads(raw)


async def _wait_for_iframe(page: Page, timeout=20) -> Optional[any]:
    """等待 #iframeResult 并返回 content_frame。"""
    try:
        el = await page.wait_for_selector("#iframeResult", timeout=timeout * 1000)
        frame = await el.content_frame()
        if frame:
            try:
                await frame.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(3)
        return frame
    except Exception:
        return None


async def _do_search(page: Page, term: str) -> Optional[any]:
    """执行一次 kns55 搜索，返回 iframe content_frame 或 None。"""
    await page.fill("#txt_1_value1", "")
    await page.type("#txt_1_value1", term, delay=10)
    await asyncio.sleep(0.3)

    for selector in SEARCH_BUTTON_SELECTORS:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click(timeout=5000)
                break
        except Exception:
            continue

    await asyncio.sleep(2)
    return await _wait_for_iframe(page, timeout=10)


async def search_kns55(page: Page, title: str,
                        debug_dir: Optional[Path] = None) -> Optional[str]:
    """
    在 kns55 上按标题搜索文章。

    策略：
      1. 完整标题搜索
      2. 如果 0 结果，逐字缩短（去掉末尾一个字）直到有结果或剩下 6 个字
      3. 从结果中按标题相似度匹配最佳文章
      4. 导航到详情页

    返回详情页 URL 或 None。
    """
    # Step 1: 导航到 kns55 首页
    kns55_url = build_proxy_url(KNS55_BASE_PATH)
    log.info(f"  导航到 kns55 ...")
    try:
        await page.goto(kns55_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(3)

    if debug_dir:
        try:
            await page.screenshot(path=debug_dir / "01_kns55_home.png")
        except Exception:
            pass

    body = await page.inner_text("body")
    if "浙江图书馆" not in body[:500]:
        log.warning("  kns55 session 可能已过期")
    log.info(f"  页面已加载: {await page.title()}")

    # Step 2: 渐进式搜索
    # kns55 完整标题搜不到时，尝试不同长度的截断
    # 按长度降序尝试：full → 20 → 15 → 10 → 8 → 6
    search_terms = [title]
    for cutoff in (20, 15, 10, 8, 6):
        t = title[:cutoff]
        if len(t) < len(search_terms[-1]) and len(t) >= 6:
            search_terms.append(t)

    frame = None
    for i, term in enumerate(search_terms):
        if i > 0:
            # 回 kns55 首页重新搜索
            try:
                await page.goto(kns55_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(2)

        log.info(f"  搜索词 [{i+1}/{len(search_terms)}] ({len(term)}字): '{term}'")
        frame = await _do_search(page, term)
        if frame:
            results = await _extract_results(frame)
            if results:
                break
        log.info(f"  0 结果")

    if not frame:
        log.warning("  搜索失败（iframe 未加载）")
        return None

    results = await _extract_results(frame)
    log.info(f"  检索到 {len(results)} 条结果")

    if not results:
        log.warning("  kns55 中未找到匹配文章（可能不在浙江图书馆收录范围内）")
        return None

    if debug_dir:
        try:
            await page.screenshot(path=debug_dir / "02_search_results.png")
            (debug_dir / "02_search_results.html").write_text(await page.content())
        except Exception:
            pass

    # Step 3: 在结果中匹配最佳标题
    candidates = [r["title"] for r in results]
    idx, match_title, score = _best_match(title, candidates)
    match_url = results[idx]["href"]

    log.info(f"  最佳匹配: '{match_title[:50]}' (score={score:.2f})")

    if score < 0.25:
        log.warning(f"  匹配度过低 ({score:.2f})，跳过")
        return None

    # Step 4: 导航到详情页
    await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(3)

    if debug_dir:
        try:
            await page.screenshot(path=debug_dir / "03_detail_page.png")
            (debug_dir / "03_detail_page.html").write_text(await page.content())
        except Exception:
            pass

    log.info(f"  详情页: {match_title[:40]}...")
    return page.url


# ── 全文提取（内联实现，避免 import fetch_shutong_fulltext） ──────────────────


async def extract_article_text(page: Page) -> str:
    """多策略提取全文。"""
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
                    log.info(f"  策略 1 ({selector}): {len(t)} 字符")
                    return t
        except Exception:
            continue

    # Strategy 2: JS evaluate — strip nav/footer/script
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
            log.info(f"  策略 2 (evaluate): {len(t)} 字符")
            return t
        if t:
            text = t
    except Exception:
        pass

    # Strategy 3: body.inner_text
    try:
        t = await page.inner_text("body")
        if t and len(t) > MIN_CONTENT_LEN:
            log.info(f"  策略 3 (body): {len(t)} 字符")
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
            log.info(f"  策略 4 (paragraphs): {len(t)} 字符")
            return t
    except Exception:
        pass

    return text


async def extract_doi(page: Page) -> str:
    """从页面提取 DOI。"""
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
    """提取代表性图片和内容图片列表。"""
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


async def extract_from_current_page(page: Page) -> dict:
    """从当前页面提取全文。"""
    text = await extract_article_text(page)
    doi = await extract_doi(page)
    img_url, imgs = await extract_images(page)
    return {"text": text, "doi": doi, "image_url": img_url, "images": imgs}


# ── 文章处理 ──────────────────────────────────────────────────────────────────


async def process_article(article: dict, page: Page,
                          debug_dir: Optional[Path] = None) -> dict:
    """单篇文章处理: 搜索 → 详情页 → 提取全文。"""
    log.info(f"\n  文章: {article['title'][:60]}...")

    detail_url = await search_kns55(page, article["title"], debug_dir=debug_dir)
    if not detail_url:
        log.warning("  ✗ 搜索未找到结果")
        return {"text": ""}

    result = await extract_from_current_page(page)
    if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
        log.info(f"  ✓ 提取到 {len(result['text'])} 字符")
        return result

    log.warning("  ✗ 全文提取失败（内容过短）")
    return {"text": ""}


# ── 浏览器管理 ────────────────────────────────────────────────────────────────


async def create_browser_context():
    """创建 Playwright browser context。返回 (p_obj, browser, ctx)."""
    p_obj = await async_playwright().start()
    browser = await p_obj.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    )
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
    )

    cookies = get_cookie_dict()
    if cookies:
        await set_cookies_in_context(ctx, cookies)
        log.info(f"已设置 {len(cookies)} 个 cookies")

    return p_obj, browser, ctx


# ── 批量处理 ──────────────────────────────────────────────────────────────────


async def process_database(theme: str, limit: int = 0,
                            debug: bool = False) -> dict:
    """处理一个数据库中的所有 CNKI 文章。"""
    stats = {"total": 0, "fetched": 0, "failed": 0}
    debug_dir: Optional[Path] = None

    db_path = _get_db_path(theme)
    if not db_path.exists():
        log.warning(f"数据库不存在: {db_path}")
        return stats

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")

    articles = get_cnki_articles_without_content(conn, limit)
    stats["total"] = len(articles)
    log.info(f"[{theme}] {len(articles)} 篇 CNKI 文章需要全文")

    if not articles:
        conn.close()
        return stats

    ensure_session()

    p_obj, browser, ctx = await create_browser_context()
    page = await ctx.new_page()

    if debug:
        debug_dir = BASE / "debug_zjlib"
        debug_dir.mkdir(exist_ok=True)

    try:
        for i, article in enumerate(articles):
            log.info(f"\n[{theme}] [{i+1}/{len(articles)}]")
            await rate_delay()

            if debug_dir:
                art_dir = debug_dir / f"{i+1}_{article['id'][:8]}"
                art_dir.mkdir(exist_ok=True)
            else:
                art_dir = None

            result = await process_article(dict(article), page, debug_dir=art_dir)

            if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
                success = update_article_content(
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

            # 定期清理页面
            if len(ctx.pages) > 3:
                for p in ctx.pages[1:]:
                    await p.close()
                page = await ctx.new_page()
    finally:
        await browser.close()
        await p_obj.stop()
        conn.close()

    return stats


# ── 单篇测试 ───────────────────────────────────────────────────────────────────


async def test_single(title: str, debug: bool = False):
    """测试单篇文章的搜索和提取。"""
    log.info(f"单篇测试: '{title}'")

    ensure_session()

    debug_dir: Optional[Path] = None
    if debug:
        debug_dir = BASE / "debug_zjlib"
        debug_dir.mkdir(exist_ok=True)

    p_obj, browser, ctx = await create_browser_context()
    page = await ctx.new_page()

    try:
        result = await process_article({"title": title}, page, debug_dir=debug_dir)
        if result.get("text") and len(result["text"]) >= MIN_CONTENT_LEN:
            log.info(f"\n✓ 成功: {len(result['text'])} 字符")
            log.info(f"  DOI: {result.get('doi', '')}")
            log.info(f"  前 300 字符: {result['text'][:300]}")
        else:
            log.error(f"\n✗ 失败: '{title}'")
    finally:
        await browser.close()
        await p_obj.stop()

    if debug:
        log.info(f"\n调试文件已保存至: {debug_dir}/")


# ── CLI ────────────────────────────────────────────────────────────────────────


def main():
    news_only = "--news-only" in sys.argv
    aam_only = "--aam-only" in sys.argv
    debug = "--debug" in sys.argv
    limit = 0
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    # 单篇测试
    if "--test-title" in sys.argv:
        idx = sys.argv.index("--test-title")
        title = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if title:
            asyncio.run(test_single(title, debug=debug))
        return

    # 批量模式
    themes = []
    if not aam_only:
        themes.append("news")
    if not news_only:
        themes.append("aam")

    log.info("=" * 60)
    log.info("浙江图书馆 CNKI 全文获取")
    log.info(f"主题: {themes}")
    if limit:
        log.info(f"限制: {limit} 篇")
    log.info("=" * 60)

    all_stats = {}
    for theme in themes:
        log.info(f"\n{'='*60}\n处理 {theme}\n{'='*60}")
        stats = asyncio.run(process_database(theme, limit, debug=debug))
        all_stats[theme] = stats
        log.info(
            f"\n[{theme}] 成功={stats['fetched']}/{stats['total']} "
            f"失败={stats['failed']}"
        )

    log.info("\n" + "=" * 60)
    log.info("完成!")
    for theme, s in all_stats.items():
        log.info(f"  {theme}: {s['fetched']}/{s['total']}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
