"""
Translation module for the aerospace news monitor.
Uses LLM (Zhipu AI glm-4-flash) to translate non-Chinese articles to Chinese.
"""
import logging
import re
import time

import config
from translator_glossary import apply_glossary, get_prompt_terms

log = logging.getLogger("news-monitor.translator")

# Rough CJK detection — any article containing significant Chinese characters
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


def contains_chinese(text: str) -> bool:
    """Check if text contains any Chinese characters."""
    return bool(CJK_RE.search(text))


def is_predominantly_chinese(text: str, threshold=0.2) -> bool:
    """Check if text is predominantly Chinese (by CJK character ratio).

    Used to decide whether content needs translation — avoids false positives
    from English articles that happen to contain a few Chinese characters.
    """
    if not text or len(text) < 50:
        return contains_chinese(text)
    cjk_count = len(CJK_RE.findall(text))
    non_space = len(text.strip())
    return (cjk_count / non_space) > threshold


def detect_language(text: str) -> str:
    """Simple language detection based on character sets."""
    if contains_chinese(text):
        return "zh"
    # Check for Korean (Hangul)
    if re.search(r"[가-힯]", text):
        return "ko"
    # Check for Japanese (Hiragana, Katakana)
    if re.search(r"[぀-ゟ゠-ヿ]", text):
        return "ja"
    # Check for Cyrillic (Russian, etc.)
    if re.search(r"[Ѐ-ӿ]", text):
        return "ru"
    return "en"  # default to English


CONTENT_TRANSLATION_PROMPT = """You are a professional aerospace and defense translator. Translate the following technical article content from any foreign language (English, Korean, Japanese, Russian, etc.) to Chinese (中文).

Requirements:
- Keep technical terms accurate
- Maintain factual accuracy, do not add or omit information
- Preserve all technical details, numbers, specifications
- If the text contains code, formulas, or data, keep those unchanged
- Respond with ONLY the translated text, no XML tags or headers
- Break long paragraphs appropriately for Chinese reading
- IMPORTANT: Military aircraft designations (e.g., F-35B Lightning II, F/A-18F Super Hornet, EA-18G Growler, F-22 Raptor, F-15EX Eagle II) must be translated in full ONCE and NEVER repeated or split within the same sentence. After the full designation appears, do NOT add any part of it again in parentheses, quotes, or as a separate word.
  ✅ Correct: "F-35B Lightning II短距起降型" (one complete translation, no repetition)
  ✅ Correct: "F-35 Lightning II战斗机" (one complete translation)
  ✅ Correct: "F-15EX Eagle II战斗机机队" (one complete translation)
  ❌ Wrong: "F-35B闪电II短距起降型闪电II" (闪电II repeated)
  ❌ Wrong: "F-35闪电II战斗机 II" (II repeated separately)
  ❌ Wrong: "F-35闪电II战斗机战斗机" (战斗机 repeated)
  ❌ Wrong: "F-15EX鹰II战斗机"鹰II"" (鹰II repeated in quotes)
  ❌ Wrong: "F-15E攻击鹰战斗轰炸机"攻击鹰"" (攻击鹰 repeated in quotes)

Original content:
{content}"""


def translate_content(content: str, api_key: str = None) -> str | None:
    """
    Translate full article content from foreign language to Chinese.
    Returns translated text, or None if failed.
    """
    if not content or len(content.strip()) < 100:
        return None
    if is_predominantly_chinese(content):
        return content  # already Chinese

    try:
        from llm_client import create_completion

        key = api_key or config.LLM_API_KEY
        if not key:
            log.warning("No API key configured for content translation")
            return None

        truncated = content[:6000]  # fit within token limits
        prompt = CONTENT_TRANSLATION_PROMPT.format(content=truncated)

        text = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )

        if not text:
            log.warning(f"Content translation empty response, retrying...")
            for attempt in range(3):
                delay = 2 ** (attempt + 1)
                log.warning(f"Content translation empty, retry {attempt+1}/3 (+{delay}s)...")
                time.sleep(delay)
                text = create_completion(
                    model=config.LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4000,
                )
                if text:
                    break

        if text and len(text) > 50:
            text = apply_glossary(text.strip(), config.THEME_NAME)
            log.info(f"Content translated: {len(content)} chars → {len(text)} chars")
            return text
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
        from llm_client import create_completion

        key = api_key or config.LLM_API_KEY
        if not key:
            log.warning("No API key configured for translation")
            return None

        prompt = config.TRANSLATION_PROMPT.format(
            source_lang=source_lang,
            glossary=get_prompt_terms(config.THEME_NAME, max_terms=25),
            title=(title or "").replace("{", "{{").replace("}", "}}"),
            summary=((summary or "")[:1000]).replace("{", "{{").replace("}", "}}"),
        )

        text = create_completion(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )

        if not text:
            # Retry with exponential backoff
            for attempt in range(3):
                delay = 2 ** (attempt + 1)
                log.warning(f"Empty translation response for '{title[:50]}...', retry {attempt+1}/3 (+{delay}s)...")
                time.sleep(delay)
                text = create_completion(
                    model=config.LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                )
                if text:
                    break
            if not text:
                log.warning(f"Empty translation response after 3 retries for '{title[:50]}...', giving up")
                return None

        # Parse response — extract from XML tags
        result = {"title": title, "summary": summary}

        title_match = re.search(r"<translated_title>(.*?)</translated_title>", text, re.DOTALL)
        summary_match = re.search(r"<translated_summary>(.*?)</translated_summary>", text, re.DOTALL)

        if title_match:
            result["title"] = apply_glossary(title_match.group(1).strip(), config.THEME_NAME)
        if summary_match:
            result["summary"] = apply_glossary(summary_match.group(1).strip(), config.THEME_NAME)

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
                result["title"] = apply_glossary(" ".join(title_parts), config.THEME_NAME)
            if summary_parts:
                result["summary"] = apply_glossary(" ".join(summary_parts), config.THEME_NAME)

            # Fallback: use whole response as title if parsing completely failed
            if not title_parts and not summary_parts:
                result["title"] = apply_glossary(text.strip()[:500], config.THEME_NAME)
                result["summary"] = summary

        log.info(f"Translated '{title[:40]}...' → '{result['title'][:40]}...'")

        # If the "translated" title contains no Chinese characters, the LLM
        # returned the original text unchanged — treat as failure.
        if not contains_chinese(result["title"]):
            log.warning(f"Translation returned non-Chinese text for '{title[:40]}...', discarding")
            return None

        return result

    except Exception as e:
        log.warning(f"Translation failed for '{title[:50]}...': {e}")
        return None
