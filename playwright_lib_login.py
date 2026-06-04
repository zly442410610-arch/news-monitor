#!/usr/bin/env python3
"""
Hubei Library CAS Login → CNKI article full-text fetch via Playwright.

Usage:
  python3 playwright_lib_login.py                    # headless
  python3 playwright_lib_login.py --headed            # visible browser
  python3 playwright_lib_login.py --article-id <id>   # fetch specific DB article(s)

Flow:
  1. Go to library homepage → click CAS login link → redirected to IAM SSO
  2. Fill credentials + captcha OCR → submit → get SESSION cookie
  3. Navigate through library portal to find CNKI access
  4. Extract rendered article content from KCMS2 SPA
"""
import asyncio, json, re, sys, base64, io, os
from pathlib import Path
from PIL import Image
import pytesseract
from datetime import datetime

BASE = Path(__file__).parent
COOKIES_PATH = BASE / ".cnki_cookies.json"
PROXY_PATH = BASE / ".cnki_proxy"
OUTPUT_DIR = BASE / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

USERNAME = os.environ["CNKI_USER_ID"]
PASSWORD = os.environ["CNKI_PASSWORD_PLAYWRIGHT"]
LIB_BASE = "https://ycfw.library.hb.cn:8000"

HEADED = "--headed" in sys.argv

# ── CNKI articles from DB to fetch ──
TARGET_ARTICLES = [
    # 基于数值虚拟飞行的串联式高速飞行器级间分离方案设计
    dict(id="b7c84fa7a403cd286c27", url="https://kns.cnki.net/kcms2/article/abstract?v=Klkw5nWhgJGXkk0E5OM2SbMUskBo3izQSQaIaBLeZHPoYU3D-P9ivUfO4HNgtkikcoodROCMNSKS-dmXWDQkCmIJ698S1Oc8xAPxQO8w&uniplatform=NZKPT"),
    # 国外组合循环发动机工程化发展分析与启示
    dict(id="baaf623f433fd652745a", url="https://kns.cnki.net/kcms2/article/abstract?v=pcbjM8AHIkMtXQB0zVGXZDQd-hBFzEId7ltOgQLFZOvJuNO3BSVg3ucg1cNBb5yRFC8GTe916cNDtOqw8B_pNv2bpsML5h1-4ELg-pxn&uniplatform=NZKPT"),
]

