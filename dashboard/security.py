"""Dashboard security module: real-time malicious access detection and IP blocking.

Monitors incoming requests, detects scanning/cracking patterns,
and automatically bans offending IPs via the 10200 monitor API.
"""
import os
import time
import json
import logging
import urllib.request
import urllib.error

log = logging.getLogger("dashboard-security")

# ── Suspicious path patterns ────────────────────────────────────────
SUSPICIOUS_PATHS = [
    "/wp-admin", "/wp-login", "/wp-content", "/wp-includes",
    "/admin", "/admin/", "/administrator",
    "/manager", "/manage", "/management",
    "/phpmyadmin", "/phpMyAdmin", "/pma",
    "/mysql", "/mysql-admin",
    "/shell", "/cmd", "/exec", "/backdoor",
    "/config", "/configuration", "/config.php",
    "/backup", "/backups", "/db_backup",
    "/.env", "/env",
    "/.git", "/.svn",
    "/xmlrpc.php", "/xmlrpc",
    "/cgi-bin", "/cgi-bin/",
    "/server-status", "/server-info",
    "/webdav", "/actuator",
    "/solr", "/jboss", "/weblogic",
    "/api/docs", "/api/swagger",
    "/graphql", "/graph",
    "/actuator/", "/actuator",
    "/vendor/", "/storage/",
    "/debug", "/test", "/tests",
    "/proxy", "/proxy/",
    "/remote/", "/upload",
    "/api/ban-ip", "/api/unban-ip",  # scanning for ban API
    "/docker", "/k8s", "/kubernetes",
    "/console", "/panel",
    "/index.php", "=phpmyadmin",
]

# Case-insensitive substring checks for suspicious query strings/bodies
SUSPICIOUS_QUERIES = [
    "union+select", "union select",
    "select+from", "select from",
    "drop+table", "drop table",
    "delete+from", "delete from",
    "insert+into", "insert into",
    "../", "..\\",
    "../../", "..\\..\\",
    "passwd", "/etc/",
    "cmd=", "exec=",
    "ping=", "nslookup=",
    "wget ", "curl ",
    "base64_decode",
    "eval(", "system(",
    "phpinfo()",
    "<script", "alert(",
    "../../../",
    ".jsp", ".do?", ".action?",
]


