"""
Groq wrapper. Every call: (a) keyed by input hash and cached on disk,
(b) exponential backoff on rate limits, (c) falls back from strict JSON
mode to plain text if the model rejects response_format, (d) raises
RateLimited only when both retries and cache are exhausted.

The JSON-mode fallback was added after verify_env.py showed gpt-oss models
occasionally reject Groq's strict response_format. The fallback strips
markdown fences and parses the first JSON object it finds.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq, RateLimitError, BadRequestError

load_dotenv()

CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", "./data/llm_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REASON = os.getenv("GROQ_MODEL_REASON", "openai/gpt-oss-120b")
MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")

_client: Groq | None = None


class RateLimited(Exception):
    """Raised when Groq is rate-limited and there is no cache entry."""


class BadLLMOutput(Exception):
    """Raised when the model returns text that cannot be parsed as JSON."""


def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key or key.endswith("replace_me"):
            raise RuntimeError("GROQ_API_KEY not set. See .env.example.")
        _client = Groq(api_key=key)
    return _client


def _cache_key(model: str, messages: list, **kw: Any) -> str:
    payload = json.dumps({"m": model, "msg": messages, **kw}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction: try direct, then markdown fenced, then
    first balanced {...} block. Raises BadLLMOutput on total failure."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise BadLLMOutput(f"no JSON object found in: {text[:200]!r}")


def call_json(
    messages: list[dict],
    *,
    model: str = MODEL_REASON,
    max_retries: int = 4,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    use_cache: bool = True,
) -> tuple[dict, bool, str | None]:
    """Returns (parsed_dict, from_cache, warning).

    warning is non-None when a cached result was used because of rate limits.
    Raises RateLimited if no cache and retries exhausted.
    Raises BadLLMOutput if the model produced unparseable output after
    both strict and fallback attempts.
    """
    key = _cache_key(model, messages, t=temperature, mt=max_tokens)
    path = CACHE_DIR / f"{key}.json"
    cached = json.loads(path.read_text()) if path.exists() else None

    # Cache-first: return immediately on a hit. This is what makes reruns
    # free on the Groq free tier. Use use_cache=False to force fresh output.
    if use_cache and cached is not None and cached != {}:
        return cached, True, None

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = _get_client().chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or "{}"
            parsed = _extract_json(text)
            # Do not cache empty results — they poison every future run.
            if parsed and parsed != {}:
                path.write_text(json.dumps(parsed))
            return parsed, False, None
        except BadRequestError as e:
            # strict JSON mode rejected — retry without response_format
            last_err = e
            try:
                resp = _get_client().chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = resp.choices[0].message.content or "{}"
                parsed = _extract_json(text)
                if parsed and parsed != {}:
                    path.write_text(json.dumps(parsed))
                return parsed, False, "json-mode rejected; used text fallback"
            except Exception as inner:
                last_err = inner
                continue
        except RateLimitError as e:
            last_err = e
            # TPD limits don't reset in seconds. Fast backoff, then give up
            # so the caller can fall back deterministically instead of
            # blocking for minutes.
            if attempt < min(max_retries, 2):
                time.sleep(1.5 * (attempt + 1) + random.random())
                continue
            if cached is not None:
                return cached, True, f"Rate limited; served from cache ({key})"
            raise RateLimited(str(e))
        except BadLLMOutput:
            # repair pass: ask the model to try again with an explicit nudge
            if attempt < max_retries - 1:
                messages = messages + [
                    {"role": "user",
                     "content": "Your previous reply was not valid JSON. "
                                "Reply with a single JSON object only."},
                ]
                continue
            raise

    if cached is not None:
        return cached, True, "Retries exhausted; served from cache"
    raise RateLimited(str(last_err) if last_err else "Unknown rate limit")


def cache_stats() -> dict:
    files = list(CACHE_DIR.glob("*.json"))
    return {"entries": len(files),
            "bytes": sum(f.stat().st_size for f in files)}
