# Mindbase — AI Knowledge Base

An AI-powered knowledge base that helps users organize documents, search for relevant information, and get answers based on their own knowledge base.

Built with **FastAPI, PostgreSQL, pgvector, React, and TypeScript**, the project combines document management, text embeddings, hybrid search, and retrieval-augmented generation (RAG).

## Features

- **Document management** — create, view, update, and delete documents.
- **File uploads** — import `.txt`, `.md`, `.pdf`, and `.docx` files with a 2 MB size limit; retain PDF page numbers and document section headings for source citations.
- **Hybrid retrieval** — combines semantic vector search and PostgreSQL full-text search over document chunks using Reciprocal Rank Fusion (RRF). Full-text retrieval combines PostgreSQL Russian and English dictionaries so both languages benefit from stemming; semantic retrieval is backed by a pgvector HNSW cosine index for scalable nearest-neighbor lookup.
- **Multi-query retrieval** — Gemini generates alternative query formulations; retrieval safely falls back to the original query if expansion is unavailable. Results from all formulations are fused with RRF.
- **RAG-based question answering** — retrieves relevant document chunks and passes them as context to Google Gemini.
- **Source references** — returns the document chunks used to generate an answer, including PDF page numbers and DOCX/Markdown section headings when available.
- **Relevance filtering** — filters out low-scoring semantic search results and limits duplicate or overly concentrated chunks.
- **Asynchronous backend** — uses FastAPI and SQLAlchemy's async API.
- **Database migrations** — manages schema changes with Alembic.
- **Account security** — Argon2id password hashing, short-lived access tokens, HttpOnly refresh cookies, refresh-token rotation and replay detection.
- **Session management** — revoke the current session on logout and list/revoke other active sessions.
- **Account recovery** — optional email verification, one-time password-reset links, and session revocation after password changes.
- **Abuse protection** — PostgreSQL-backed rate limits for authentication and recovery endpoints, shared across API workers.
- **Security audit trail** — records authentication and account-security events without storing passwords or raw action tokens.
- **Automated tests** — tests the API and application behavior with pytest.
- **Docker Compose** — provides a containerized development environment for the backend and database.

## Tech Stack

| Area | Technologies |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL, pgvector |
| Embeddings | Sentence Transformers |
| AI generation | Google Gemini API |
| Frontend | React, TypeScript, Vite |
| Migrations | Alembic |
| Testing | pytest, pytest-asyncio, HTTPX |
| Infrastructure | Docker, Docker Compose |

## Screenshots

### Main Interface

![Mindbase main interface](screenshots/home.png)

### API Documentation

![FastAPI interactive documentation](screenshots/api-docs.png)

## Architecture

```text
                    ┌──────────────────────┐
                    │   React + TypeScript │
                    │      Frontend        │
                    └──────────┬───────────┘
                               │ HTTP / REST
                    ┌──────────▼───────────┐
                    │       FastAPI        │
                    │      REST API        │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
       ┌─────────▼─────────┐      ┌──────────▼──────────┐
       │ Document Services │      │    Search / RAG     │
       │ Chunking, Storage │      │ Retrieval, Context  │
       └─────────┬─────────┘      └──────────┬──────────┘
                 │                           │
       ┌─────────▼───────────────────────────▼──────────┐
       │             PostgreSQL + pgvector              │
       │           Documents, Chunks, Embeddings        │
       └────────────────────────────────────────────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │    Google Gemini    │
                                    │   Answer Generation │
                                    └─────────────────────┘
```

### Search workflow

1. A user submits a natural-language query.
2. The application first checks for title matches.
3. Gemini optionally expands the query into a small set of alternative formulations.
4. Each formulation retrieves document chunks through semantic vector search and PostgreSQL full-text search.
5. Reciprocal Rank Fusion combines the ranked lists; duplicate chunks are removed and no document contributes more than two chunks.
6. The most relevant chunks are combined into context.
7. Google Gemini generates an answer based on that context.
8. The API returns the answer and its source chunks.

## Getting Started

### Prerequisites

- Python 3.13
- Node.js and npm
- Docker Desktop with Docker Compose
- Git
- A Google Gemini API key for AI-powered answers

### 1. Clone the repository

```bash
git clone https://github.com/eduardtavalbi/ai-knowledge-base.git
cd ai-knowledge-base
```

### 2. Configure environment variables

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Configure the following variables in `.env`:

```dotenv
APP_NAME=AI Knowledge Base API
DEBUG=false
AUTH_SECRET_KEY=GENERATE_A_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS
REFRESH_TOKEN_COOKIE_SECURE=false
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FRONTEND_PUBLIC_URL=http://localhost:5173
EMAIL_VERIFICATION_REQUIRED=false
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_STARTTLS=true
SMTP_USE_SSL=false
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5434/knowledge_base
POSTGRES_DB=knowledge_base
POSTGRES_USER=postgres
POSTGRES_PASSWORD=YOUR_PASSWORD
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.8-flash
```

