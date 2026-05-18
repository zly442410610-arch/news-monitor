#!/usr/bin/env python3
"""
Domestic news collector — deploy on a Chinese server to collect Chinese
aerospace/news and push to the main server.

Usage:
    python3 collector.py              # Run one cycle (push to main server)
    python3 collector.py --daemon     # Run continuously
    python3 collector.py --dry-run    # Test fetching without sending

Config via environment variables:
    MAIN_SERVER_URL  (default: http://47.103.207.227:80)
    COLLECTOR_API_KEY (shared secret with main server)
"""
import hashlib
import logging
import os
import time
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("collector")

# ── Config ────────────────────────────────────────────────────────────────

MAIN_SERVER = os.environ.get("MAIN_SERVER_URL", "http://47.103.207.227:80")
API_KEY = os.environ.get("COLLECTOR_API_KEY", "default-key")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))  # minutes

# ── Chinese RSS Sources ───────────────────────────────────────────────────
# These sources are ONLY accessible from within China.
# Add/remove as needed — edit this file directly on the domestic server.
RSS_SOURCES = {
    # 国防/军事新闻
    "观察者网军事": "https://user.guancha.cn/rss/military.xml",
    "凤凰网军事": "https://news.ifeng.com/rss/military.xml",
    "环球网军事": "https://mil.huanqiu.com/rss.xml",
    # 航天/科技
    "航天科技集团": "https://www.spacechina.com/rss/news.xml",
    "cnBeta": "https://www.cnbeta.com/rss",
    "澎湃新闻": "https://www.thepaper.cn/rss/news.xml",
    # 搜索引擎搜索
    "Baidu News - 固体火箭": "https://news.baidu.com/ns?word=固体火箭发动机&tn=newsrss&ie=utf-8",
    "Baidu News - 冲压": "https://news.baidu.com/ns?word=冲压发动机&tn=newsrss&ie=utf-8",
    "Baidu News - 高超声速": "https://news.baidu.com/ns?word=高超声速推进&tn=newsrss&ie=utf-8",
    "Sogou News - 固体火箭": "https://news.sogou.com/news?query=固体火箭发动机&rss=1",
    "Sogou News - 冲压": "https://news.sogou.com/news?query=冲压发动机&rss=1",
    # Extended keyword feeds
    "Baidu News - 高超声速导弹": "https://news.baidu.com/ns?word=高超声速导弹&tn=newsrss&ie=utf-8",
    "Baidu News - 火箭发动机": "https://news.baidu.com/ns?word=火箭发动机&tn=newsrss&ie=utf-8",
    "Baidu News - 导弹推进": "https://news.baidu.com/ns?word=导弹推进技术&tn=newsrss&ie=utf-8",
    "Baidu News - 固体推进剂": "https://news.baidu.com/ns?word=固体推进剂&tn=newsrss&ie=utf-8",
    "Sogou News - 高超声速": "https://news.sogou.com/news?query=高超声速&rss=1",
    "Sogou News - 火箭发动机": "https://news.sogou.com/news?query=火箭发动机&rss=1",
}

# ── Keywords matching the main server's focus ─────────────────────────────
KEYWORDS = [
    # Core solid rocket terms
    "固体火箭发动机", "固体推进剂", "固体发动机", "固体火箭",
    "固体助推器", "固体燃料", "固体火箭试车",
    "HTPB", "复合推进剂", "GEM-63", "GEM63",
    # Core ramjet terms
    "冲压发动机", "超燃冲压", "超燃冲压发动机",
    "亚燃冲压", "冲压", "高超声速推进",
    # Broad terms
    "火箭发动机", "发动机试车", "火箭试车",
    "高超声速", "高超音速导弹",
    "弹道导弹", "巡航导弹",
    "推进系统", "导弹推进",
    # Related organizations/projects
    "国防科大", "航天科技", "航天科工",
    "火箭军", "导弹试验",
]

