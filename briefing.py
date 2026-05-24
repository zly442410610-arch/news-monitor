#!/usr/bin/env python3
"""
Weekly briefing generator and monthly research survey generator for the news monitor.
Collects articles, generates Chinese briefing or research-survey report using LLM,
and saves/notifies.
"""
import json
import logging
import re
from datetime import datetime, timezone

import config
from monitor import init_db, get_articles_for_briefing

log = logging.getLogger(f"{config.LOGGER_NAME}.briefing")


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
        from llm_client import create_completion
        briefing = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
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


def md_to_html(md: str) -> str:
    """Convert basic Markdown (headings, bold, italic, links, lists) to HTML."""
    lines = md.split("\n")
    out: list[str] = []
    in_list = False

    for line in lines:
        # Horizontal rule
        if re.match(r"^---+$", line.strip()):
            out.append("<hr>")
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            out.append(f"<h{level}>{text}</h{level}>")
            continue

        # Unordered list
        if re.match(r"^[\s]*[-*+]\s+", line):
            content = re.sub(r"^[\s]*[-*+]\s+", "", line)
            content = _inline_md(content)
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{content}</li>")
            continue
        elif in_list and line.strip() == "":
            out.append("</ul>")
            in_list = False
            continue
        elif in_list:
            # Still in list but line doesn't start with marker — close it
            out.append("</ul>")
            in_list = False

        # Empty line = paragraph break
        if line.strip() == "":
            out.append("</p>" if out and out[-1] != "</p>" and not out[-1].startswith("<h") and not out[-1].startswith("<li") and not out[-1].startswith("<ul") else "")
            continue

        # Regular paragraph
        content = _inline_md(line.strip())
        if content:
            out.append(f"<p>{content}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def _inline_md(text: str) -> str:
    """Convert inline Markdown: bold, italic, code, links."""
    # Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic *text* or _text_
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # Links [text](url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:var(--accent);">\1</a>', text)
    return text


def generate_monthly_survey(articles: list[dict], year: str, month: str, topic: str = "", prompt: str = "") -> str:
    """
    Generate a research-survey-style monthly report from a list of articles using LLM.
    Returns Markdown text with the correct title prepended.
    `topic` is the Chinese topic name, e.g. "固体动力" or "空空导弹".
    `prompt` is the theme-specific LLM prompt (uses config.MONTHLY_REPORT_PROMPT if empty).
    """
    if not articles:
        return ""

    # Determine topic from config if not explicitly passed
    if not topic:
        topic = config.APP_NAME_CN.replace("信息采集系统", "").strip()

    # Determine prompt from config if not explicitly passed
    if not prompt:
        prompt = config.MONTHLY_REPORT_PROMPT

    # Limit to most relevant articles to avoid exceeding LLM context window
    articles = sorted(articles, key=lambda a: a.get("relevance", 0) or 0, reverse=True)[:50]

    article_lines = []
    for i, a in enumerate(articles, 1):
        title = a.get("translated_title") or a["title"]
        raw_summary = a.get("translated_summary") or a.get("summary") or ""
        summary = str(raw_summary)[:800]
        source = a.get("source", "") or ""
        published = (a.get("published") or "")[:16]
        url = a.get("url", "") or ""
        kw = a.get("matched_kw", "") or ""
        article_lines.append(
            f"[Article {i}]\n"
            f"Title: {title}\n"
            f"Source: {source} | {published}\n"
            f"Summary: {summary}\n"
            f"Keywords: {kw}\n"
            f"URL: {url}\n"
        )

    articles_text = "\n---\n".join(article_lines)
    prompt = prompt.format(year=year, month=month, topic_zh=topic)
    prompt = f"{prompt}\n\n{articles_text}"

    # Primary model (glm-4.7 now), falls back to gpt-5.4-mini if needed
    survey_model = config.LLM_MODEL

    try:
        from llm_client import create_completion
        survey = create_completion(
            model=survey_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=6000,
        )

        if not survey:
            log.warning("Empty survey from LLM")
            return ""

        # Strip any H1 the LLM generated — we prepend the correct one server-side
        survey = re.sub(r"^#\s+.*\n?", "", survey, count=1).strip()

        # Prepend correct title
        correct_title = f"# {year}年{month}月{topic}技术研究进展综述"
        return f"{correct_title}\n\n{survey}"
    except Exception as e:
        log.error(f"Monthly survey generation failed: {e}")
        return ""
