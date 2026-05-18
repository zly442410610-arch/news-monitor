#!/usr/bin/env python3
"""
Weekly briefing generator for the news monitor.
Collects articles from the past 7 days, generates a Chinese briefing using LLM,
and saves/notifies.
"""
import json
import logging
from datetime import datetime, timezone

import config
from monitor import init_db, get_articles_for_briefing

log = logging.getLogger(f"{config.LOGGER_NAME}.briefing")


def _get_llm_text(resp) -> str:
    """Extract text from Anthropic response, handling thinking blocks."""
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text.strip()
    return ""


def generate_briefing_text(articles: list[dict]) -> str:
    """
    Generate a Chinese-language briefing from a list of articles using LLM.
    Returns the briefing text as a string.
    """
    if not articles:
        return "本周暂无相关新闻。"

    # Format articles for the LLM prompt
    article_lines = []
    for i, a in enumerate(articles, 1):
        title = a.get("translated_title") or a["title"]
        summary = a.get("translated_summary") or a.get("summary", "")
        source = a.get("source", "")
        published = (a.get("published") or "")[:16]
        url = a.get("url", "")
        kw = a.get("matched_kw", "")
        article_lines.append(
            f"[Article {i}]\n"
            f"Title: {title}\n"
            f"Source: {source} | {published}\n"
            f"Summary: {summary[:500]}\n"
            f"Keywords: {kw}\n"
            f"URL: {url}\n"
        )

    articles_text = "\n---\n".join(article_lines)
    prompt = f"{config.BRIEFING_PROMPT}\n\n{articles_text}"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
        resp = client.messages.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        briefing = _get_llm_text(resp)
        if not briefing:
            log.warning("Empty briefing from LLM")
            return _generate_fallback_briefing(articles)
        return briefing
    except Exception as e:
        log.error(f"Briefing generation failed: {e}")
        return _generate_fallback_briefing(articles)


def _generate_fallback_briefing(articles: list[dict]) -> str:
    """Generate a simple text-based briefing without LLM."""
    lines = [f"{config.FALLBACK_BRIEFING_TITLE}\n", f"生成时间: {datetime.now(timezone.utc).isoformat()[:16]}\n"]
    lines.append(f"本周收录: {len(articles)} 篇文章\n\n---\n")

    for i, a in enumerate(articles, 1):
        title = a.get("translated_title") or a["title"]
        source = a.get("source", "")
        published = (a.get("published") or "")[:16]
        url = a.get("url", "")
        lines.append(f"### {i}. {title}")
        lines.append(f"来源: {source} | {published}")
        lines.append(f"链接: {url}\n")

    return "\n".join(lines)


def save_briefing(text: str) -> str:
    """Save briefing to file. Returns file path."""
    config.BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    week_num = now.isocalendar()[1]
    filename = f"briefing-{now.year}-week{week_num}-{now.strftime('%Y%m%d')}.md"
    path = config.BRIEFING_DIR / filename
    path.write_text(text, encoding="utf-8")
    log.info(f"Briefing saved to {path}")
    return str(path)


def run(days=7, notify=True) -> str:
    """
    Generate weekly briefing. Returns briefing text.

    Steps:
    1. Query articles from the past N days from DB
    2. Generate summary using LLM (or fallback format)
    3. Save to file
    4. Notify via configured channels
    """
    conn = init_db()
    try:
        articles = get_articles_for_briefing(conn, days=days)
        log.info(f"Briefing: {len(articles)} articles from last {days} days")

        if not articles:
            msg = f"过去 {days} 天内没有收录到相关新闻。"
            log.info(msg)
            return msg

        text = generate_briefing_text(articles)
        filepath = save_briefing(text)

        # Notify
        if notify:
            try:
                from notifier import notify_briefing
                notify_briefing(text)
            except Exception as e:
                log.warning(f"Briefing notification failed: {e}")

        log.info(f"Briefing generated: {len(text)} chars → {filepath}")
        return text
    finally:
        conn.close()