# ── Patent search keywords ─────────────────────────────────────────────────
PATENT_KEYWORDS = [
    "solid rocket motor",
    "solid propellant",
    "ramjet",
    "scramjet",
    "hypersonic propulsion",
    "ducted rocket",
    "solid rocket booster",
]


# ── Functions ─────────────────────────────────────────────────────────────


def keyword_match(text: str) -> list[str]:
    text_lower = text.lower()
    matched = []
    for kw in KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw)
    return matched


def make_article_id(url: str, title: str) -> str:
    raw = f"{url}#{title[:100].lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def fetch_rss(url: str) -> list[dict]:
    entries = []
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            log.warning(f"Parse error: {url[:50]}...")
            return entries
        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            if summary:
                summary = BeautifulSoup(summary, "lxml").get_text(separator=" ", strip=True)[:2000]
            if title and link:
                entries.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "published": entry.get("published", ""),
                    "source": url,
                })
        log.info(f"Fetched {len(entries)} from {url[:50]}...")
    except Exception as e:
        log.error(f"Fetch error {url[:50]}: {e}")
    return entries


# ── Patent Search (Google Patents) ───────────────────────────────────────


def search_patents() -> list[dict]:
    """Search Google Patents for recent propulsion-related patents."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }
    results = []
    seen = set()

    for kw in PATENT_KEYWORDS:
        url = f"https://patents.google.com/?q={kw}&num=10&sort=newest&hl=en"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                log.warning(f"Patent search failed ({kw[:30]}): HTTP {r.status_code}")
                continue

            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select("article") or soup.find_all("div", class_="result-item")

            for item in items[:10]:
                # Title
                title_el = item.find("h4") or item.find("h3")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)[:200]
                if not title:
                    continue

                # URL
                link_el = item.find("a") or title_el.find("a")
                link = ""
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    link = f"https://patents.google.com{href}" if href.startswith("/") else href

                # Abstract/summary
                abs_el = item.find("div", class_="abstract") or item.find("p")
                summary = abs_el.get_text(strip=True)[:1000] if abs_el else ""

                # Deduplicate by title
                key = title[:80].lower().strip()
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "title": f"[专利] {title}",
                    "url": link or f"https://patents.google.com/?q={kw}&num=1",
                    "summary": summary or f"Patent related to {kw}",
                    "published": "",
                    "source": f"Google Patents - {kw}",
                    "matched_kw": kw,
                    "relevance": 70,
                })

            log.info(f"Patent search '{kw[:30]}': {len(items)} results")
        except Exception as e:
            log.error(f"Patent search error ({kw[:30]}): {e}")

    log.info(f"Patent search complete. {len(results)} unique patents found.")
    return results


def search_patents_patentsview() -> list[dict]:
    """Search USPTO PatentsView API for recent propulsion-related patents.

    Uses CPC classification codes (no API key required):
    - F02K: Jet-propulsion plants (rocket engines, ramjets, scramjets)
    - B64G: Cosmonautics/space vehicles
    """
    results = []
    seen = set()

    # CPC classes relevant to propulsion
    cpc_queries = [
        {"cpc_subclass_id": "F02K"},
        {"cpc_subclass_id": "B64G"},
    ]

    fields = [
        "patent_number", "patent_title", "patent_date",
        "patent_abstract", "cpc_subclass_id"
    ]

    for cpc in cpc_queries:
        cls = cpc["cpc_subclass_id"]
        params = {
            "q": cpc,
            "f": fields,
            "o": {"per_page": 15, "sort": "patent_date desc"},
        }
        url = "https://patentsview.org/api/patents/query"
        try:
            r = requests.post(url, json=params, timeout=15)
            if r.status_code != 200:
                log.warning(f"PatentsView search failed (CPC {cls}): HTTP {r.status_code}")
                continue

            data = r.json()
            patents = data.get("patents", [])
            for p in patents:
                title = (p.get("patent_title") or "").strip()
                if not title:
                    continue

                # Deduplicate
                key = title[:80].lower().strip()
                if key in seen:
                    continue
                seen.add(key)

                abstract = (p.get("patent_abstract") or "")[:1000]
                patent_no = p.get("patent_number", "")
                patent_date = p.get("patent_date", "")
                # Match against patent keywords to set relevance
                matched = []
                for kw in PATENT_KEYWORDS:
                    if kw.lower() in title.lower() or kw.lower() in abstract.lower():
                        matched.append(kw)

                relevance = 60 + min(len(matched) * 10, 40) if matched else 50
                match_str = ", ".join(matched) if matched else cls

                results.append({
                    "title": f"[专利] {title}",
                    "url": f"https://patents.google.com/patent/US{patent_no}/en" if patent_no else "",
                    "summary": abstract or f"USPTO patent {patent_no} in CPC class {cls}",
                    "published": patent_date,
                    "source": f"USPTO PatentsView - {cls}",
                    "matched_kw": match_str,
                    "relevance": relevance,
                })

            log.info(f"PatentsView CPC {cls}: {len(patents)} results")
        except Exception as e:
            log.error(f"PatentsView search error (CPC {cls}): {e}")

    log.info(f"PatentsView search complete. {len(results)} unique patents.")
    return results


def push_articles(articles: list[dict]) -> int:
    """Push collected articles to the main server. Returns count of saved articles."""
    if not articles:
        return 0

    payload = {
        "api_key": API_KEY,
        "articles": [
            {
                "title": a["title"],
                "url": a["url"],
                "summary": a.get("summary", ""),
                "published": a.get("published", ""),
                "source": a.get("source", "国内采集"),
                "matched_kw": a.get("matched_kw", ""),
                "relevance": a.get("relevance", 0),
            }
            for a in articles
        ],
    }

    try:
        r = requests.post(
            f"{MAIN_SERVER}/api/collect",
            json=payload,
            headers={"User-Agent": "news-collector/1.0"},
            timeout=15,
        )
        if r.status_code == 200:
            result = r.json()
            log.info(f"Pushed {len(articles)} articles, saved {result.get('saved', 0)} new")
            return result.get("saved", 0)
        else:
            log.warning(f"Push failed: HTTP {r.status_code} {r.text[:100]}")
            return 0
    except Exception as e:
        log.error(f"Push error: {e}")
        return 0


def collect() -> list[dict]:
    """Run one collection cycle. Returns list of matched articles + patents."""
    all_matched = []
    for source_name, url in RSS_SOURCES.items():
        entries = fetch_rss(url)
        for entry in entries:
            matched = keyword_match(f"{entry['title']} {entry['summary']}")
            if matched:
                entry["matched_kw"] = ", ".join(matched)
                entry["relevance"] = min(len(matched) * 20, 100)
                entry["source"] = source_name
                all_matched.append(entry)
                log.info(f"[{source_name}] {entry['title'][:60]} → matched: {matched}")

    # Also search for patents (Google Patents)
    patents = search_patents()
    all_matched.extend(patents)
    for p in patents:
        log.info(f"[Google Patent] {p['title'][:60]}")

    # Additional patent search via USPTO PatentsView API (free, no key)
    patents_pv = search_patents_patentsview()
    all_matched.extend(patents_pv)
    for p in patents_pv:
        log.info(f"[PatentsView] {p['title'][:60]}")

    log.info(f"Collection cycle complete. {len(all_matched)} matched articles/patents.")
    return all_matched


def run(dry_run=False):
    log.info(f"=== Collector cycle starting (server={MAIN_SERVER}) ===")
    articles = collect()
    if not dry_run and articles:
        push_articles(articles)
    log.info(f"=== Cycle complete ===")
    return articles


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    daemon = "--daemon" in sys.argv

    if daemon:
        log.info(f"Daemon mode: polling every {POLL_INTERVAL} minutes")
        while True:
            run(dry_run=False)
            time.sleep(POLL_INTERVAL * 60)
    else:
        run(dry_run=dry_run)
