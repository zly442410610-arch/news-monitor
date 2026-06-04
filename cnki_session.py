"""
CNKI proxy session manager for Zhejiang Library (erm.zjlib.cn).

Periodically runs Playwright to:
1. Login to www.zjlib.cn
2. Click CNKI "立即访问" to establish session cookies on erm.zjlib.cn
3. Extract cookies for use with requests library

Usage:
    from cnki_session import refresh_cnki_session, load_cnki_cookies
    refresh_cnki_session()           # one-shot refresh
    cookies = load_cnki_cookies()    # {name: value, ...}
"""
import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent
COOKIE_JAR = BASE / ".cnki_cookies.json"
PROXY_FILE = BASE / ".cnki_proxy"
LOCK = threading.Lock()

log = logging.getLogger("cnki_session")

CREDENTIALS = {
    "id": os.environ["CNKI_USER_ID"],
    "password": os.environ["CNKI_PASSWORD_ZJLIB"],
}


def load_cnki_cookies() -> dict[str, str]:
    """Load session cookies from cookie jar. Returns {name: value}."""
    if not COOKIE_JAR.exists():
        return {}
    try:
        data = json.loads(COOKIE_JAR.read_text())
        return data.get("cookies", {})
    except Exception:
        return {}


def save_cnki_cookies(cookies: dict[str, str]):
    """Persist session cookies to cookie jar file."""
    with LOCK:
        COOKIE_JAR.write_text(
            json.dumps({"cookies": cookies}, ensure_ascii=False) + "\n"
        )


def load_proxy_config() -> Optional[dict]:
    """Load {token, key} from .cnki_proxy."""
    if not PROXY_FILE.exists():
        return None
    try:
        return json.loads(PROXY_FILE.read_text())
    except Exception:
        return None


async def _async_refresh() -> Optional[dict[str, str]]:
    """Run Playwright login → CNKI popup → extract cookies.
    Returns {name: value} cookie dict on success, None on failure.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("playwright not installed — cannot refresh CNKI session")
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        try:
            # ── Login ──
            log.info("CNKI session: logging into www.zjlib.cn...")
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

            # Verify login
            if "userToken" not in {c["name"]: c["value"] for c in await ctx.cookies()}:
                log.warning("CNKI session: login failed (no userToken cookie)")
                return None
            log.info("CNKI session: login OK")

            # ── Navigate to digital resources ──
            await page.goto(
                "https://www.zjlib.cn/resource/digital",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(5)

            # Click Z filter
            await page.locator("text=Z").first.click()
            await asyncio.sleep(5)

            # Response handler to keep Vue event loop alive
            async def _on_response(resp):
                if "/bff-api/" in resp.url:
                    try:
                        await resp.text()
                    except Exception:
                        pass
            page.on("response", _on_response)

            # Find the CNKI button
            cnki_btn = None
            for b in await page.locator("button").all():
                txt = await b.inner_text()
                if "立即访问" not in txt:
                    continue
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
                log.warning("CNKI session: CNKI button not found")
                return None

            # ── Click CNKI and capture popup ──
            log.info("CNKI session: clicking '立即访问'...")
            async with page.context.expect_page() as popup_info:
                await cnki_btn.click(force=True, timeout=5000)
            popup = await popup_info.value
            try:
                await popup.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(3)
            log.info(f"CNKI session: popup URL = {popup.url[:100]}...")
            await popup.close()

            # ── Extract cookies ──
            all_cookies = await ctx.cookies()
            erm_cookies = {}
            for c in all_cookies:
                if "erm.zjlib.cn" in c.get("domain", ""):
                    erm_cookies[c["name"]] = c["value"]

            log.info(
                f"CNKI session: got {len(erm_cookies)} erm.zjlib.cn cookies: "
                f"{list(erm_cookies.keys())}"
            )
            return erm_cookies

        except Exception as e:
            log.error(f"CNKI session: refresh failed: {e}")
            return None
        finally:
            await page.close()
            await browser.close()


def refresh_cnki_session() -> bool:
    """Synchronous wrapper: run Playwright session refresh.
    Returns True if cookies were obtained and saved.
    """
    log.info("Refreshing CNKI session...")
    try:
        cookies = asyncio.run(_async_refresh())
    except Exception as e:
        log.error(f"CNKI session refresh error: {e}")
        return False

    if cookies:
        save_cnki_cookies(cookies)
        log.info(f"CNKI session refreshed ({len(cookies)} cookies saved)")
        return True
    else:
        log.warning("CNKI session refresh returned no cookies")
        return False


class CnkiSessionRefresher:
    """Background thread that periodically refreshes the CNKI session.

    Starts a daemon thread that calls refresh_cnki_session() every
    `interval_minutes`. Call `start()` to begin.
    """

    def __init__(self, interval_minutes: int = 30):
        self.interval = interval_minutes
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="cnki-refresher")
        self._thread.start()
        log.info(f"CNKI session refresher started (interval={self.interval}min)")

    def stop(self):
        self._stop.set()

    def _run(self):
        # Do an initial refresh immediately
        if refresh_cnki_session():
            log.info("Initial CNKI session established")
        else:
            log.warning("Initial CNKI session refresh failed, will retry")

        while not self._stop.wait(self.interval * 60):
            if self._stop.is_set():
                break
            refresh_cnki_session()


# Singleton for use across the application
_refresher_instance: Optional[CnkiSessionRefresher] = None


def start_session_refresher(interval_minutes: int = 30):
    """Start the global CNKI session refresher singleton."""
    global _refresher_instance
    if _refresher_instance is None:
        _refresher_instance = CnkiSessionRefresher(interval_minutes=interval_minutes)
        _refresher_instance.start()
    return _refresher_instance


def stop_session_refresher():
    """Stop the global CNKI session refresher."""
    global _refresher_instance
    if _refresher_instance:
        _refresher_instance.stop()
        _refresher_instance = None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    success = refresh_cnki_session()
    print(f"\nRefresh {'OK' if success else 'FAILED'}")
    if success:
        cookies = load_cnki_cookies()
        print(f"Cookies: {json.dumps(cookies, indent=2)}")
