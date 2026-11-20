"""LiteLLM service tests with provider calls mocked for repeatability."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.services import llm_service


def settings():
    return Settings("gemini/gemini-2.0-flash", ("secret-a", "secret-b"), "sqlite:////data/app.db", (), True, "helpful")


def result(reply="answer", cache_hit=False):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
        model="gemini/gemini-2.0-flash",
        _hidden_params={"cache_hit": cache_hit},
    )


def test_cache_initialized_with_litellm_local_cache():
    llm_service.enable_cache()
    assert llm_service.litellm.cache is not None
    assert "cache" in llm_service.litellm.input_callback


def test_litellm_cache_identity_includes_full_messages_and_model():
    cache = llm_service.litellm.Cache(type="local")
    first = cache.get_cache_key(model="gemini/gemini-2.0-flash", messages=[
        {"role": "system", "content": "helpful"}, {"role": "user", "content": "hello"},
    ])
    different_message = cache.get_cache_key(model="gemini/gemini-2.0-flash", messages=[
        {"role": "system", "content": "helpful"}, {"role": "user", "content": "different"},
    ])
    different_system = cache.get_cache_key(model="gemini/gemini-2.0-flash", messages=[
        {"role": "system", "content": "different system"}, {"role": "user", "content": "hello"},
    ])
    different_model = cache.get_cache_key(model="gpt-4o-mini", messages=[
        {"role": "system", "content": "helpful"}, {"role": "user", "content": "hello"},
    ])
    assert len({first, different_message, different_system, different_model}) == 4


def test_cache_hit_has_exact_source_null_key_zero_fallback_and_saved_usage(monkeypatch):
    monkeypatch.setattr(llm_service.litellm, "completion", lambda **kwargs: result(cache_hit=True))
    answer = llm_service.complete(settings(), [{"role": "system", "content": "helpful"}, {"role": "user", "content": "hi"}], {})
    assert answer["resolution_source"] == "LLM_CACHE"
    assert answer["key_id"] is None
    assert answer["fallback_attempts"] == 0
    assert (answer["input_tokens"], answer["output_tokens"]) == (12, 4)


def test_cache_miss_is_live_and_reports_successful_key(monkeypatch):
    monkeypatch.setattr(llm_service.litellm, "completion", lambda **kwargs: result(cache_hit=False))
    answer = llm_service.complete(settings(), [{"role": "user", "content": "new request"}], {})
    assert answer["resolution_source"] == "LIVE_INFERENCE"
    assert answer["key_id"] == "key_1"
    assert answer["fallback_attempts"] == 0


def test_first_key_error_falls_back_to_second_and_tracks_attempts(monkeypatch):
    calls = []
    def completion(**kwargs):
        calls.append(kwargs)
        if kwargs["api_key"] == "secret-a":
            raise type("RateLimitError", (Exception,), {"status_code": 429})("rate limited")
        return result()
    monkeypatch.setattr(llm_service.litellm, "completion", completion)
    answer = llm_service.complete(settings(), [{"role": "user", "content": "hello"}], {})
    assert [call["api_key"] for call in calls] == ["secret-a", "secret-b"]
    assert answer["key_id"] == "key_2"
    assert answer["fallback_attempts"] == 1
    assert answer["resolution_source"] == "LIVE_INFERENCE"


def test_simulated_key_one_failure_uses_second_real_key(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_service.litellm, "completion", lambda **kwargs: calls.append(kwargs) or result())
    answer = llm_service.complete(settings(), [{"role": "user", "content": "hello"}], {"key_1": 429})
    assert [call["api_key"] for call in calls] == ["secret-b"]
    assert answer["key_id"] == "key_2"
    assert answer["fallback_attempts"] == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_supported_provider_errors_fail_over(monkeypatch, status):
    count = 0
    def completion(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise type("ProviderError", (Exception,), {"status_code": status})("unavailable")
        return result()
    monkeypatch.setattr(llm_service.litellm, "completion", completion)
    assert llm_service.complete(settings(), [{"role": "user", "content": "x"}], {})["key_id"] == "key_2"


def test_all_simulated_keys_return_clean_503_without_provider_call(monkeypatch):
    monkeypatch.setattr(llm_service.litellm, "completion", lambda **kwargs: pytest.fail("must not call provider"))
    with pytest.raises(HTTPException) as error:
        llm_service.complete(settings(), [{"role": "user", "content": "x"}], {"*": 429})
    assert error.value.status_code == 503
    assert error.value.detail == "all providers unavailable"


def test_simulation_disables_litellm_cache_for_every_real_attempt(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_service.litellm, "completion", lambda **kwargs: calls.append(kwargs) or result())
    llm_service.complete(settings(), [{"role": "user", "content": "x"}], {"key_1": 429})
    assert calls[0]["cache"] == {"no-cache": True}
