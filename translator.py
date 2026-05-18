"""
Translation module for the aerospace news monitor.
Uses Anthropic Claude to translate non-Chinese articles to Chinese.
"""
import logging
import re

import config

log = logging.getLogger("news-monitor.translator")

# Rough CJK detection — any article containing significant Chinese characters
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


def contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return bool(CJK_RE.search(text))


def detect_language(text: str) -> str:
    """Simple language detection based on character sets."""
    if contains_chinese(text):
        return "zh"
    # Check for extended Latin (European languages)
    return "en"  # default to English


CONTENT_TRANSLATION_PROMPT = """You are a professional aerospace and defense translator. Translate the following technical article content from English to Chinese (中文).

Requirements:
- Keep technical terms accurate
- Maintain factual accuracy, do not add or omit information
- Preserve all technical details, numbers, specifications
- If the text contains code, formulas, or data, keep those unchanged
- Respond with ONLY the translated text, no XML tags or headers
- Break long paragraphs appropriately for Chinese reading

Original content:
{content}"""


def translate_content(content: str, api_key: str = None) -> str | None:
    """
    Translate full article content from foreign language to Chinese.
    Returns translated text, or None if failed.
    """
    if not content or len(content.strip()) < 100:
        return None
    if contains_chinese(content):
        return content  # already Chinese

    try:
        import anthropic

        key = api_key or config.LLM_API_KEY
        if not key:
            log.warning("No API key configured for content translation")
            return None

        client = anthropic.Anthropic(api_key=key)
        truncated = content[:6000]  # fit within token limits
        prompt = CONTENT_TRANSLATION_PROMPT.format(content=truncated)

        resp = client.messages.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )

        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        if text and len(text) > 50:
            log.info(f"Content translated: {len(content)} chars → {len(text)} chars")
            return text.strip()
        return None
    except Exception as e:
        log.warning(f"Content translation failed ({len(content)} chars): {e}")
        return None


def translate_article(title: str, summary: str, api_key: str = None) -> dict | None:
    """
    Translate article title and summary from foreign language to Chinese.
    Returns dict with 'title' and 'summary' translations, or None if not needed/failed.
    """
    # Skip if already in Chinese
    if contains_chinese(title) and contains_chinese(summary):
        return None  # already Chinese, no translation needed

    source_lang = detect_language(title)

    try:
        import anthropic

        key = api_key or config.LLM_API_KEY
        if not key:
            log.warning("No API key configured for translation")
            return None

        client = anthropic.Anthropic(api_key=key)

        prompt = config.TRANSLATION_PROMPT.format(
            source_lang=source_lang,
            title=title,
            summary=(summary or "")[:1000],
        )

        resp = client.messages.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )

        # Extract text — handle thinking blocks
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        if not text:
            log.warning(f"Empty translation response for '{title[:50]}...'")
            return None

        # Parse response — extract from XML tags
        result = {"title": title, "summary": summary}

        title_match = re.search(r"<translated_title>(.*?)</translated_title>", text, re.DOTALL)
        summary_match = re.search(r"<translated_summary>(.*?)</translated_summary>", text, re.DOTALL)

        if title_match:
            result["title"] = title_match.group(1).strip()
        if summary_match:
            result["summary"] = summary_match.group(1).strip()

        # Fallback: if XML parsing failed, try the old line-based approach
        if not title_match and not summary_match:
            lines = text.strip().split("\n")
            title_parts = []
            summary_parts = []
            current_section = None
            title_headers = ["Translated Title", "Translated title", "Title", "title"]
            summary_headers = ["Translated Summary", "Translated summary", "Summary", "summary"]

            def startswith_any(s, prefixes):
                for p in prefixes:
                    if s.startswith(p + ":") or s.startswith(p + "："):
                        _, rest = s.split(p + s[len(p)], 1)
                        rest = rest.lstrip(":：").strip()
                        return rest
                return None

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                title_rest = startswith_any(line, title_headers)
                if title_rest is not None:
                    current_section = "title"
                    if title_rest:
                        title_parts.append(title_rest)
                    continue
                summary_rest = startswith_any(line, summary_headers)
                if summary_rest is not None:
                    current_section = "summary"
                    if summary_rest:
                        summary_parts.append(summary_rest)
                    continue
                if current_section == "title" and not line.startswith(("---", "=")):
                    title_parts.append(line)
                elif current_section == "summary" and not line.startswith(("---", "=")):
                    summary_parts.append(line)

            if title_parts:
                result["title"] = " ".join(title_parts)
            if summary_parts:
                result["summary"] = " ".join(summary_parts)

            # Fallback: use whole response as title if parsing completely failed
            if not title_parts and not summary_parts:
                result["title"] = text.strip()[:500]
                result["summary"] = summary

        log.info(f"Translated '{title[:40]}...' → '{result['title'][:40]}...'")
        return result

    except Exception as e:
        log.warning(f"Translation failed for '{title[:50]}...': {e}")
        return None
