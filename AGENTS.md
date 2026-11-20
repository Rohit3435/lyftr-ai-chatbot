# Lyftr AI Chatbot — Agent Instructions

## Project goals

Build the Lyftr AI Chatbot according to the user's assignment requirements. The intended stack is React with Vite, Python with FastAPI, LiteLLM, SQLite, Docker, Docker Compose, Git, and GitHub.

## Before making changes

- Inspect the existing repository, its Git status, and relevant files before modifying anything.
- Find and read the uploaded assignment requirements before implementing application behavior. Treat its API contracts, required fields, response shapes, status codes, and feature requirements as authoritative. Do not invent or silently change an exact contract. If the assignment is not available in the workspace, report that clearly and proceed only with work that does not depend on missing details.
- Preserve existing user work. Do not overwrite unrelated files or discard uncommitted changes.
- Work in small, reviewable milestones. Explain material implementation choices and run relevant automated checks after implementation; fix failures before moving to the next milestone.

## Required application capabilities

When implementing the application, satisfy the assignment requirements for:

- A React + Vite frontend and a Python + FastAPI backend.
- LiteLLM integration with at least two API keys and automatic failover between configured keys.
- Built-in response caching and multi-turn conversation history.
- SQLite persistence.
- Per-request token usage and latency tracking.
- Exact assignment API contracts.
- Docker and Docker Compose configuration.
- Automated backend tests, deployment configuration, and a useful README.

Do not use fake or placeholder implementations for mandatory features. Keep credentials out of source code and logs; load secrets from environment configuration and document required variables without publishing their values.

## Git and secrets

- Use conventional commit messages for successfully tested milestones, and report every commit hash.
- Never commit secrets, .env files, or other credential material. Keep safe templates such as .env.example free of real values.
- Never force-push, never delete existing user work, and never push to GitHub without the user's explicit approval.
- Inspect git status before committing and ensure only intended files are included.

## Quality and communication

- Keep changes scoped to the current requested milestone; do not build application features when the user has asked only for repository setup.
- Do not claim tests or checks passed unless they were actually run. Report changes, checks, and limitations clearly.