def ocr_digits(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    img = img.point(lambda x: 0 if x < 128 else 255)
    text = pytesseract.image_to_string(img, config="--psm 7 digits").strip()
    return re.sub(r"\D", "", text)

async def fill_input(page, selectors, value):
    """Try multiple selectors to find and fill an input field."""
    for sel in selectors:
        try:
            inp = page.locator(sel).first
            if await inp.count() > 0 and await inp.is_visible():
                await inp.fill(value)
                return True
        except:
            continue
    return False

async def click_first(page, selectors):
    """Try multiple selectors and click the first match."""
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return True
        except:
            continue
    return False

async def wait_stable(page, ms=2000):
    """Wait for page to be stable after interaction."""
    await page.wait_for_timeout(ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass

async def do_cas_login(page, context):
    """Execute CAS login flow. Returns True if SESSION cookie obtained."""
    print("\n[Login] Starting CAS flow from library homepage...")

    # Step A: Go to library homepage
    await page.goto(LIB_BASE, wait_until="domcontentloaded", timeout=30000)
    await wait_stable(page, 3000)
    print(f"  Homepage: {page.url[:100]}")

    # Step B: Find and click CAS login link
    # Check if already redirected to IAM
    if "iam.library.hb.cn" in page.url:
        print("  Already on IAM page")
    else:
        cas_found = await click_first(page, [
            'a[href*="cas/login"]',
            'a:has-text("读者证登录")',
            'a:has-text("CAS")',
            'a:has-text("统一认证")',
        ])
        if cas_found:
            print("  Clicked CAS login link")
            await wait_stable(page, 5000)
        else:
            # Try to navigate directly
            print("  CAS link not found, trying direct navigation...")
            await page.goto(f"{LIB_BASE}/cas/login", wait_until="domcontentloaded", timeout=30000)
            await wait_stable(page, 5000)

    print(f"  After CAS redirect: {page.url[:120]}")

    # Step C: Fill credentials (now on IAM page)
    if "iam.library.hb.cn" not in page.url:
        print(f"  [!] Not on IAM page: {page.url}")
        await page.screenshot(path=str(BASE / "err_not_iam.png"))
        return False

    await page.screenshot(path=str(BASE / "iam_page.png"))

    # Fill username
    await fill_input(page, [
        'input[name="username"]',
        'input[id="username"]',
        'input[placeholder*="账"]',
        'input[placeholder*="用户"]',
        'input[type="text"]',
    ], USERNAME)
    print("  Filled username")

    # Fill password
    await fill_input(page, [
        'input[name="password"]',
        'input[id="password"]',
        'input[placeholder*="密"]',
        'input[type="password"]',
    ], PASSWORD)
    print("  Filled password")

    # Step D: Handle captcha with OCR (retry loop)
    for cap_attempt in range(3):
        # Find captcha image
        captcha_src = None
        imgs = await page.locator("img").all()
        for img_el in imgs:
            src = (await img_el.get_attribute("src")) or ""
            if any(k in src.lower() for k in ['captcha', 'code', 'verify']):
                captcha_src = src
                break

        if captcha_src:
            if captcha_src.startswith("/"):
                captcha_src = "https://iam.library.hb.cn" + captcha_src
            # Fetch captcha within browser context (same session)
            b64data = await page.evaluate(f"""
                async () => {{
                    const r = await fetch('{captcha_src}', {{credentials:'include'}});
                    const b = await r.blob();
                    return await new Promise(r => {{
                        const f = new FileReader();
                        f.onloadend = () => r(f.result);
                        f.readAsDataURL(b);
                    }});
                }}
            """)
            img_bytes = base64.b64decode(b64data.split(",")[1])
            captcha_text = ocr_digits(img_bytes)
            print(f"  Captcha OCR: '{captcha_text}'")

            await fill_input(page, [
                'input[name="captcha"]',
                'input[placeholder*="验证"]',
                'input[name="code"]',
            ], captcha_text)
        else:
            print("  No captcha image found")

        # Submit
        await click_first(page, [
            'button[type="submit"]',
            'button:has-text("登录")',
            'input[type="submit"]',
        ])

        await wait_stable(page, 6000)
        print(f"  Attempt {cap_attempt+1} result: {page.url[:100]}")

        # Check for captcha error
        try:
            body = await page.text_content("body") or ""
            if "验证码" in body and "错误" in body:
                print("  [!] Captcha error, retrying with fresh captcha...")
                # Refresh captcha
                await click_first(page, [
                    'img[onclick*="captcha"]',
                    'img[onclick*="verify"]',
                    'img[onclick*="get"]',
                ])
                await page.wait_for_timeout(500)
                continue
            if "success" in body.lower() or "ycfw" in page.url or LIB_BASE in page.url:
                print("  Login successful!")
                break
        except:
            pass

    # Step E: Wait for redirect back to library proxy
    await wait_stable(page, 3000)

    # Save cookies
    cookies = await context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    COOKIES_PATH.write_text(json.dumps(cookie_dict, indent=2, ensure_ascii=False))

    if "SESSION" in cookie_dict:
        print(f"  Got SESSION cookie: {cookie_dict['SESSION'][:40]}...")
        return True
    else:
        print("  No SESSION cookie after login")
        return False


async def extract_proxy_token(page):
    """Extract the Sangfor VPN proxy token from current page HTML/URL."""
    html = await page.content()

    # Check HTML for proxy tokens in resource URLs
    tokens = re.findall(r'/vpn/1/([A-Z0-9]{25,40})', html)
    if tokens:
        return tokens[0]

    # Check URL
    m = re.search(r'/vpn/1/([A-Z0-9]{25,40})', page.url)
    if m:
        return m.group(1)

    # Check all iframes
    for i in range(await page.locator("iframe").count()):
        try:
            src = await page.locator("iframe").nth(i).get_attribute("src")
            if src:
                m = re.search(r'/vpn/1/([A-Z0-9]{25,40})', src)
                if m:
                    return m.group(1)
        except:
            pass

    return None


async def get_cnki_context(page, context):
    """After login, navigate to CNKI via library portal.
    Returns (page_on_cnki, proxy_token) or (None, None)."""
    print("\n[CNKI] Navigating to CNKI via library portal...")

    # Check current page - might already be on library portal
    token = await extract_proxy_token(page)
    if token:
        print(f"  Found proxy token: {token[:30]}...")

    # Refresh - go to library homepage with current cookies
    await page.goto(LIB_BASE, wait_until="domcontentloaded", timeout=30000)
    await wait_stable(page, 3000)

    # Look for CNKI link
    cnki_clicked = await click_first(page, [
        'a:has-text("知网")',
        'a:has-text("CNKI")',
        'a:has-text("中国知网")',
        'a[title*="知网"]',
    ])

    if cnki_clicked:
        await wait_stable(page, 8000)
        print(f"  After CNKI click: {page.url[:120]}")

        # Check for new tab
        if len(context.pages) > 1:
            page = context.pages[-1]
            print(f"  Switched to new tab: {page.url[:120]}")

        token = await extract_proxy_token(page)
        if token:
            print(f"  Token from CNKI page: {token[:30]}...")

        await page.screenshot(path=str(BASE / "cnki_portal.png"))
        return page, token

    # If no CNKI link found, try constructing CNKI access URL directly
    # The library portal usually loads resources via iframes
    print("  No CNKI link found, checking for resource tokens...")

    # Extract token from any resource URL
    html = await page.content()
    all_tokens = re.findall(r'/vpn/1/([A-Z0-9]{25,40})', html)
    if all_tokens:
        token = all_tokens[0]
        print(f"  Found token from resources: {token[:30]}...")
        # Construct CNKI URL with token
        cnki_proxy = f"{LIB_BASE}/https/vpn/1/{token}/www.cnki.net"
        await page.goto(cnki_proxy, wait_until="domcontentloaded", timeout=30000)
        await wait_stable(page, 5000)
        print(f"  CNKI via proxy: {page.url[:120]}")
        await page.screenshot(path=str(BASE / "cnki_via_token.png"))
        return page, token

    return page, token


async def fetch_article_content_in_browser(page, article_url, proxy_token):
    """Navigate to a CNKI article URL within the browser session and extract rendered content.

    For KCMS2 SPAs, we wait for XHR to complete and extract the rendered text.
    """
    print(f"\n[Fetch] Getting article content...")
    print(f"  URL: {article_url[:100]}")

    # Build proxy URL if we have a token
    if proxy_token:
        for domain in ("kns.cnki.net", "www.cnki.net", "navi.cnki.net"):
            if domain in article_url:
                path = article_url[article_url.index(domain) + len(domain):]
                proxy_url = f"{LIB_BASE}/https/vpn/1/{proxy_token}{path}"
                if "uniplatform=" not in proxy_url:
                    proxy_url += "&uniplatform=NZKPT" if "?" in proxy_url else "?uniplatform=NZKPT"
                break
        else:
            proxy_url = article_url
    else:
        proxy_url = article_url

    print(f"  Proxy URL: {proxy_url[:120]}")

    # Navigate to article
    try:
        await page.goto(proxy_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Navigation error: {e}")

    # Wait for the SPA to load content
    await page.wait_for_timeout(15000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass

    print(f"  Final URL: {page.url[:150]}")
    print(f"  Title: {await page.title()}")

    await page.screenshot(path=str(BASE / "article_page.png"))

    # Extract content
    result = await page.evaluate("""() => {
        // Try to find article content in various formats
        const data = {
            title: document.title,
            url: location.href,
            abstract: '',
            keywords: '',
            authors: '',
            affiliation: '',
            fund: '',
            doi: '',
            content: '',
            html: document.body.innerHTML.substring(0, 100000)
        };

        // KCMS2 specific: look for abstract in meta tags
        const meta = document.querySelectorAll('meta');
        meta.forEach(m => {
            const name = (m.getAttribute('name') || '').toLowerCase();
            const content = m.getAttribute('content') || '';
            if (name === 'citation_abstract' || name === 'description') {
                if (content.length > data.abstract.length) data.abstract = content;
            }
            if (name === 'citation_keywords') data.keywords = content;
            if (name === 'citation_author') data.authors = content;
            if (name === 'citation_doi') data.doi = content;
        });

        // KCMS2: JSON-LD structured data
        const ld = document.querySelector('script[type="application/ld+json"]');
        if (ld) data.jsonld = ld.textContent.substring(0, 5000);

        // Get all visible text (excluding scripts, styles)
        const body = document.body || document.documentElement;
        data.body_text = body.innerText.substring(0, 50000);

        // Look for specific CNKI KCMS2 content containers
        const containers = [
            '.article-content', '#article-content', '.main-content',
            '.abstract-content', '.detail-content', '.content',
            '[class*="article"]', '[class*="content"]', '[class*="detail"]',
            '.cnki-content', '#content', '.wrapper'
        ];
        for (const sel of containers) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
                let text = '';
                els.forEach(el => text += el.innerText + '\\n');
                if (text.trim().length > 100) {
                    data.content = text.substring(0, 50000);
                    break;
                }
            }
        }

        return data;
    }""")

    print(f"  Body text length: {len(result.get('body_text',''))}")
    print(f"  Abstract length: {len(result.get('abstract',''))}")
    print(f"  Content length: {len(result.get('content',''))}")

    if result.get('abstract'):
        print(f"  Abstract preview: {result['abstract'][:200]}")
    if result.get('body_text'):
        print(f"  Body preview: {result['body_text'][:300]}")

    return result


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=not HEADED,
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()
        page.set_default_timeout(45000)

        # ── Login ──
        login_ok = await do_cas_login(page, context)
        if not login_ok:
            print("\n[x] Login failed, exiting")
            await page.screenshot(path=str(BASE / "error_login_failed.png"))
            if not HEADED:
                await browser.close()
            return

        # ── Get CNKI context + proxy token ──
        page, proxy_token = await get_cnki_context(page, context)

        # Save token + cookie to config file
        cookies = await context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        jsession = cookie_dict.get("JSESSIONID-UMS-ycfw.library.hb.cn", "")
        if proxy_token:
            PROXY_PATH.write_text(f"{proxy_token}\n{jsession}")
            print(f"\n  Saved proxy config: token={proxy_token[:30]}...")

        # ── Fetch articles ──
        for art in TARGET_ARTICLES:
            result = await fetch_article_content_in_browser(page, art["url"], proxy_token)

            # Save result to file for processing
            output = {
                "id": art["id"],
                "url": art["url"],
                "fetched_at": datetime.now().isoformat(),
                "result": result,
            }
            out_path = OUTPUT_DIR / f"cnki_article_{art['id'][:12]}.json"
            out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
            print(f"  Saved result to {out_path.name}")

            break  # Start with first article only

        if not HEADED:
            await browser.close()
        else:
            input("\nPress Enter to close browser...")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
