# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Babalar** is a RAG-powered chatbot for a Turkish expatriate WhatsApp community in Munich. Users ask questions in Turkish about daily life (housing, cars, bureaucracy, etc.) and receive AI-generated answers sourced from historical community WhatsApp messages.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy (async) |
| Database | PostgreSQL 16 + pgvector (1536-dim HNSW index) |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS + Zustand |
| Ingestion | Node.js 20 + whatsapp-web.js + node-cron |
| LLM | OpenAI GPT-4o-mini (chat + categorization) + text-embedding-3-small |
| Infra | AWS (EC2, RDS, CloudFront, S3) + CDK (Python) |

## Development Commands

```bash
# Start all services (postgres, backend, ingestion, frontend)
docker compose up -d

# Run DB migrations (required after first start or schema changes)
docker compose exec backend alembic upgrade head

# Create admin user + first invite code
docker compose exec backend python -m app.cli setup

# View logs
docker compose logs -f [backend|ingestion|frontend]

# Frontend dev only (if running outside Docker)
cd babalar-frontend && npm install && npm run dev

# Infrastructure deploy
cd infrastructure && cdk deploy --all
```

**Local URLs**:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/docs

## Architecture

Three independent services communicate via HTTP:

```
[React Frontend] → [FastAPI Backend :8000] → [PostgreSQL + pgvector]
                                             ↑
                  [Node.js Ingestion] ────────┘ (via /api/ingest/*)
```

### Backend (`babalar-backend/app/`)

Strict **API → Service → Model** layering:

- `api/` — FastAPI route handlers, no business logic
  - `auth.py` — registration (invite-code gated), login, token refresh
  - `chat.py` — RAG query, usage counters, category listing
  - `admin.py` — invite code management, config, user/group admin
  - `ingest.py` — internal endpoint authenticated via `INGEST_API_KEY`
- `services/` — all business logic lives here
  - `rag.py` — full RAG pipeline: scope check → vector search → LLM answer
  - `categorizer.py` — batch GPT-4o-mini categorization of incoming messages
  - `embedding.py` — OpenAI embedding wrapper
  - `rate_limiter.py` — PostgreSQL-backed daily per-user and global counters
- `models/models.py` — SQLAlchemy ORM (User, Message, WaGroup, AdminConfig, etc.)
- `config.py` — Pydantic `Settings` loading all env vars

### RAG Pipeline (`services/rag.py`)

1. **Scope check** (GPT-4o-mini) — reject off-topic questions early
2. **Embed question** — `text-embedding-3-small`
3. **pgvector search** — top-K messages by cosine similarity
4. **LLM answer** — GPT-4o-mini answers based strictly on retrieved context

Dynamic config (stored in `admin_config` table): `rag_top_k`, `user_daily_limit`, `total_daily_limit`.

### Ingestion Service (`babalar-ingestion/src/index.js`)

Runs on cron `0 2 * * *` (UTC). Flow:
1. Connect to WhatsApp Web via persistent session (Docker volume)
2. Discover all groups → POST to `/api/ingest/groups`
3. Fetch messages since `last_ingested_at` per group
4. POST batches to `/api/ingest/messages`
5. Backend: categorize → embed → insert with HNSW index update

### Frontend (`babalar-frontend/src/`)

- Zustand store in `store/auth` for JWT token management (access + refresh)
- `PrivateRoute` / `AdminRoute` guards in `App.tsx`
- Pages: `LoginPage`, `RegisterPage`, `ChatPage`, `AdminPage`

## Configuration

Copy `.env.example` → `.env` before first run. Critical variables:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Required for embeddings + LLM |
| `JWT_SECRET` | Must be 32+ random chars |
| `INGEST_API_KEY` | Shared secret between ingestion ↔ backend |
| `DATABASE_URL` | asyncpg URL (`postgresql+asyncpg://...`) |

## Database Migrations

Migrations are in `babalar-backend/alembic/versions/`. Always run `alembic upgrade head` after pulling schema changes. Generate new migrations with:

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
```

## AWS Infrastructure

CDK stacks in `infrastructure/`:
- `VpcStack` → VPC, private subnets, security groups
- `DatabaseStack` → RDS db.t4g.micro PostgreSQL 16 (private subnet)
- `BackendStack` → EC2 t4g.small, ALB, Docker Compose
- `FrontendStack` → S3 + CloudFront (geo-restricted to Germany)

Secrets must be created in AWS Secrets Manager before CDK deploy: `babalar/db-password`, `babalar/openai-api-key`, `babalar/jwt-secret`, `babalar/ingest-api-key`.

## Testing

No test suite exists yet. `pytest>=8` and `pytest-asyncio>=0.24` are in `pyproject.toml` optional deps. When adding tests, place them under `babalar-backend/app/tests/` and use `pytest-asyncio` for async service tests with a real test database.
