"""
MCP (Model Context Protocol) server for news-monitor.
Exposes read-only tools for AI clients to query the article database.

Usage:
    python3 main.py mcp           # stdio mode (Claude Desktop)
    python3 main.py mcp --sse     # SSE mode (web)
"""
import logging
import sqlite3

from mcp.server import FastMCP

import config
from theme import NEWS, AAM

THEMES = {"news": NEWS, "aam": AAM}

log = logging.getLogger("news-monitor.mcp")

mcp = FastMCP("news-monitor", log_level="WARNING")


def _get_conn(theme: str) -> sqlite3.Connection:
    """Get a database connection for the given theme."""
    t = THEMES.get(theme)
    if not t:
        raise ValueError(f"Unknown theme: {theme}. Options: {', '.join(THEMES.keys())}")
    db_path = config.BASE_DIR / "data" / f"{t.db_name}.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def get_latest_articles(theme: str = "news", limit: int = 10) -> str:
    """Get the latest N articles for a theme.

    Args:
        theme: Theme name ('news' for 航天动力, 'aam' for 空空导弹)
        limit: Number of articles to return (max 50)
    """
    conn = _get_conn(theme)
    try:
        rows = conn.execute(
            "SELECT id, title, translated_title, source, published, "
            "       article_type, relevance, matched_kw "
            "FROM articles ORDER BY published DESC LIMIT ?",
            (min(limit, 50),),
        ).fetchall()
        if not rows:
            return "暂无文章"
        lines = [f"找到 {len(rows)} 篇文章："]
        for r in rows:
            title = r["translated_title"] or r["title"]
            pub = (r["published"] or "")[:10]
            kw = r["matched_kw"] or ""
            lines.append(f"- [{r['article_type']}] {title} ({r['source']}, {pub}) 相关度:{r['relevance']} 关键词:{kw[:60]}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def search_articles(theme: str = "news", query: str = "", limit: int = 20) -> str:
    """Search articles by keyword across title, summary, and content.

    Args:
        theme: Theme name ('news' or 'aam')
        query: Search keyword
        limit: Max results (max 50)
    """
    if not query:
        return "请提供搜索关键词"
    conn = _get_conn(theme)
    try:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT id, title, translated_title, source, published, relevance "
            "FROM articles WHERE title LIKE ? OR summary LIKE ? "
            "OR translated_title LIKE ? OR translated_summary LIKE ? "
            "OR content LIKE ? OR translated_content LIKE ? "
            "ORDER BY published DESC LIMIT ?",
            (like,) * 6 + (min(limit, 50),),
        ).fetchall()
        if not rows:
            return f"未找到包含「{query}」的文章"
        lines = [f"搜索「{query}」找到 {len(rows)} 篇："]
        for r in rows:
            title = r["translated_title"] or r["title"]
            pub = (r["published"] or "")[:10]
            lines.append(f"- {title} ({r['source']}, {pub}) 相关度:{r['relevance']}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_article(theme: str = "news", article_id: str = "") -> str:
    """Get full details of a specific article by ID.

    Args:
        theme: Theme name ('news' or 'aam')
        article_id: Article ID (the 24-character hex string)
    """
    if not article_id:
        return "请提供文章 ID"
    conn = _get_conn(theme)
    try:
        row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        if not row:
            return f"未找到 ID 为 {article_id} 的文章"
        title = row["translated_title"] or row["title"]
        summary = row["translated_summary"] or row["summary"]
        content = row["translated_content"] or row["content"] or ""
        kw = row["matched_kw"] or ""
        lines = [
            f"标题: {title}",
            f"原文标题: {row['title']}",
            f"来源: {row['source']}",
            f"发布时间: {row['published'] or '?'}",
            f"类型: {row['article_type'] or 'news'}",
            f"相关度: {row['relevance']}/100",
            f"AI 评分: {row['llm_relevance']//10 if row['llm_relevance'] else '未评分'}/10",
            f"关键词: {kw}",
            f"作者: {row['author'] or '未知'}",
            f"机构: {row['affiliation'] or '未知'}",
            f"URL: {row['url']}",
            f"",
            f"摘要: {summary[:500]}",
        ]
        if content:
            lines.extend(["", f"正文({len(content)}字):", content[:2000]])
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_stats(theme: str = "news") -> str:
    """Get database statistics for a theme.

    Args:
        theme: Theme name ('news' or 'aam')
    """
    conn = _get_conn(theme)
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        h24 = conn.execute("SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-1 day')").fetchone()[0]
        paper = conn.execute("SELECT COUNT(*) FROM articles WHERE article_type='paper'").fetchone()[0]
        patent = conn.execute("SELECT COUNT(*) FROM articles WHERE article_type='patent'").fetchone()[0]
        news_cnt = total - paper - patent
        last_poll = conn.execute(
            "SELECT started_at, duration_sec, articles_found FROM poll_stats ORDER BY id DESC LIMIT 1"
        ).fetchone()
        lines = [
            f"主题: {theme}",
            f"文章总数: {total}",
            f"最近24小时: {h24}",
            f"论文: {paper}",
            f"新闻: {news_cnt}",
            f"专利: {patent}",
        ]
        if last_poll:
            lines.append(f"上次采集: {last_poll['started_at'][:19]} ({last_poll['duration_sec']}秒, {last_poll['articles_found']}篇)")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_source_status(theme: str = "news") -> str:
    """Show the latest fetch status for all RSS sources of a theme.

    Args:
        theme: Theme name ('news' or 'aam')
    """
    conn = _get_conn(theme)
    try:
        rows = conn.execute("""
            SELECT s.source_name, s.success, s.articles_found, s.error_msg
            FROM source_stats s
            WHERE s.id IN (SELECT MAX(id) FROM source_stats GROUP BY source_name)
            ORDER BY s.source_name
        """).fetchall()
        if not rows:
            return "暂无采集记录"
        ok = sum(1 for r in rows if r["success"])
        fail = sum(1 for r in rows if not r["success"])
        lines = [f"数据源状态: {ok} 正常 / {fail} 异常 (共 {len(rows)} 源)"]
        for r in rows:
            icon = "✅" if r["success"] else "❌"
            articles = r["articles_found"]
            err = f" - {r['error_msg'][:50]}" if not r["success"] and r["error_msg"] else ""
            lines.append(f"{icon} {r['source_name']} ({articles}篇){err}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_keyword_trend(keyword: str = "", days: int = 30) -> str:
    """Show daily article count trend for a keyword across all themes.

    Args:
        keyword: The keyword to check
        days: Number of days to look back
    """
    if not keyword:
        return "请提供关键词"
    results = []
    for theme in ("news", "aam"):
        conn = _get_conn(theme)
        try:
            rows = conn.execute(
                "SELECT DATE(published) as day, COUNT(*) as cnt FROM articles "
                "WHERE published >= datetime('now', ? || ' days') "
                "AND matched_kw LIKE ? GROUP BY day ORDER BY day",
                (f"-{days}", f"%{keyword}%"),
            ).fetchall()
            if rows:
                total = sum(r["cnt"] for r in rows)
                results.append(f"[{theme}] 关键词「{keyword}」近{days}天出现 {total} 次")
                for r in rows[-14:]:  # show last 14 days
                    results.append(f"  {r['day']}: {r['cnt']}篇")
        finally:
            conn.close()
    if not results:
        return f"未找到关键词「{keyword}」的趋势数据"
    return "\n".join(results)


def main(transport: str = "stdio"):
    """Run the MCP server with the given transport."""
    log.info(f"Starting MCP server ({transport} transport)...")
    mcp.run(transport=transport)
