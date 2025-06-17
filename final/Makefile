# Makefile simplificado para EntrenAI

.PHONY: help install dev run test clean services-up services-down

help:
	@echo "Comandos disponibles:"
	@echo "  install       - Instalar dependencias"
	@echo "  dev          - Ejecutar en modo desarrollo"
	@echo "  run          - Ejecutar API"
	@echo "  test         - Ejecutar tests"
	@echo "  services-up  - Levantar servicios Docker"
	@echo "  services-down - Bajar servicios Docker"
	@echo "  clean        - Limpiar archivos temporales"

install:
	pip install -r requirements.txt

dev:
	uvicorn src.entrenai.api.main:app --reload --host 0.0.0.0 --port 8000

run:
	uvicorn src.entrenai.api.main:app --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

services-up:
	docker-compose up -d postgres redis

services-down:
	docker-compose down

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f entrenai

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
