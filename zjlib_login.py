#!/usr/bin/env python3
"""
Zhejiang Library (浙江图书馆) Playwright login script.
Logs in, navigates to CNKI resource, clicks through to generate a session-bound goto token,
then saves token and cookies for use by the monitor.

Usage:
  python3 zjlib_login.py                    # interactive login, save session
  python3 zjlib_login.py --fetch-url <url>  # login + fetch one article URL through proxy
"""
import asyncio, json, sys, re, time, os
from pathlib import Path

BASE = Path(__file__).parent
COOKIE_FILE = BASE / ".cnki_cookies.json"
PROXY_FILE = BASE / ".cnki_proxy"
CREDENTIALS = {
    "id": os.environ.get("CNKI_USER_ID", "410322198907101852"),
    "password": os.environ.get("CNKI_PASSWORD_ZJLIB", "zly7830469L@"),
}

# ── helpers ──────────────────────────────────────────────────────────────────

def save_cookies(cookies: list[dict]):
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
    print(f"  Cookies saved → {COOKIE_FILE} ({len(cookies)} cookies)")

def save_proxy_config(token: str, cookie_name: str = "", cookie_value: str = ""):
    """Save 3-line format: token, cookie_name, cookie_value."""
    PROXY_FILE.write_text(f"{token}\n{cookie_name}\n{cookie_value}")
    print(f"  Proxy config saved → {PROXY_FILE}")

def cookie_dict(cookies: list[dict]) -> dict:
    return {c["name"]: c["value"] for c in cookies}

# ── Playwright login + CNKI access flow ─────────────────────────────────────