class SecurityMonitor:
    """Per-IP request monitoring and auto-blocking."""

    def __init__(self, ban_api_url: str = "http://127.0.0.1:10200/api/ban-ip",
                 api_key: str = ""):
        self._ban_api_url = ban_api_url
        self._api_key = api_key or os.environ.get("BAN_API_KEY", "")

        # IP -> {"count": int, "first_seen": float, "last_seen": float,
        #        "suspicious_hits": int, "paths": list[str]}
        self._ip_tracker: dict[str, dict] = {}

        # Configurable thresholds
        self._rate_limit = 300          # max requests in window
        self._rate_window = 60          # seconds
        self._suspicious_threshold = 5  # suspicious paths before ban
        self._ban_cooldown = 300        # don't re-ban same IP within seconds

        # Recently banned IPs (cooldown cache)
        self._banned_cache: dict[str, float] = {}

        # Cleanup interval (last cleanup time)
        self._last_cleanup = time.time()

    # ── Localhost / private IPs that should never be banned ────
    _TRUSTED_IPS = frozenset(["127.0.0.1", "::1", "localhost", "0.0.0.0"])

    def check(self, ip: str, path: str, user_agent: str = "",
              query: str = "", body: str = "") -> bool:
        """Check if request is suspicious. Returns True if deemed safe.

        If suspicious patterns detected, auto-bans the IP.
        """
        # Skip tracking/banning for trusted local IPs
        if ip in self._TRUSTED_IPS:
            return True

        now = time.time()

        # Periodic cleanup of stale tracker entries
        if now - self._last_cleanup > 300:
            self._cleanup(now)

        # Initialize or update IP tracking
        if ip not in self._ip_tracker:
            self._ip_tracker[ip] = {
                "count": 0,
                "first_seen": now,
                "last_seen": now,
                "suspicious_hits": 0,
                "paths": [],
            }
        info = self._ip_tracker[ip]
        info["count"] += 1
        info["last_seen"] = now

        # Rate limiting check
        elapsed = now - info["first_seen"]
        if elapsed < self._rate_window and info["count"] > self._rate_limit:
            log.warning(f"IP {ip} 请求频率过高 ({info['count']}/{elapsed:.0f}s)，自动封禁")
            self._ban_ip(ip, f"请求频率过高: {info['count']}次/{elapsed:.0f}秒")
            return False

        # Check for suspicious path patterns
        path_lower = path.lower()
        for pattern in SUSPICIOUS_PATHS:
            if pattern in path_lower:
                info["suspicious_hits"] += 1
                info["paths"].append(path[:100])
                log.info(f"IP {ip} 访问可疑路径: {path}")
                if info["suspicious_hits"] >= self._suspicious_threshold:
                    paths_str = ", ".join(info["paths"][-10:])
                    self._ban_ip(ip, f"扫描/破解路径: {paths_str}")
                    return False
                return True  # Still safe but tracked

        # Check for suspicious query strings
        query_lower = (query or "").lower()
        body_lower = (body or "").lower()
        combined = f"{query_lower} {body_lower}"
        for sq in SUSPICIOUS_QUERIES:
            if sq in combined:
                info["suspicious_hits"] += 1
                info["paths"].append(f"{path}?{query[:50]}")
                log.info(f"IP {ip} 可疑查询: {path}?{query[:100]}")
                if info["suspicious_hits"] >= max(1, self._suspicious_threshold - 2):
                    self._ban_ip(ip, f"SQL注入/XSS扫描: {query[:100]}")
                    return False
                return True

        # Check for known bad user-agents (scanner tools)
        ua_lower = user_agent.lower()
        bad_ua = ["sqlmap", "nikto", "nmap", "masscan", "zgrab",
                   "acunetix", "nessus", "openvas", "nutch",
                   "go-http-client", "python-requests", "python-urllib",
                   "curl/", "wget/"]
        for bua in bad_ua:
            if bua in ua_lower:
                info["suspicious_hits"] += 1
                log.info(f"IP {ip} 扫描工具 User-Agent: {user_agent[:80]}")
                if info["suspicious_hits"] >= 2:
                    self._ban_ip(ip, f"扫描工具: {user_agent[:80]}")
                    return False
                return True

        return True

    def _ban_ip(self, ip: str, reason: str):
        """Send ban request to the 10200 monitor API."""
        now = time.time()

        # Cooldown check — don't spam the API for the same IP
        if ip in self._banned_cache:
            if now - self._banned_cache[ip] < self._ban_cooldown:
                return
        self._banned_cache[ip] = now

        if not self._api_key:
            log.warning(f"BAN_API_KEY 未设置，无法自动封禁 IP {ip}")
            return

        payload = json.dumps({
            "ip": ip,
            "reason": reason,
            "method": "dashboard-auto",
        }).encode("utf-8")

        req = urllib.request.Request(
            self._ban_api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self._api_key,
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            log.warning(f"✓ IP {ip} 已自动封禁: {reason}")
        except urllib.error.HTTPError as e:
            log.error(f"封禁 IP {ip} 失败 (HTTP {e.code}): {e.read().decode()[:200]}")
        except Exception as e:
            log.error(f"封禁 IP {ip} 失败: {e}")

    def _cleanup(self, now: float):
        """Remove stale entries from IP tracker."""
        stale = []
        for ip, info in self._ip_tracker.items():
            if now - info["last_seen"] > 3600:  # 1h idle
                stale.append(ip)
        for ip in stale:
            del self._ip_tracker[ip]

        # Also cleanup old banned cache entries
        stale_banned = []
        for ip, ts in self._banned_cache.items():
            if now - ts > 3600:
                stale_banned.append(ip)
        for ip in stale_banned:
            del self._banned_cache[ip]

        self._last_cleanup = now
        log.debug(f"安全监控: 清理 {len(stale)} 个过期 IP 记录, "
                  f"{len(self._ip_tracker)} 个活跃跟踪")


# Global singleton
_SECURITY = None


def get_monitor() -> SecurityMonitor:
    """Get or create the global security monitor singleton."""
    global _SECURITY
    if _SECURITY is None:
        api_key = os.environ.get("BAN_API_KEY", "")
        _SECURITY = SecurityMonitor(api_key=api_key)
        log.info(f"安全监控初始化完成 (API key {'已设置' if api_key else '未设置'})")
    return _SECURITY
