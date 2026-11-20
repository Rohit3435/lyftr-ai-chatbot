"""Shared temporary configuration for isolated backend tests."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_test_root = tempfile.mkdtemp(prefix="lyftr-tests-")
os.environ.update({
    "LLM_API_KEYS": "test-key-one,test-key-two",
    "LLM_MODEL": "gemini/gemini-2.0-flash",
    "DATABASE_URL": f"sqlite:///{_test_root}/app.db",
    "ALLOWED_ORIGINS": "http://localhost:3000,https://frontend.example",
    "ENABLE_FAILURE_SIMULATION": "true",
})

from app import main  # noqa: E402
from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Give each test a fresh database, two fake keys, and a live ASGI app."""
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.initialize()
    monkeypatch.setattr(main, "database", database)
    monkeypatch.setattr(main, "settings", Settings(
        model="gemini/gemini-2.0-flash",
        api_keys=("secret-one", "secret-two"),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        allowed_origins=("http://localhost:3000", "https://frontend.example"),
        enable_failure_simulation=True,
        default_system_prompt="Helpful test assistant.",
    ))
    with TestClient(main.app) as client:
        yield client, database


def install_fake_complete(monkeypatch, reply="A helpful answer.", calls=None):
    """Replace the provider service while preserving route and SQLite behavior."""
    def fake(settings, messages, simulation):
        if calls is not None:
            calls.append((messages, simulation))
        return {
            "reply": reply,
            "resolution_source": "LIVE_INFERENCE",
            "model": settings.model,
            "latency_ms": 2,
            "input_tokens": 17,
            "output_tokens": 5,
            "key_id": "key_1",
            "fallback_attempts": 0,
        }
    monkeypatch.setattr(main, "complete", fake)
