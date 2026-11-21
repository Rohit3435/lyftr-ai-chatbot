# Lyftr AI Chatbot

Lyftr AI is a full-stack conversational assistant built for the LLM Chatbot with Key Failover and Response Caching assignment. React and Vite provide the chat interface. FastAPI rebuilds each turn's full context from SQLite, calls LiteLLM with ordered API key fallback, and returns per-response token usage and latency. LiteLLM's local cache serves exact repeated model requests.

## Technology stack and layout

- Frontend: React 18, Vite, responsive CSS.
- Backend: Python 3.12, FastAPI, LiteLLM.
- Storage/cache: SQLite and LiteLLM's in-process local cache.
- Runtime: Docker, Docker Compose, Nginx.

```text
backend/app/              FastAPI routes, configuration, SQLite, LiteLLM service
backend/tests/            Mock-based API and service tests
frontend/src/             Chat interface and styling
docs/ARCHITECTURE.md      Mermaid system diagram and request flow
docs/INTERVIEW_GUIDE.md   Module walkthrough and interview questions
docker-compose.yml        Local full-stack deployment
render.yaml               Backend deployment blueprint with persistent disk
```

## 1. Live URLs

- Frontend: https://frontend-ivory-six-90.vercel.app
- Backend:https://lyftr-ai-chatbot-iq5e.onrender.com/docs
- Local frontend: http://localhost:3000
- Local backend: http://localhost:8000

Public deployment and the assignment demo video still need hosting accounts, valid provider keys, and the student's voice recording. No public URLs are claimed until they are deployed and checked.

## 2. Run locally: with Docker and without

### Configuration

Copy `.env.example` to `.env` and replace the two placeholder values in `LLM_API_KEYS` with at least two valid keys for the same provider and model. Never commit `.env`. The default model is `gemini/gemini-3.1-flash-lite`; change `LLM_MODEL` if your provider keys belong to a different supported provider/model. Keep keys in the backend environment only.

Variables:

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEYS` | Comma-separated provider keys, tried in order and named `key_1`, `key_2`, etc. |
| `LLM_MODEL` | LiteLLM model identifier compatible with those keys. |
| `DATABASE_URL` | SQLite path; Docker default is `sqlite:////data/app.db`. |
| `ALLOWED_ORIGINS` | Comma-separated browser origins allowed by CORS. |
| `ENABLE_FAILURE_SIMULATION` | Enables the per-request failover demonstration header. |
| `DEFAULT_SYSTEM_PROMPT` | Default assistant instruction; optional override per session. |
| `VITE_API_URL` | Public API base URL embedded in the frontend build. |

### With Docker

Install Docker Desktop and GNU Make (or run the equivalent Docker commands). From the repository root:

```sh
cp .env.example .env
# Edit .env and provide two compatible provider API keys.
make up
```

The UI is at http://localhost:3000 and the API at http://localhost:8000. SQLite persists in the named `lyftr-data` volume mounted at `/data`.

```sh
make down
docker compose logs -f backend
```

The app starts without credentials so health and UI can be inspected, but chat calls return 503 until valid keys are configured. `make up` builds both images and starts the backend before the frontend health check passes.

### Without Docker

Use Python 3.12+ and Node 20+.

```powershell
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:LLM_API_KEYS="your_provider_key_1,your_provider_key_2" # PowerShell
$env:DATABASE_URL="sqlite:///./data/app.db"
$env:ALLOWED_ORIGINS="http://localhost:3000"
uvicorn app.main:app --reload --port 8000
```

On macOS/Linux, activate with `source .venv/bin/activate` and export the three environment variables before starting Uvicorn.

In another terminal:

```powershell
cd frontend
npm.cmd install
# Set VITE_API_URL=http://localhost:8000 in frontend/.env.local if needed.
npm.cmd run dev -- --port 3000
```

On macOS/Linux, use `npm install` and `npm run dev -- --port 3000`.

