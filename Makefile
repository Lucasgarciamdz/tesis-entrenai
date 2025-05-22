# Makefile for Entrenai Project

# Default Python interpreter
PYTHON = python3

# Virtual environment directory
VENV_DIR = .venv
VENV_ACTIVATE = . $(VENV_DIR)/bin/activate

# Default FastAPI run command
RUN_ARGS = --host $(shell grep FASTAPI_HOST .env | cut -d '=' -f2) --port $(shell grep FASTAPI_PORT .env | cut -d '=' -f2)

.PHONY: help setup run test lint docs clean services-up services-down services-logs services-restart

help:
	@echo "Available commands:"
	@echo "  setup          : Create virtual environment and install dependencies"
	@echo "  run            : Run the FastAPI application"
	@echo "  test           : Run pytest tests"
	@echo "  lint           : Run linters (e.g., flake8, black) - (Placeholder)"
	@echo "  docs           : Generate documentation (e.g., Sphinx) - (Placeholder)"
	@echo "  clean          : Remove virtual environment and __pycache__ directories"
	@echo "  services-up    : Start Docker Compose services in detached mode"
	@echo "  services-down  : Stop Docker Compose services"
	@echo "  services-logs  : View logs for Docker Compose services"
	@echo "  services-restart: Restart Docker Compose services"
	@echo "  run-celery-worker: Run a Celery worker locally"

setup: $(VENV_DIR)/bin/activate
$(VENV_DIR)/bin/activate: requirements.txt
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_ACTIVATE); pip install --upgrade pip
	$(VENV_ACTIVATE); pip install -r requirements.txt
	@echo "Virtual environment created and dependencies installed."
	@touch $(VENV_DIR)/bin/activate

run: $(VENV_DIR)/bin/activate .env
	@echo "Starting FastAPI application..."
	$(VENV_ACTIVATE); uvicorn src.entrenai.api.main:app $(RUN_ARGS)

run-celery-worker: $(VENV_DIR)/bin/activate .env
	@echo "Starting Celery worker..."
	$(VENV_ACTIVATE); celery -A src.entrenai.celery_app.app worker -l INFO -P eventlet

test: $(VENV_DIR)/bin/activate
	@echo "Running tests..."
	$(VENV_ACTIVATE); pytest

lint: $(VENV_DIR)/bin/activate
	@echo "Running linters... (Not yet implemented)"
	# $(VENV_ACTIVATE); flake8 src tests
	# $(VENV_ACTIVATE); black src tests --check

docs:
	@echo "Generating documentation... (Not yet implemented)"
	# cd docs && $(MAKE) html

clean:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@echo "Cleaned up virtual environment and cache files."

# Docker Compose commands
services-up: .env
	@echo "Starting Docker services..."
	docker compose up -d --remove-orphans --build

services-down:
	@echo "Stopping Docker services..."
	docker compose down

services-logs:
	@echo "Showing Docker service logs..."
	docker compose logs -f

services-restart: services-down services-up

# Ensure .env exists for commands that need it
.env:
	@echo "Error: .env file not found. Please copy .env.example to .env and configure it."
	@exit 1
