# AI Knowledge Base API

An AI-powered knowledge base API built with FastAPI, PostgreSQL, pgvector, and SQLAlchemy.

## Features

- Create, retrieve, update, and delete documents
- Upload `.txt` and `.md` files
- Semantic search using multilingual text embeddings
- PostgreSQL storage with pgvector
- Database migrations with Alembic
- Automated tests with pytest

## Tech Stack

- Python
- FastAPI
- SQLAlchemy (async)
- PostgreSQL
- pgvector
- Sentence Transformers
- Alembic
- Docker Compose
- pytest

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/eduardtavalbi/ai-knowledge-base.git
cd ai-knowledge-base
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file based on `.env.example` and adjust the database connection settings if needed.

### 5. Start PostgreSQL with pgvector

```powershell
docker compose up -d db
```

### 6. Apply database migrations

```powershell
python -m alembic upgrade head
```

### 7. Start the API

```powershell
uvicorn app.main:app --reload
```

The API documentation is available at:

http://127.0.0.1:8000/docs

## Running Tests

```powershell
python -m pytest
```

## Project Status

This project is under active development.