"""Unified LLM client wrapper for OpenAI-compatible APIs (Zhipu AI, OpenAI, etc.).
Supports automatic fallback to backup models on failure (up to 4 tiers)."""
import logging
import threading
import time
import httpx
from openai import OpenAI
import config

_client = None
_fallback_client = None
_fallback2_client = None
_fallback3_client = None
_fallback4_client = None
_API_TIMEOUT = 15  # seconds for connect + read (fail fast → fallback)
_MAX_CONCURRENT = getattr(config, "LLM_CONCURRENCY", 2)
_RPM = getattr(config, "LLM_RPM", 60)  # requests per minute

_log = logging.getLogger("llm_client")

# Token usage tracking (per-run accumulation)
_token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

# Rate limiter
_semaphore = threading.Semaphore(_MAX_CONCURRENT)
_rate_lock = threading.Lock()
_last_request_time = 0.0
_MIN_INTERVAL = 60.0 / _RPM


def reset_token_usage():
    """Reset the accumulated token counters (call at start of each poll cycle)."""
    _token_usage["prompt_tokens"] = 0
    _token_usage["completion_tokens"] = 0


def get_token_usage() -> dict:
    """Return accumulated token usage as a dict."""
    return dict(_token_usage)


def _get_client(base_url=None, api_key=None):
    global _client
    kwargs = dict(max_retries=0)
    if config.LLM_PROXY:
        kwargs["http_client"] = httpx.Client(proxy=config.LLM_PROXY)
    if base_url or api_key:
        return OpenAI(
            api_key=api_key or config.LLM_API_KEY,
            base_url=base_url or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
            **kwargs,
        )
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
            **kwargs,
        )
    return _client


def _get_fallback_client():
    global _fallback_client
    if _fallback_client is None and config.LLM_FALLBACK_BASE_URL:
        _fallback_client = OpenAI(
            api_key=config.LLM_FALLBACK_API_KEY or config.LLM_API_KEY,
            base_url=config.LLM_FALLBACK_BASE_URL or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
            max_retries=0,
        )
    return _fallback_client


def _get_fallback2_client():
    global _fallback2_client
    if _fallback2_client is None and config.LLM_FALLBACK2_BASE_URL:
        _fallback2_client = OpenAI(
            api_key=config.LLM_FALLBACK2_API_KEY or config.LLM_API_KEY,
            base_url=config.LLM_FALLBACK2_BASE_URL or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
            max_retries=0,
        )
    return _fallback2_client


def _get_fallback3_client():
    global _fallback3_client
    if _fallback3_client is None and config.LLM_FALLBACK3_BASE_URL:
        _fallback3_client = OpenAI(
            api_key=config.LLM_FALLBACK3_API_KEY or config.LLM_API_KEY,
            base_url=config.LLM_FALLBACK3_BASE_URL or config.LLM_BASE_URL,
            timeout=_API_TIMEOUT,
            max_retries=0,
        )
    return _fallback3_client


def _get_fallback4_client():
    global _fallback4_client
    if _fallback4_client is None and config.LLM_FALLBACK4_BASE_URL:
        _fallback4_client = OpenAI(
            api_key=config.LLM_FALLBACK4_API_KEY or config.LLM_API_KEY,
            base_url=config.LLM_FALLBACK4_BASE_URL,
            timeout=_API_TIMEOUT,
            max_retries=0,
            http_client=httpx.Client(proxy="http://127.0.0.1:7890"),
        )
    return _fallback4_client


def _throttle():
    """Rate limiter — ensure we don't exceed RPM limit."""
    global _last_request_time
    with _rate_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < _MIN_INTERVAL:
            sleep_time = _MIN_INTERVAL - elapsed
            _log.debug(f"Rate limit throttle: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        _last_request_time = time.time()


def create_completion(model, messages, max_tokens) -> str:
    """Send a chat completion request, return response text (or empty string).
    Falls back through up to 3 tiers: primary → LLM_FALLBACK_MODEL → LLM_FALLBACK2_MODEL.
    Tracks token usage for visibility.
    Rate-limited to LLM_RPM with max LLM_CONCURRENCY concurrent calls.
    """
    # Some models (Cerebras, DeepSeek R1) consume tokens for reasoning before
    # outputting content — add a 2K buffer so content isn't truncated to empty
    _REASONING_BUFFER = 2048

    with _semaphore:
        _throttle()
        try:
            resp = _get_client().chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens + _REASONING_BUFFER,
            )
            text = resp.choices[0].message.content or ""
            _track_usage(resp)
            if text:
                return text
        except Exception as e:
            _log.debug(f"Primary LLM call failed: {e}")

        # Fallback tier 1
        fallback_model = config.LLM_FALLBACK_MODEL
        if fallback_model:
            fallback_client = _get_fallback_client() or _get_client()
            try:
                resp = fallback_client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                _track_usage(resp)
                text = resp.choices[0].message.content or ""
                if text:
                    return text
            except Exception as e:
                _log.debug(f"Fallback LLM call failed: {e}")

        # Fallback tier 2 (NVIDIA — try multiple comma-separated models)
        fallback2_models = [m.strip() for m in config.LLM_FALLBACK2_MODEL.split(",") if m.strip()] if config.LLM_FALLBACK2_MODEL else []
        if fallback2_models:
            fallback2_client = _get_fallback2_client()
            if fallback2_client:
                for fb2_model in fallback2_models:
                    try:
                        resp = fallback2_client.chat.completions.create(
                            model=fb2_model,
                            messages=messages,
                            max_tokens=max_tokens,
                        )
                        _track_usage(resp)
                        text = resp.choices[0].message.content or ""
                        if text:
                            return text
                    except Exception as e:
                        _log.debug(f"Fallback2 LLM '{fb2_model}' failed: {e}")
                        continue

        # Fallback tier 3 (ZhiPu free models — comma-separated)
        fallback3_models = [m.strip() for m in config.LLM_FALLBACK3_MODEL.split(",") if m.strip()] if config.LLM_FALLBACK3_MODEL else []
        if fallback3_models:
            fallback3_client = _get_fallback3_client()
            if fallback3_client:
                for fb3_model in fallback3_models:
                    try:
                        resp = fallback3_client.chat.completions.create(
                            model=fb3_model,
                            messages=messages,
                            max_tokens=max_tokens,
                        )
                        _track_usage(resp)
                        text = resp.choices[0].message.content or ""
                        if text:
                            return text
                    except Exception as e:
                        _log.debug(f"Fallback3 LLM '{fb3_model}' failed: {e}")
                        continue

        # Fallback tier 4 (Cerebras — via Clash proxy)
        fallback4_models = [m.strip() for m in config.LLM_FALLBACK4_MODEL.split(",") if m.strip()] if config.LLM_FALLBACK4_MODEL else []
        if fallback4_models:
            fallback4_client = _get_fallback4_client()
            if fallback4_client:
                for fb4_model in fallback4_models:
                    try:
                        resp = fallback4_client.chat.completions.create(
                            model=fb4_model,
                            messages=messages,
                            max_tokens=max_tokens + 1024,  # extra room for reasoning tokens
                        )
                        _track_usage(resp)
                        text = resp.choices[0].message.content or ""
                        if text:
                            return text
                    except Exception as e:
                        _log.debug(f"Fallback4 LLM '{fb4_model}' failed: {e}")
                        continue

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
