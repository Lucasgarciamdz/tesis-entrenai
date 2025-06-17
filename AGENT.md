# Entrenai Development Guide

## Commands
- **Test**: `make test` or `pytest` (for single test: `pytest tests/unit/core/test_file_processor.py::test_txt_file_processor_extract_text`)
- **Build/Run**: `make run` (FastAPI) or `uvicorn src.entrenai.api.main:app --reload`
- **Services**: `make services-up` (starts Docker services), `make services-down` (stops)
- **Celery**: `make run-celery-worker` or `celery -A src.entrenai.celery_app.app worker -l INFO -P eventlet`

## Architecture
Modular RAG system with: FastAPI API (`src/entrenai/api/`), Moodle integration (`src/entrenai/core/clients/moodle_client.py`), Pgvector DB (`src/entrenai/core/db/pgvector_wrapper.py`), Ollama LLMs (`src/entrenai/core/ai/ollama_wrapper.py`), N8N workflows (`src/entrenai/core/clients/n8n_client.py`), Celery tasks (`src/entrenai/core/tasks.py`), Redis broker. Docker services: Moodle, PostgreSQL, Pgvector, Ollama, N8N, Redis.

## Code Style
- **Language**: User-facing text in Spanish, internal code in English
- **Python**: Strict PEP 8, type hints mandatory, Google-style docstrings in Spanish
- **Imports**: Use `httpx` for HTTP, prefer f-strings, modular design
- **Error handling**: Comprehensive with Spanish messages for users
- **Testing**: pytest, unit tests required for new features
- **Git**: Spanish commit messages, atomic commits, conventional format (`feat:`, `fix:`, `docs:`, etc.)

## File Structure
- `src/entrenai/api/`: FastAPI endpoints and routers
- `src/entrenai/core/`: Core business logic (ai/, clients/, db/, files/, tasks.py)
- `src/entrenai/config/`: Configuration management
- `tests/unit/`: Unit tests, `tests/integration/`: Integration tests
