"""Contract, persistence, and failover tests using deterministic fake inference."""

from app.services import llm_service
from conftest import install_fake_complete


def test_health_reports_database_keys_and_cache(api):
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_chat_response_and_history_preserve_metadata(api, monkeypatch):
    client, _ = api
    install_fake_complete(monkeypatch)
    response = client.post("/chat", json={"session_id": "s-123", "message": "Hello"})
    assert response.status_code == 200
    assert response.json()["metadata"] == {
        "resolution_source": "LIVE_INFERENCE", "model": "gemini/gemini-2.0-flash", "latency_ms": 2,
        "input_tokens": 17, "output_tokens": 5, "key_id": "key_1", "fallback_attempts": 0,
    }
    history = client.get("/sessions/s-123/messages")
    assert [row["role"] for row in history.json()["messages"]] == ["user", "assistant"]
    assert history.json()["messages"][1]["metadata"]["input_tokens"] == 17


def test_invalid_session_and_message_inputs_are_422(api):
    client, _ = api
    cases = [
        {"session_id": "", "message": "hello"},
        {"session_id": "s-1", "message": "   "},
        {"session_id": "x" * 129, "message": "hello"},
        {"session_id": "s-1", "message": "x" * 4001},
        {"session_id": "s-1", "message": "hello", "extra": "not allowed"},
    ]
    for body in cases:
        response = client.post("/chat", json=body)
        assert response.status_code == 422
        assert "detail" in response.json()


def test_malformed_json_is_json_422(api):
    client, _ = api
    response = client.post("/chat", content='{"session_id":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_multi_turn_and_sessions_are_isolated(api, monkeypatch):
    client, _ = api
    calls = []
    install_fake_complete(monkeypatch, calls=calls)
    client.post("/chat", json={"session_id": "first", "message": "first turn", "system_prompt": "Be brief"})
    client.post("/chat", json={"session_id": "first", "message": "second turn"})
    client.post("/chat", json={"session_id": "second", "message": "separate"})
    assert [message["role"] for message in calls[1][0]] == ["system", "user", "assistant", "user"]
    assert calls[1][0][0]["content"] == "Be brief"
    assert [message["content"] for message in calls[2][0]] == ["Helpful test assistant.", "separate"]


def test_system_prompt_is_not_in_history_response(api, monkeypatch):
    client, _ = api
    install_fake_complete(monkeypatch)
    client.post("/chat", json={"session_id": "private", "message": "hello", "system_prompt": "private instruction"})
    assert "private instruction" not in client.get("/sessions/private/messages").text


def test_unknown_session_is_404_and_has_no_history(api):
    response = api[0].get("/sessions/no-such-session/messages")
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_sqlite_persists_after_database_object_reopens(api, monkeypatch):
    client, database = api
    install_fake_complete(monkeypatch)
    client.post("/chat", json={"session_id": "persist", "message": "remember me"})
    reopened = type(database)(f"sqlite:///{database.path}")
    assert len(reopened.history("persist")) == 2


def test_failed_request_is_not_saved(api, monkeypatch):
    client, database = api
    monkeypatch.setattr("app.main.complete", lambda *args: (_ for _ in ()).throw(__import__("fastapi").HTTPException(503, "all providers unavailable")))
    response = client.post("/chat", json={"session_id": "failed", "message": "do not save"})
    assert response.status_code == 503
    assert response.json() == {"detail": "all providers unavailable"}
    assert database.history("failed") == []
    assert not database.session_exists("failed")


def test_simulated_key_one_failure_reaches_real_fallback_contract(api, monkeypatch):
    client, _ = api
    calls = []
    install_fake_complete(monkeypatch, calls=calls)
    response = client.post("/chat", json={"session_id": "fallback", "message": "hello"}, headers={"X-Simulate-Failure": "key_1=429"})
    assert response.status_code == 200
    assert calls[0][1] == {"key_1": 429}


def test_all_simulated_keys_fail_with_503_and_no_history(api, monkeypatch):
    client, database = api
    monkeypatch.setattr("app.main.complete", lambda settings, messages, simulation: llm_service.complete(settings, messages, simulation))
    response = client.post("/chat", json={"session_id": "all-fail", "message": "hello"}, headers={"X-Simulate-Failure": "*=429"})
    assert response.status_code == 503
    assert response.json() == {"detail": "all providers unavailable"}
    assert database.history("all-fail") == []


def test_invalid_simulation_headers_are_422(api):
    client, _ = api
    for value in ["key_1=401", "key_9=429", "key_1=429,bad", "*=429,key_2=500"]:
        response = client.post("/chat", json={"session_id": "s", "message": "hi"}, headers={"X-Simulate-Failure": value})
        assert response.status_code == 422
        assert "detail" in response.json()


def test_simulation_header_ignored_when_feature_is_disabled(api, monkeypatch):
    client, _ = api
    settings = __import__("app.main", fromlist=["settings"]).settings
    monkeypatch.setattr("app.main.settings", settings.__class__(**{**settings.__dict__, "enable_failure_simulation": False}))
    calls = []
    install_fake_complete(monkeypatch, calls=calls)
    response = client.post("/chat", json={"session_id": "disabled", "message": "hi"}, headers={"X-Simulate-Failure": "invalid"})
    assert response.status_code == 200
    assert calls[0][1] == {}


def test_cors_allows_configured_frontend_and_custom_header(api):
    client, _ = api
    response = client.options("/chat", headers={
        "Origin": "https://frontend.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-simulate-failure",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert "x-simulate-failure" in response.headers["access-control-allow-headers"].lower()
