# Mindbase — AI Knowledge Base

An AI-powered knowledge base that helps users organize documents, search for relevant information, and get answers based on their own knowledge base.

Built with **FastAPI, PostgreSQL, pgvector, React, and TypeScript**, the project combines document management, text embeddings, hybrid search, and retrieval-augmented generation (RAG).

## Features

- **Document management** — create, view, update, and delete documents.
- **File uploads** — import `.txt` and `.md` files with UTF-8 validation and a 2 MB size limit.
- **Hybrid search** — combines title matching, PostgreSQL full-text search, and semantic search as a fallback.
- **Semantic search** — represents text with multilingual embeddings and uses pgvector cosine distance to find relevant content.
- **RAG-based question answering** — retrieves relevant document chunks and passes them as context to Google Gemini.
- **Source references** — returns the document chunks used to generate an answer.
- **Relevance filtering** — filters out low-scoring semantic search results and limits duplicate or overly concentrated chunks.
- **Asynchronous backend** — uses FastAPI and SQLAlchemy's async API.
- **Database migrations** — manages schema changes with Alembic.
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
3. If no results are found, PostgreSQL full-text search is used.
4. If that also returns no results, semantic search ranks document chunks by cosine distance.
5. For question answering, the most relevant chunks are combined into context.
6. Google Gemini generates an answer based on that context.
7. The API returns the answer and its source chunks.

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
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5434/knowledge_base
POSTGRES_DB=knowledge_base
POSTGRES_USER=postgres
POSTGRES_PASSWORD=YOUR_PASSWORD
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash
```

Use your own credentials. Never commit `.env` or API keys.

### 3. Start the database

```powershell
docker compose up -d db
```

The database is exposed on port `5434` on the host. The Compose configuration uses an external Docker volume named `ai_knowledge_base_vector_data`; make sure this volume exists before starting the database.

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
Alembic uses the database connection configured in alembic.ini. Make sure its URL points to your local PostgreSQL instance before running migrations.

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
| `GET` | `/documents/` | List documents |
| `POST` | `/documents/` | Create a document |
| `GET` | `/documents/{id}` | Retrieve a document |
| `PUT` | `/documents/{id}` | Update a document |
| `DELETE` | `/documents/{id}` | Delete a document |
| `POST` | `/documents/upload` | Upload a `.txt` or `.md` file |
| `GET` | `/documents/search?q=...` | Search documents |
| `GET` | `/documents/search/chunks?q=...` | Search document chunks |
| `POST` | `/documents/ask` | Answer a question using retrieved context |

See the interactive API documentation at `/docs` for request schemas and response formats.

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

Mindbase is an ongoing personal project focused on backend development, semantic retrieval, and AI-powered knowledge management.

## Security Notes

- Keep API keys and credentials in local environment files.
- Do not commit `.env`, database backups, or other sensitive files.
- Use `.env.example` as a template with placeholder values only.
