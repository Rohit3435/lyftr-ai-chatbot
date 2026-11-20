"""Environment based settings shared by the backend modules."""

from dataclasses import dataclass
import os


def _true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    model: str
    api_keys: tuple[str, ...]
    database_url: str
    allowed_origins: tuple[str, ...]
    enable_failure_simulation: bool
    default_system_prompt: str


def get_settings() -> Settings:
    """Read configuration at startup so secrets never live in source code."""
    raw_keys = os.getenv("LLM_API_KEYS", "")
    keys = tuple(key.strip() for key in raw_keys.split(",") if key.strip() and not key.strip().lower().startswith("your_"))
    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return Settings(
        model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
        api_keys=keys,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/app.db"),
        allowed_origins=tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip()),
        enable_failure_simulation=_true(os.getenv("ENABLE_FAILURE_SIMULATION", "false")),
        default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT", "You are Lyftr AI, a helpful and concise assistant."),
    )
