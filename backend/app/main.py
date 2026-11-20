"""FastAPI application and the three public assignment endpoints."""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import Database
from .schemas import ChatRequest, ChatResponse
from .services.llm_service import complete, enable_cache, parse_simulation_header

settings = get_settings()
database = Database(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistent storage and LiteLLM's in-memory response cache."""
    database.initialize()
    enable_cache()
    yield


app = FastAPI(title="Lyftr AI Chatbot", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Simulate-Failure"],
)


@app.exception_handler(Exception)
async def unexpected_error_handler(request, error: Exception):
    """Keep unexpected failures in the required JSON error shape."""
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health")
def health() -> dict:
    """Report app, database, configured key pool, and cache state."""
    with database.connect() as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "ok", "keys_configured": len(settings.api_keys), "cache_enabled": True}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, x_simulate_failure: str | None = Header(default=None, alias="X-Simulate-Failure")) -> dict:
    """Build full conversation context, call LiteLLM, then persist a successful turn."""
    simulation: dict[str, int] = {}
    if settings.enable_failure_simulation:
        simulation = parse_simulation_header(x_simulate_failure, settings.api_keys)

    previous_prompt = database.get_system_prompt(payload.session_id)
    system_prompt = payload.system_prompt or previous_prompt or settings.default_system_prompt
    conversation = database.history(payload.session_id)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend({"role": row["role"], "content": row["content"]} for row in conversation)
    messages.append({"role": "user", "content": payload.message})

    result = complete(settings, messages, simulation)
    metadata = {key: result[key] for key in (
        "resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"
    )}
    database.save_turn(payload.session_id, payload.message, result["reply"], metadata, system_prompt)
    return {"session_id": payload.session_id, "reply": result["reply"], "metadata": metadata}


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> dict:
    """Return oldest-first persisted turns without any system prompt."""
    if not database.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    messages = []
    for row in database.history(session_id):
        item = {"role": row["role"], "content": row["content"]}
        if row["metadata"]:
            item["metadata"] = json.loads(row["metadata"])
        messages.append(item)
    return {"session_id": session_id, "messages": messages}
