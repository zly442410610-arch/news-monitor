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
from monitor import init_db, get_articles_for_briefing, get_articles_for_digest

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


def save_paper_digest(text: str) -> str:
    """Save paper digest to file. Returns file path."""
    config.BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    week_num = now.isocalendar()[1]
    filename = f"paper-digest-{now.year}-week{week_num}-{now.strftime('%Y%m%d')}.md"
    path = config.BRIEFING_DIR / filename
    path.write_text(text, encoding="utf-8")
    log.info(f"Paper digest saved to {path}")
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


def _generate_fallback_paper_digest(articles: list[dict]) -> str:
    """Generate a simple text-based paper digest without LLM."""
    now_str = datetime.now(timezone.utc).isoformat()[:16]
    lines = [f"# 论文精读（自动生成）\n", f"生成时间: {now_str}\n"]
    lines.append(f"收录论文: {len(articles)} 篇\n\n---\n")

    for i, a in enumerate(articles, 1):
        title = a.get("translated_title") or a.get("title", "")
        author = a.get("author", "")
        source = a.get("source", "")
        published = (a.get("published") or "")[:16]
        url = a.get("url", "")
        lines.append(f"### {i}. {title}")
        if author:
            lines.append(f"作者: {author}")
        lines.append(f"来源: {source} | {published}")
        lines.append(f"链接: {url}\n")

    return "\n".join(lines)


def generate_paper_digest(conn, days=7, max_papers=10) -> str:
    """
    Generate a Chinese-language paper digest from recent paper-type articles
    using LLM. Returns the digest text as a string.
    """
    papers = get_articles_for_digest(conn, days=days, max_papers=max_papers)
    log.info(f"Paper digest: {len(papers)} papers from last {days} days")

    if not papers:
        msg = f"过去 {days} 天内没有收录到相关论文。"
        log.info(msg)
        return msg

    # Format papers for the LLM prompt
    paper_lines = []
    for i, a in enumerate(papers, 1):
        title = a.get("translated_title") or a.get("title", "")
        author = a.get("author", "")
        source = a.get("source", "")
        published = (a.get("published") or "")[:16]
        summary = (a.get("translated_summary") or a.get("summary", ""))[:800]
        url = a.get("url", "")
        doi = a.get("doi") or ""
        paper_lines.append(
            f"[Paper {i}]\n"
            f"Title: {title}\n"
            f"Author: {author}\n"
            f"Source: {source} | {published}\n"
            f"Summary: {summary}\n"
            f"DOI: {doi}\n"
            f"URL: {url}\n"
        )

    papers_text = "\n---\n".join(paper_lines)

    domain = config.APP_NAME_CN.replace("信息采集系统", "").strip()
    digest_prompt = (
        f"你是一个航空航天领域的科研助手。以下是从近期{len(papers)}篇关于{domain}的论文中提取的信息。\n"
        f"请用中文生成一份论文精读报告，要求：\n\n"
        f"1. 对每篇论文，按以下结构分析：\n"
        f"   - **核心贡献**：用1-2句话概括论文的主要贡献\n"
        f"   - **技术亮点**：用通俗易懂的语言解释关键技术点\n"
        f"   - **工程应用价值**：分析该成果的工程转化潜力\n\n"
        f"2. 在分析中使用[N]索引引用文献（例如：\"文献[1]提出了一种新方法...\"）\n\n"
        f"3. 最后，写一段总结性评述，概括本期论文的整体研究趋势和方向。\n\n"
        f"以下是论文列表：\n"
        f"{papers_text}\n"
    )

    try:
        from llm_client import create_completion
        digest = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": digest_prompt}],
            max_tokens=4000,
        )
        if not digest:
            log.warning("Empty paper digest from LLM")
            digest = _generate_fallback_paper_digest(papers)
    except Exception as e:
        log.error(f"Paper digest generation failed: {e}")
        digest = _generate_fallback_paper_digest(papers)

    # Append reference list
    refs = "\n\n---\n## 参考文献\n"
    for i, a in enumerate(papers, 1):
        title = a.get("translated_title") or a.get("title", "")
        url = a.get("url", "")
        source = a.get("source", "")
        refs += f"{i}. [{title}]({url}) -- {source}\n"

    full_text = digest + refs
    filepath = save_paper_digest(full_text)
    log.info(f"Paper digest generated: {len(full_text)} chars → {filepath}")
    return full_text


def _add_ref_ids(html: str) -> str:
    """Post-process HTML to wrap reference list in <ol> with id anchors."""
    m = re.search(r'(<h2>参考文献</h2>\s*)((?:<p>\d+\..*?</p>\s*)+)', html, re.DOTALL)
    if not m:
        return html
    items = re.findall(r'<p>(\d+)\.\s+(.*?)</p>', m.group(2), re.DOTALL)
    lis = "\n".join(f'<li id="ref-{num}">{content.strip()}</li>' for num, content in items)
    replacement = f'{m.group(1)}<ol class="ref-list">\n{lis}\n</ol>'
    return html.replace(m.group(0), replacement, 1)


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

    html = "\n".join(out)
    html = _add_ref_ids(html)
    return html


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
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Citation references [N] — expand ranges first, then comma-separated, then singles
    text = re.sub(r"\[(\d+)-(\d+)\]", lambda m: "".join(f"[{i}]" for i in range(int(m.group(1)), int(m.group(2)) + 1)), text)
    text = re.sub(r"\[(\d+)(?:\s*,\s*\d+)+\]", lambda m: "".join(f"[{g}]" for g in re.findall(r"\d+", m.group(0))), text)
    text = re.sub(r"\[(\d{1,2})\]", r'<sup><a href="#ref-\1" class="ref-cite">[\1]</a></sup>', text)
    return text


def generate_monthly_survey(articles: list[dict], year: str, month: str, topic: str = "", prompt: str = "", prefix: str = "") -> str:
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
        survey = f"{correct_title}\n\n{survey}"

        # Strip any reference section the LLM generated — we replace it with our own
        survey = re.sub(r"\n##\s*参考文献\s*[\s\S]*", "", survey)

        # Append reference list with links to local article pages
        ref_lines = ["\n\n---\n", "## 参考文献\n"]
        for i, a in enumerate(articles, 1):
            title = a.get("translated_title") or a["title"]
            source = a.get("source", "")
            art_id = a.get("id", "")
            ref_lines.append(f"{i}. [{title}]({prefix}/article?id={art_id}) — {source}")
        survey += "\n".join(ref_lines)

        return survey
    except Exception as e:
        log.error(f"Monthly survey generation failed: {e}")
        return ""
