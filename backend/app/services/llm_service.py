"""LiteLLM completion calls, built-in caching, and ordered key failover."""

import re
import time
from typing import Any

import litellm
from fastapi import HTTPException

from ..config import Settings


SIMULATION_CODES = {429, 500, 502, 503}


def enable_cache() -> None:
    """Enable LiteLLM's process-local exact-match response cache."""
    # LiteLLM hashes the model and the complete messages/parameters, so the
    # system prompt and prior turns are part of the cache identity.
    # enable_cache wires LiteLLM's request and success callbacks as well as
    # constructing its Cache object; assigning Cache alone would not activate it.
    litellm.enable_cache(type="local")


def parse_simulation_header(value: str | None, keys: tuple[str, ...]) -> dict[str, int]:
    """Validate one-request failure instructions without ever using real keys."""
    if not value:
        return {}
    simulated: dict[str, int] = {}
    for item in value.split(","):
        match = re.fullmatch(r"\s*(\*|key_[1-9][0-9]*)\s*=\s*(429|500|502|503)\s*", item)
        if not match:
            raise HTTPException(status_code=422, detail="invalid X-Simulate-Failure header")
        key_id, raw_code = match.groups()
        if key_id != "*" and int(key_id[4:]) > len(keys):
            raise HTTPException(status_code=422, detail="unknown key in X-Simulate-Failure header")
        if key_id in simulated or (key_id == "*" and simulated):
            raise HTTPException(status_code=422, detail="duplicate key in X-Simulate-Failure header")
        simulated[key_id] = int(raw_code)
    if "*" in simulated and len(simulated) != 1:
        raise HTTPException(status_code=422, detail="wildcard must be used alone")
    return simulated


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read LiteLLM response fields across dict and model response types."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _provider_error_is_retryable(error: Exception) -> bool:
    """Only rate limits, quota failures, and server errors advance the pool."""
    code = getattr(error, "status_code", None) or getattr(error, "http_status", None)
    if code in {429, 500, 502, 503}:
        return True
    name = type(error).__name__.lower()
    message = str(error).lower()
    return "ratelimit" in name or "quota" in message or any(token in message for token in ("resource_exhausted", "insufficient_quota"))


def complete(settings: Settings, messages: list[dict[str, str]], simulation: dict[str, int]) -> dict[str, Any]:
    """Call configured keys in order and return usage plus the selected key."""
    if not settings.api_keys:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    for index, api_key in enumerate(settings.api_keys, start=1):
        key_id = f"key_{index}"
        if "*" in simulation or key_id in simulation:
            continue

        try:
            started = time.perf_counter()
            response = litellm.completion(
                model=settings.model,
                messages=messages,
                api_key=api_key,
                num_retries=0,
                # A simulation must exercise provider fallback even when an
                # identical request is already in LiteLLM's local cache.
                cache={"no-cache": True} if simulation else None,
            )
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
            choices = _field(response, "choices", []) or []
            choice = choices[0] if choices else None
            reply = _field(_field(choice, "message", {}), "content", "")
            if isinstance(reply, list):
                reply = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in reply)
            if not isinstance(reply, str) or not reply.strip():
                raise RuntimeError("provider returned an empty response")

            usage = _field(response, "usage", {}) or {}
            hidden = _field(response, "_hidden_params", {}) or {}
            cache_hit = bool(_field(hidden, "cache_hit", False))
            response_model = _field(response, "model", None) or settings.model
            return {
                "reply": reply.strip(),
                "model": response_model,
                "resolution_source": "LLM_CACHE" if cache_hit else "LIVE_INFERENCE",
                "latency_ms": elapsed_ms,
                "input_tokens": int(_field(usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(_field(usage, "completion_tokens", 0) or 0),
                "key_id": None if cache_hit else key_id,
                "fallback_attempts": 0 if cache_hit else index - 1,
            }
        except Exception as error:
            if _provider_error_is_retryable(error):
                continue
            # Provider/SDK errors are not allowed to leak secrets or stack traces.
            raise HTTPException(status_code=503, detail="all providers unavailable") from None

    raise HTTPException(status_code=503, detail="all providers unavailable")