async def do_login(page) -> dict:
    """Log into www.zjlib.cn, return cookies dict after login."""
    print("Step 1: navigating to www.zjlib.cn...")
    await page.goto("https://www.zjlib.cn/", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    # Click the login button — the "登录" link in the top bar
    login_btn = page.locator("a:text('登录')").first
    if await login_btn.is_visible():
        await login_btn.click()
        print("  Clicked login button")
    else:
        print("  Login button not found, trying direct navigation...")

    await asyncio.sleep(3)

    # Switch to the login iframe if present
    frames = page.frames
    print(f"  Found {len(frames)} frames")
    main = page

    # Check for login form elements
    # Radio buttons for login mode: first is 身份证号/手机号, second is 手机号快捷登录
    # Click the first radio if not already selected
    radio_id = main.locator("input[type='radio']").first
    if await radio_id.is_visible(timeout=3000):
        is_checked = await radio_id.is_checked()
        if not is_checked:
            await radio_id.check()
            print("  Selected ID card login mode")
            await asyncio.sleep(1)

    # Fill ID card / phone number
    id_input = main.locator("input[placeholder='请输入身份证号/手机号']").first
    if await id_input.is_visible(timeout=5000):
        await id_input.fill(CREDENTIALS["id"])
        print("  Filled ID card number")
    else:
        # Fallback: try any visible text input before password
        inputs = await main.locator("input:not([type='radio']):not([type='checkbox']):not([type='password'])").all()
        for inp in inputs:
            if await inp.is_visible():
                ph = await inp.get_attribute("placeholder") or ""
                print(f"  Found visible input: placeholder='{ph}'")
                await inp.fill(CREDENTIALS["id"])
                break

    # Fill password
    pw_input = main.locator("input[placeholder='请输入读者密码']").first
    if await pw_input.is_visible(timeout=3000):
        await pw_input.fill(CREDENTIALS["password"])
        print("  Filled password")
    else:
        pw_input = main.locator("input[type='password']").first
        if await pw_input.is_visible(timeout=3000):
            await pw_input.fill(CREDENTIALS["password"])
            print("  Filled password (fallback)")

    await asyncio.sleep(1)

    # Click login button — try various selectors
    for btn_text in ["登 录", "登录", " 登 录"]:
        btn = main.locator(f"button:text('{btn_text.strip()}')").first
        if await btn.is_visible(timeout=2000):
            await btn.click()
            print(f"  Clicked login button: '{btn_text.strip()}'")
            break
    else:
        # Try by class
        btn = main.locator("button.ant-btn-primary").first
        if await btn.is_visible(timeout=2000):
            await btn.click()
            print("  Clicked primary button")
        else:
            print("  Login button not found")

    await asyncio.sleep(5)

    # Save screenshot after login
    await page.screenshot(path=BASE / "debug_after_login.png")
    print("  Screenshot: debug_after_login.png")

    cookies = await page.context.cookies()
    cdict = cookie_dict(cookies)
    print(f"  Cookies after login: {len(cookies)}")
    if "userToken" in cdict:
        print(f"  userToken: {cdict['userToken'][:40]}...")
    else:
        print("  WARNING: no userToken cookie found")
    save_cookies(cookies)
    return cdict


async def navigate_to_cnki(page) -> str | None:
    """Navigate to digital resources, find CNKI, click '立即访问', return the goto URL."""
    print("\nStep 2: navigating to digital resources page...")
    await page.goto("https://www.zjlib.cn/", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)

    # Click "数字资源" link to go to digital resources
    print("  Looking for digital resources link...")
    # Try multiple possible link texts
    resource_links = [
        page.locator("a:text('数字资源')").first,
        page.locator("a:text('数字资源')").first,
        page.locator("a:text('资源')").first,
    ]
    clicked = False
    for link in resource_links:
        if await link.is_visible(timeout=3000):
            href = await link.get_attribute("href")
            print(f"  Found digital resources link: {href}")
            await link.click()
            clicked = True
            break

    if not clicked:
        # Try direct navigation
        print("  No digital resources link found, trying direct URL...")
        await page.goto("https://www.zjlib.cn/Resource.htm", wait_until="domcontentloaded", timeout=30000)

    await asyncio.sleep(3)
    await page.screenshot(path=BASE / "debug_resources.png")
    print("  Screenshot: debug_resources.png")

    # Check current URL
    current_url = page.url
    print(f"  Current URL: {current_url}")

    # Look for the letter filter tabs
    print("\nStep 3: clicking letter 'Z' filter...")
    # The resource list has letter filter buttons
    letter_z = page.locator("a:text('Z')").first
    if await letter_z.is_visible(timeout=5000):
        await letter_z.click()
        print("  Clicked letter Z filter")
        await asyncio.sleep(3)
    else:
        # Try other selectors for letter filter
        letter_z = page.locator("span:text('Z')").first
        if await letter_z.is_visible(timeout=3000):
            await letter_z.click()
            print("  Clicked span Z filter")
            await asyncio.sleep(3)
        else:
            print("  Letter Z filter not found")

    await page.screenshot(path=BASE / "debug_letter_z.png")
    print("  Screenshot: debug_letter_z.png")

    # Find CNKI resource
    print("\nStep 4: finding CNKI resource...")
    cnki_texts = [
        "知网",
        "CNKI",
        "中国知网",
        "知网数据库",
    ]
    cnki_link = None
    for text in cnki_texts:
        link = page.locator(f"a:text('{text}')").first
        if await link.is_visible(timeout=3000):
            print(f"  Found CNKI link containing '{text}'")
            cnki_link = link
            break

    if not cnki_link:
        # Try broader search
        all_links = await page.locator("a").all()
        print(f"  Checking {len(all_links)} links on page...")
        for link in all_links:
            txt = await link.inner_text()
            if "知网" in txt or "CNKI" in txt:
                print(f"  Found: '{txt[:80]}'")
                cnki_link = link
                break

    if cnki_link:
        # Scroll to the link
        await cnki_link.scroll_into_view_if_needed()
        await asyncio.sleep(1)

        # Check for "立即访问" button near this link
        parent = cnki_link.locator("..")
        visit_btn = parent.locator("text='立即访问'").first
        if await visit_btn.is_visible(timeout=3000):
            print("  Found '立即访问' button, clicking...")
            async with page.context.expect_page() as new_page_info:
                await visit_btn.click()
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            cnki_url = new_page.url
            print(f"  CNKI access URL: {cnki_url}")
            await new_page.screenshot(path=BASE / "debug_cnki_page.png")
            print("  Screenshot: debug_cnki_page.png")
            return cnki_url
        else:
            print("  No '立即访问' button found near CNKI link")
            # Try clicking the link itself
            print("  Clicking the CNKI link directly...")
            async with page.context.expect_page() as new_page_info:
                await cnki_link.click()
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            cnki_url = new_page.url
            print(f"  CNKI access URL: {cnki_url}")
            return cnki_url
    else:
        print("  CNKI resource not found!")
        await page.screenshot(path=BASE / "debug_no_cnki.png")
        return None


async def extract_goto_token(cnki_url: str) -> str | None:
    """Extract the goto token from a CNKI access URL."""
    # Pattern: /goto/{TOKEN}/kns55/... or /goto/{TOKEN}/kcms/...
    m = re.search(r"/goto/([^/]+(?:/[^/]+)?)/kns55|/goto/([^/]+(?:/[^/]+)?)/kcms", cnki_url)
    if m:
        token = m.group(1) or m.group(2)
        print(f"  Extracted token: {token}")
        return token
    # Simpler: grab everything between /goto/ and the next / that precedes kns or kcms
    m = re.search(r"/goto/([^/]+(?:/[^/]+)?)/", cnki_url)
    if m:
        token = m.group(1)
        print(f"  Extracted token (fallback): {token}")
        return token
    print(f"  Could not extract token from URL: {cnki_url}")
    return None


async def fetch_article_through_proxy(page, token: str, article_url: str, cookies: dict):
    """Try to fetch a CNKI article through the proxy using the authenticated session."""
    # Build proxied URL
    for domain in ("kns.cnki.net", "www.cnki.net", "navi.cnki.net"):
        if domain in article_url:
            path = article_url[article_url.index(domain) + len(domain):]
            proxied = f"https://erm.zjlib.cn/goto/{token}{path}"
            print(f"\nFetching article through proxy: {proxied[:100]}...")
            await page.goto(proxied, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            await page.screenshot(path=BASE / "debug_article_fetch.png")
            print(f"  Response URL: {page.url}")
            print(f"  Status: {await page.evaluate('document.body.innerText.substring(0, 200)')}")
            return page.url
    print("  Could not identify domain in article URL")
    return None


async def main():
    from playwright.async_api import async_playwright

    fetch_url = None
    if "--fetch-url" in sys.argv:
        idx = sys.argv.index("--fetch-url")
        fetch_url = sys.argv[idx + 1]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # Step 1: Login
        cdict = await do_login(page)
        if not cdict.get("userToken"):
            print("\nWARNING: Login may have failed, continuing anyway...")

        # Step 2: Navigate to CNKI
        cnki_url = await navigate_to_cnki(page)
        if cnki_url:
            token = await extract_goto_token(cnki_url)
            if token:
                # Save the new token
                cookies = await context.cookies()
                ck_dict = cookie_dict(cookies)
                save_proxy_config(
                    token,
                    ck_dict.get("SSO-SESSIONID", ""),
                    ""
                )
                print(f"\n  New token saved! Token: {token}")
                print(f"  SSO-SESSIONID: {ck_dict.get('SSO-SESSIONID', 'N/A')[:30]}...")

                # If a fetch URL was provided, try fetching
                if fetch_url:
                    await fetch_article_through_proxy(page, token, fetch_url, ck_dict)
            else:
                print("\n  Could not extract token. Manual inspection needed.")
                print(f"  CNKI URL: {cnki_url}")
        else:
            print("\nFailed to access CNKI. Debug screenshots saved.")
            # Try getting the page content for debugging
            content = await page.content()
            debug_html = BASE / "debug_resources.html"
            debug_html.write_text(content)
            print(f"  Page HTML saved → {debug_html}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
