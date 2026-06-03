#!/usr/bin/env python3
"""
Import cookies from 书童 proxy for CNKI full-text access.

Usage:
    # Export cookies from browser (Netscape format) first, then:
    python3 import_shutong_cookies.py /path/to/cookies_shutong.txt

    # Test proxy connectivity without importing:
    python3 import_shutong_cookies.py --test-only

    # Show current cookie status:
    python3 import_shutong_cookies.py --status
"""
import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("shutong")

BASE = Path(__file__).parent
COOKIE_JAR = BASE / ".shutong_cookies.json"
COOKIE_JAR_LEGACY = BASE / ".cnki_cookies.json"  # fallback


def parse_netscape_cookie_file(filepath: str) -> list[dict]:
    """Parse Netscape HTTP cookie file format."""
    cookies = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("HttpOnly"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0]
                # flag = parts[1]  # TRUE/FALSE
                path = parts[2]
                secure = parts[3].upper() == "TRUE"
                expires = parts[4]
                name = parts[5]
                value = parts[6]
                cookies.append({
                    "domain": domain,
                    "path": path,
                    "secure": secure,
                    "expires": expires,
                    "name": name,
                    "value": value,
                })
    return cookies


def extract_shutong_cookies(cookies: list[dict]) -> dict[str, str]:
    """Extract 书童 session cookies from parsed cookie list."""
    important_names = {
        "yiffamlusername", "yiffamluserid", "yiffamlgroupid",
        "yiffamlrnd", "yiffamlauth", "acw_tc", "UM_distinctid",
    }
    result = {}
    for c in cookies:
        domain = c["domain"].lstrip(".")
        if "shutong2" in domain and c["name"] in important_names:
            result[c["name"]] = c["value"]
        elif "wvpn.sjlib" in domain:
            result.setdefault("_wvpn_cookies", {})
            result["_wvpn_cookies"][c["name"]] = c["value"]
    return result


def parse_flat_cookies(cookies: list[dict]) -> dict[str, str]:
    """Convert parsed cookies to flat {name: value} dict (all domains)."""
    flat = {}
    for c in cookies:
        flat[c["name"]] = c["value"]
    return flat


def save_shutong_cookies(cookies: dict):
    """Save 书童 cookies to persistent file."""
    COOKIE_JAR.write_text(
        json.dumps({"cookies": cookies, "imported_at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n"
    )
    log.info(f"Saved {len(cookies)} cookies to {COOKIE_JAR.name}")


def load_shutong_cookies() -> dict[str, str]:
    """Load 书童 cookies from persistent file."""
    if COOKIE_JAR.exists():
        try:
            data = json.loads(COOKIE_JAR.read_text())
            return data.get("cookies", {})
        except Exception:
            pass
    return {}


def test_proxy_connectivity(cookies: dict) -> bool:
    """Test if the 书童 proxy works by trying to access it with cookies."""
    import urllib.request

    if not cookies:
        log.error("No cookies to test with")
        return False

    # Prepare cookie header
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())

    # Test 1: access the main page
    url = "http://3.shutong2.com/"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": cookie_header,
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
        if "095195923" in html or "VIP" in html:
            log.info("Test 1 OK: main page shows logged-in status")
        else:
            log.warning("Test 1: main page loaded but login status not confirmed")
    except Exception as e:
        log.error(f"Test 1 FAILED: main page access error: {e}")
        return False

    # Test 2: access api33.php (triggers redirect to CNKI proxy)
    # First check if we need a referer
    url2 = "http://3.shutong2.com/api33.php"
    req2 = urllib.request.Request(url2, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": cookie_header,
        "Referer": "http://3.shutong2.com/zhongwenku/",
    })
    try:
        resp2 = urllib.request.urlopen(req2, timeout=30)
        final_url = resp2.url
        html2 = resp2.read().decode("utf-8", errors="replace")
        log.info(f"Test 2: api33.php redirected to {final_url[:100]}")
        if "wvpn.sjlib" in final_url or "cnki" in final_url.lower():
            log.info("Test 2 OK: proxy redirect working")
        elif "shutong2" in final_url:
            log.warning("Test 2: no redirect happened (may need fresh login)")
            return False
    except Exception as e:
        log.error(f"Test 2 FAILED: {e}")
        return False

    # Test 3: try direct CNKI search via proxy (if cookies include wvpn session)
    wvpn_cookies = {k: v for k, v in cookies.items() if "sjlib" in str(k) or "wvpn" in str(k)}
    if wvpn_cookies:
        wvpn_header = "; ".join(f"{k}={v}" for k, v in wvpn_cookies.items())
        search_url = "https://kns-cnki-net-443.wvpn.sjlib.cn/kns8s/DefaultResult/Index"
        req3 = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": wvpn_header,
        })
        try:
            resp3 = urllib.request.urlopen(req3, timeout=15)
            if resp3.status == 200:
                log.info("Test 3 OK: direct proxy access works")
                return True
        except Exception as e:
            log.warning(f"Test 3: direct proxy access failed (expected, may need PHP gateway): {e}")
            # This is OK - the PHP gateway may be required

    return True


