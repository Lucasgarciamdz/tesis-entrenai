# Documentación de EntrenAI Refactorizado

## Estructura del proyecto
- `api/`: Endpoints y lógica de la API (FastAPI)
- `core/`: Núcleo de lógica de IA, clientes externos, base de datos y procesamiento de archivos
- `config/`: Configuración y logs
- `celery/`: Tareas asíncronas y gestión de colas
- `docs/`: Documentación y ejemplos
- Infraestructura: Docker, Makefile, requirements

## Cómo levantar el sistema

1. Instalar dependencias:
   ```
   pip install -r requirements.txt
   pip install -r requirements.celery.txt
   ```
2. Levantar la app principal:
   ```
   make iniciar
   ```
3. Levantar el worker de Celery:
   ```
   make iniciar-celery
   ```
4. (Opcional) Usar Docker Compose:
   ```
   docker-compose up --build
   ```

## Integración IA-Moodle
- El sistema permite a un profesor de Moodle tener una carpeta de archivos y, por detrás, se arma una inteligencia personalizada usando una base de datos vectorial (pgvector en Postgres).
- El worker Celery solo gestiona colas y delega tareas a la API principal vía HTTP.
- El frontend es simple y en español.

## Endpoints principales
- `/api/v1/salud`: Chequeo de salud
- `/api/v1/cursos`: Listar cursos de Moodle
- `/api/v1/cursos/{curso_id}/configurar-ia`: Configurar IA para un curso
- `/api/v1/cursos/{curso_id}/archivos-indexados`: Listar archivos indexados
- `/api/v1/cursos/{curso_id}/refrescar-archivos`: Refrescar archivos indexados
- `/api/v1/tareas/{tarea_id}/estado`: Estado de tarea
- `/api/v1/cursos/{curso_id}/flujo-n8n`: Configuración de flujo N8N 