Use your own credentials. Set a cryptographically random `AUTH_SECRET_KEY` of at least 32 characters and a non-default database password. Never commit `.env` or API keys. For local HTTP development, keep `REFRESH_TOKEN_COOKIE_SECURE=false`; set it to `true` behind HTTPS in production. Set `FRONTEND_ORIGINS` to the exact comma-separated origins serving the browser app (without trailing slashes). To require verified email addresses, set `EMAIL_VERIFICATION_REQUIRED=true` and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, and any required SMTP credentials; set `FRONTEND_PUBLIC_URL` to the public frontend URL.

Authentication abuse-protection defaults are 20 login attempts per IP and 8 per email/IP pair per 15 minutes; recovery endpoints allow 20 requests per IP and 4 per email/IP pair per hour; registration allows 10 attempts per IP per hour. Tune these values with the `AUTH_*` variables above. Counters are stored in PostgreSQL, so limits are shared across API workers. The API uses the direct client address and does not trust arbitrary forwarded-IP headers; configure trusted proxy handling at the deployment edge before placing it behind a reverse proxy. Security audit events store keyed digests of email, IP, and user-agent values rather than raw values, and never store passwords or action tokens. Rate-limit buckets older than 24 hours are cleaned up during authentication requests; define an operational retention policy for audit events before public deployment.

If you are upgrading a database that already contains documents, set `MIGRATION_OWNER_EMAIL` and `MIGRATION_OWNER_PASSWORD` before applying the ownership migration. The migration assigns all existing documents to this account; choose credentials you control. These variables are only needed for a database with existing documents.

### 3. Start the database

```powershell
docker compose up -d db
```

The database is exposed on `127.0.0.1:5434` only. The API is also bound to `127.0.0.1:8000`; neither service is exposed to other machines on the network. Docker Compose creates the persistent volume `ai_knowledge_base_vector_data` automatically on first startup.

### 4. Set up the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5. Apply database migrations

```powershell
python -m alembic upgrade head
```
Alembic uses the same `DATABASE_URL` from your `.env` file as the application. The migration runner automatically switches to the synchronous PostgreSQL driver required by Alembic; no manual URL edit is needed.

### 6. Start the backend

```powershell
python -m uvicorn app.main:app --reload
```

The API documentation is available at:

http://127.0.0.1:8000/docs

### 7. Start the frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173

If needed, configure `VITE_API_URL` in `frontend/.env.local` to point to the backend URL.

## Running Tests

From the project root, with the virtual environment activated:

```powershell
python -m pytest -v
```

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register an account |
| `POST` | `/auth/login` | Create a session and issue an access token |
| `POST` | `/auth/refresh` | Rotate the HttpOnly refresh cookie and issue a new access token |
| `POST` | `/auth/logout` | Revoke the current session |
| `GET` | `/auth/me` | Get the authenticated account |
| `POST` | `/auth/verify-email` | Verify an email using a one-time token |
| `POST` | `/auth/resend-verification` | Resend an email verification link |
| `POST` | `/auth/forgot-password` | Request a password reset link |
| `POST` | `/auth/reset-password` | Set a new password using a one-time token |
| `GET` | `/auth/sessions` | List the account's active sessions |
| `DELETE` | `/auth/sessions/{session_id}` | Revoke one of the account's sessions |
| `GET` | `/documents/` | List the current user's documents |
| `POST` | `/documents/` | Create a document |
| `GET` | `/documents/{id}` | Retrieve a document |
| `PUT` | `/documents/{id}` | Update a document |
| `DELETE` | `/documents/{id}` | Delete a document |
| `POST` | `/documents/upload` | Upload a `.txt`, `.md`, `.pdf`, or `.docx` file |
| `GET` | `/documents/search?q=...` | Search documents |
| `GET` | `/documents/search/chunks?q=...` | Search document chunks |
| `POST` | `/documents/ask` | Answer a question using retrieved context |

The frontend keeps the short-lived access token in memory and the API sets a rotating refresh token in an HttpOnly cookie. A page reload restores the session through `POST /auth/refresh`; refresh-token reuse revokes that session. Cookie-based authentication routes validate browser `Origin` values against `FRONTEND_ORIGINS`.

All document endpoints require `Authorization: Bearer <access_token>`. See the interactive API documentation at `/docs` for request schemas and response formats.

## Project Structure

```text
ai-knowledge-base/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── services/
├── alembic/
├── frontend/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Project Status

Mindbase is evolving into a multi-tenant commercial application. Each account owns a private document collection; document CRUD, deduplication, hybrid retrieval, and RAG context are scoped to the authenticated user.

## Security Notes

- Keep API keys and credentials in local environment files.
- Do not commit `.env`, database backups, or other sensitive files.
- Use `.env.example` as a template with placeholder values only.
- Document endpoints require a bearer access token. Passwords are hashed with Argon2id; JWT access tokens expire after 30 minutes.
- Every document query and retrieval path is scoped by the authenticated owner. Identical content can exist in separate accounts without cross-account deduplication.
- Session refresh, token rotation/replay detection, logout, per-session revocation, email verification, and password reset are implemented. Before public commercial deployment, still add production secret management, monitoring/alerting, and operational retention policies for security logs.
- Docker Compose binds the API and database ports to loopback and requires an explicit `POSTGRES_PASSWORD`; do not replace this with a default or weak password.