def show_status():
    """Show current 书童 cookie status."""
    cookies = load_shutong_cookies()
    if not cookies:
        log.info("No 书童 cookies configured")
        return

    log.info(f"Cookie file: {COOKIE_JAR}")
    log.info(f"Total cookies: {len(cookies)}")
    for name, value in sorted(cookies.items()):
        log.info(f"  {name}={value[:30]}...")

    # Check expiry from username cookie
    import urllib.request
    try:
        req = urllib.request.Request("http://3.shutong2.com/", headers={
            "User-Agent": "Mozilla/5.0",
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")
        match = re.search(r'剩余天数[：:]\s*(\d+)', html)
        if match:
            log.info(f"VIP剩余天数: {match.group(1)}天")
        else:
            log.info("VIP info not found on main page (may need re-login)")
    except Exception as e:
        log.error(f"Status check failed: {e}")


def integrate_with_config():
    """Create a config flag indicating 书童 proxy is available."""
    cfg_file = BASE / ".shutong_enabled"
    cfg_file.write_text("1\n")
    log.info(f"书童 proxy enabled flag written to {cfg_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Import 书童 proxy cookies for CNKI access")
    parser.add_argument("cookie_file", nargs="?", help="Path to Netscape-format cookies.txt")
    parser.add_argument("--test-only", action="store_true", help="Test proxy connectivity only")
    parser.add_argument("--status", action="store_true", help="Show current cookie status")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.test_only:
        cookies = load_shutong_cookies()
        if not cookies:
            log.error("No cookies found. Run the import script with a cookie file first.")
            sys.exit(1)
        log.info("Testing 书童 proxy connectivity...")
        ok = test_proxy_connectivity(cookies)
        if ok:
            log.info("Proxy OK:书童代理可用")
            integrate_with_config()
        else:
            log.error("Proxy FAILED:需要重新导出 cookies")
        return

    cookie_file = args.cookie_file
    if not cookie_file:
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(cookie_file):
        log.error(f"File not found: {cookie_file}")
        sys.exit(1)

    # Parse cookies
    raw_cookies = parse_netscape_cookie_file(cookie_file)
    log.info(f"Parsed {len(raw_cookies)} cookies from {cookie_file}")

    # Extract 书童 cookies
    shutong_data = extract_shutong_cookies(raw_cookies)
    flat = parse_flat_cookies(raw_cookies)

    if not any("yiffamlauth" in k or "yiffamluserid" in k for k in flat):
        log.warning("No 书童 session cookies found! Make sure you exported cookies AFTER logging in.")
        log.info("Found domains in file: " + ", ".join(set(c["domain"] for c in raw_cookies)))
        # Try all cookies anyway
        if flat:
            log.info(f"Using all {len(flat)} cookies from export")
            save_shutong_cookies(flat)
        else:
            sys.exit(1)
    else:
        log.info(f"Found 书童 session cookies: {[k for k in flat if 'yiffaml' in k]}")
        save_shutong_cookies(flat)

    # Test connectivity
    log.info("\nTesting proxy connectivity...")
    ok = test_proxy_connectivity(flat)
    if ok:
        integrate_with_config()
        log.info("\n✓ 书童代理配置成功！")
        log.info("  现在可以运行 backfill_cnki_fulltext.py --shutong 来回填全文了")
    else:
        log.error("\n✗ 代理测试失败，请检查 cookie 是否已过期")


if __name__ == "__main__":
    main()
