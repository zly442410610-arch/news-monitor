"""Unified LLM client wrapper for OpenAI-compatible APIs (NVIDIA, OpenAI, etc.).
Supports automatic fallback to a backup model on failure."""
import logging
from openai import OpenAI
import config

_client = None
_fallback_client = None
_API_TIMEOUT = 60  # seconds for connect + read

_log = logging.getLogger("llm_client")

# Token usage tracking (per-run accumulation)
_token_usage = {"prompt_tokens": 0, "completion_tokens": 0}


def reset_token_usage():
    """Reset the accumulated token counters (call at start of each poll cycle)."""
    _token_usage["prompt_tokens"] = 0
    _token_usage["completion_tokens"] = 0


def get_token_usage() -> dict:
    """Return accumulated token usage as a dict."""
    return dict(_token_usage)


def _get_client(base_url=None, api_key=None):
    global _client
    if base_url or api_key:
        return OpenAI(
            api_key=api_key or config.LLM_API_KEY,
            base_url=base_url or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
        )
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
        )
    return _client


def _get_fallback_client():
    global _fallback_client
    if _fallback_client is None and config.LLM_FALLBACK_BASE_URL:
        _fallback_client = OpenAI(
            api_key=config.LLM_FALLBACK_API_KEY or config.LLM_API_KEY,
            base_url=config.LLM_FALLBACK_BASE_URL or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
        )
    return _fallback_client


def create_completion(model, messages, max_tokens) -> str:
    """Send a chat completion request, return response text (or empty string).
    Falls back to LLM_FALLBACK_MODEL / LLM_FALLBACK_BASE_URL on failure.
    Tracks token usage for visibility.
    """
    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content or ""
        _track_usage(resp)
        if text:
            return text
    except Exception as e:
        _log.debug(f"Primary LLM call failed: {e}")

    # Fallback
    fallback_model = config.LLM_FALLBACK_MODEL
    if not fallback_model:
        return ""  # no fallback configured

    fallback_client = _get_fallback_client() or _get_client()
    try:
        resp = fallback_client.chat.completions.create(
            model=fallback_model,
            messages=messages,
            max_tokens=max_tokens,
        )
        _track_usage(resp)
        return resp.choices[0].message.content or ""
    except Exception:
        return ""


def _track_usage(resp):
    """Extract and accumulate token usage from an API response."""
    try:
        usage = resp.usage
        if usage:
            pt = usage.prompt_tokens or 0
            ct = usage.completion_tokens or 0
            _token_usage["prompt_tokens"] += pt
            _token_usage["completion_tokens"] += ct
            _log.debug(f"LLM tokens: +{pt} prompt +{ct} completion "
                       f"(total: {_token_usage['prompt_tokens']}p / {_token_usage['completion_tokens']}c)")
    except Exception:
        pass
