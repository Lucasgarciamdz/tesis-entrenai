# Refactor de EntrenAI

Este proyecto es una reescritura completa y simplificada de la aplicación original, orientada a la gestión de inteligencia artificial personalizada para cátedras de Moodle. Todo el código, documentación y estructura están en español.

## Estructura principal
- `api/`: Endpoints y lógica de la API (FastAPI)
- `core/`: Núcleo de lógica de IA, clientes externos, base de datos y procesamiento de archivos
- `config/`: Configuración y logs
- `celery/`: Tareas asíncronas y gestión de colas
- `docs/`: Documentación y ejemplos
- `docker/`, `Dockerfile*`, `Makefile`, `requirements*`: Infraestructura y dependencias

## Objetivo
Simplificar el código, mejorar la organización y mantener toda la funcionalidad, con todo en español y siguiendo buenas prácticas de Python. 