On macOS/Linux, use `export LLM_API_KEYS='key1,key2'`, `export DATABASE_URL='sqlite:///./data/app.db'`, and `export ALLOWED_ORIGINS='http://localhost:3000'` before starting FastAPI.

## 3. Design decisions: key fallback, caching, SQLite session storage

- **Key fallback:** `llm_service.py` tries each credential in order and advances for rate limiting, quota exhaustion, or 5xx errors. Keys need to be compatible with the configured LiteLLM model. The response exposes an identifier and fallback count, never a credential.
- **Caching:** LiteLLM's local cache uses the exact model request, including the system prompt and complete conversation, as its identity. Session IDs are not sent to LiteLLM, so the same initial prompt in a new session can hit cache. Simulated requests bypass cache.
- **SQLite:** The backend keeps turns in `messages`, with assistant metadata stored as JSON. `sessions` stores the optional system prompt privately. Turns are inserted only after successful inference, and session history is returned oldest first.
- **Latency and usage:** the backend measures completion time and returns LiteLLM prompt/completion token counts for that request. Cached responses preserve cached usage.
- **Failure simulation:** when enabled, `X-Simulate-Failure: key_1=429` skips key 1 in one request; `*=429` forces the clean all providers unavailable response. A successful fallback still calls a real model.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the diagram and [docs/INTERVIEW_GUIDE.md](docs/INTERVIEW_GUIDE.md) for detailed module descriptions.

## 4. Verification: how to see failover, cache hits and per-message token usage

Run the deterministic backend tests:

```sh
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

These tests mock provider completions and do not require live credentials. They verify request validation, history isolation, persistence, metadata handling, fallback behavior, CORS, and simulated failures. Live inference requires two valid compatible API keys.

Check health:

```sh
curl http://localhost:8000/health
```

Send a chat request, then repeat the same message with a new session ID. The first successful request should report `LIVE_INFERENCE`; the repeated exact request should report `LLM_CACHE`, preserve reply and token usage, and set `key_id` to null:

```sh
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"s-demo-1","message":"Explain caching in one sentence"}'
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"s-demo-2","message":"Explain caching in one sentence"}'
```

With `ENABLE_FAILURE_SIMULATION=true`, force a key-1 fallback:

```sh
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id":"s-fallback","message":"Give me a short greeting"}'
```

If two valid keys are configured, this should return a real model answer with `key_id: "key_2"` and `fallback_attempts: 1`. Force all keys to fail (this should return 503 and write no history):

```sh
curl -i -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id":"s-all-fail","message":"This turn should not be stored"}'
```

Read a completed session oldest first at `GET /sessions/{session_id}/messages`. Assistant responses in the UI show source, model, latency, input tokens, and output tokens alongside the corresponding message.

### Deployment instructions

1. Push the repository to GitHub. Create the backend service from [render.yaml](render.yaml), attach its persistent `/data` disk, and set `LLM_API_KEYS` to at least two compatible provider credentials. Set `ALLOWED_ORIGINS` to the deployed Vercel origin. Keep failure simulation enabled only when you intend to demonstrate the test hook.
2. Import `frontend/` into Vercel as a Vite project and set `VITE_API_URL` to the Render backend origin. Redeploy after setting it because Vite embeds this value at build time.
3. Visit `/health`, send a real request, check a cache hit, and exercise failure simulation before adding verified public URLs above.
4. Record and submit the requested 2–3 minute narrated demo through the assignment's submission form.

The included Render blueprint requires storage and environment values but cannot deploy without your Render account and provider credentials. Vercel and Render public URLs remain pending until deployment is completed and checked.

## 5. Setup Used: your editor and AI tools

Implementation environment: Visual Studio Code and OpenAI Codex. Claude Code and GitHub Copilot are also suitable development tools for this project.

## 6. Bonus features (if any)

- Session-specific system prompt support with private prompt storage.
- Per-turn latency, token, cache source, selected key, and fallback count display.
- A configurable failure simulation hook for safe failover demonstrations.
- Interview guide with architecture walkthrough and likely technical questions.
