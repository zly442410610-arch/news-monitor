#!/usr/bin/env python3
"""
Zhejiang Library → CNKI proxy token acquisition.
Logs in, clicks CNKI '立即访问', captures the popup opened by the Vue handler,
and extracts the proxy credentials (token + /e/key/) from the resolved URL.

Usage:
  python3 zjlib_cnki_login.py
"""
import asyncio, json, re, sys, os
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
PROXY_FILE = BASE / ".cnki_proxy"
CREDENTIALS = {
    "id": os.environ["CNKI_USER_ID"],
    "password": os.environ["CNKI_PASSWORD_ZJLIB"],
}

def save_config(config: dict):
    PROXY_FILE.write_text(json.dumps(config, ensure_ascii=False) + "\n")
    print(f"Config saved -> {PROXY_FILE}")


async def login_and_navigate(context):
    """Log into www.zjlib.cn, then navigate to digital resources page. Returns the page object."""
    page = await context.new_page()
    print("Step 1: Login...")
    await page.goto("https://www.zjlib.cn/", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    await page.locator("div.login-btn").first.click()
    await asyncio.sleep(2)

    await page.locator("#form_item_readerId").first.fill(CREDENTIALS["id"])
    await page.locator("#form_item_password").first.fill(CREDENTIALS["password"])
    agree = page.locator("#form_item_agree").first
    if await agree.is_visible(timeout=2000) and not await agree.is_checked():
        await agree.check()
    await page.locator("button.auth-form-submit-btn").first.click()
    await asyncio.sleep(8)

    ok = "userToken" in {c["name"]: c["value"] for c in await context.cookies()}
    print(f"  Login {'OK' if ok else 'FAILED'}")
    if not ok:
        await page.close()
        return None

    print("  Navigating to digital resources...")
    await page.goto("https://www.zjlib.cn/resource/digital", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)
    return page


async def get_proxy_url(page) -> str | None:
    """
    Given a page on the digital resources page (Z filter active),
    find the CNKI resource button, click it, capture the popup,
    and return the resolved proxy URL.
    """
    # Click Z filter
    await page.locator("text=Z").first.click()
    await asyncio.sleep(5)

    # Add response handler (keeps page event loop alive)
    async def on_response(resp):
        if "/bff-api/" in resp.url:
            try:
                await resp.text()
            except:
                pass
    page.on("response", on_response)

    # Find the CNKI button
    all_btns = await page.locator("button").all()
    cnki_btn = None
    for b in all_btns:
        txt = await b.inner_text()
        if "立即访问" in txt:
            has_cnki = await b.evaluate("""
                el => { let p = el.parentElement;
                    for (let i = 0; i < 5 && p; i++) {
                        if (p.textContent.includes('知网')) return true;
                        p = p.parentElement;
                    }
                    return false;
                }
            """)
            if has_cnki:
                cnki_btn = b
                break

    if not cnki_btn:
        print("  CNKI button not found!")
        return None

    # Click and capture the popup
    print("  Clicking '立即访问', waiting for popup...")
    async with page.context.expect_page() as popup_info:
        await cnki_btn.click(force=True, timeout=5000)

    popup = await popup_info.value
    try:
        await popup.wait_for_load_state("domcontentloaded", timeout=30000)
    except:
        pass
    await asyncio.sleep(5)

    url = popup.url
    title = await popup.title()
    print(f"  Popup URL: {url[:150]}")
    print(f"  Title: {title}")

    await popup.close()
    return url


def extract_config(url: str) -> dict:
    """Extract token and key from the resolved CNKI proxy URL."""
    cfg = {}
    m = re.search(r'/goto/(\d+)', url)
    if m:
        cfg["token"] = m.group(1)
    m = re.search(r'/e/([a-zA-Z0-9_-]+)', url)
    if m:
        cfg["key"] = m.group(1)
    return cfg


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 900},
        )

        page = await login_and_navigate(ctx)
        if not page:
            await browser.close()
            return

        url = await get_proxy_url(page)
        await page.close()

        if not url:
            print("Failed to get proxy URL!")
            await browser.close()
            return

        cfg = extract_config(url)
        print(f"\nConfig: {json.dumps(cfg, indent=2)}")

        if "token" in cfg and "key" in cfg:
            save_config(cfg)

            # Build proxy URL template
            proxy_tpl = f"https://erm.zjlib.cn/goto/{cfg['token']}/e/{cfg['key']}%s"
            print(f"Proxy URL template: {proxy_tpl % '/kcms2/article/...'}")
        else:
            print("Failed to extract token/key from URL!")
            print(f"Raw URL: {url}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
