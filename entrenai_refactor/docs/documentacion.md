# Documentación Técnica y Registro de Cambios - EntrenAI Refactorizado

Este documento detalla la estructura técnica, la configuración y el registro de cambios del proyecto EntrenAI refactorizado.

## Registro de Cambios (Refactorización)

-   **General**: Inicio de la refactorización para simplificar el código, mejorar la organización, traducir todo a español y seguir buenas prácticas de desarrollo en Python.
-   **Estructura del Proyecto**:
    -   El directorio `core/` ha sido renombrado a `nucleo/` para reflejar la terminología en español.
    -   Los archivos de infraestructura principales (`Dockerfile`, `Dockerfile.celery`, `docker-compose.yml`, `Makefile`) han sido adaptados desde la raíz del proyecto original y ahora residen y se gestionan desde dentro de `entrenai_refactor/`.
    -   Los archivos de requisitos (`requirements.txt`, `requirements.celery.txt`) han sido consolidados y actualizados, también ubicados en `entrenai_refactor/`.
-   **Documentación**:
    -   `README.md` actualizado para reflejar la nueva estructura y modo de uso.
    -   Este archivo (`documentacion.md`) creado para servir como documentación técnica centralizada y registro de cambios del refactor.
-   _(Más cambios se añadirán aquí a medida que avance la refactorización)_

## Estructura del Proyecto (`entrenai_refactor/`)

La estructura del directorio `entrenai_refactor/` es la siguiente:

-   `api/`: Contiene todos los endpoints y la lógica de la API desarrollada con FastAPI.
    -   `rutas/`: Módulos específicos para diferentes grupos de rutas.
    -   `estaticos/`: Archivos estáticos (HTML, JS, CSS) para interfaces de usuario simples.
    -   `modelos.py`: Modelos Pydantic para la validación de datos de entrada/salida.
    -   `principal.py`: Punto de entrada principal de la aplicación FastAPI.
-   `nucleo/`: El corazón de la aplicación, con la lógica de negocio.
    -   `archivos/`: Lógica para el procesamiento y manejo de archivos.
    -   `bd/`: Interacción con la base de datos (ej. PGVector).
        - `init.sql`: Script de inicialización para la base de datos pgvector (usado por Docker Compose).
    -   `clientes/`: Clientes para interactuar con servicios externos (Moodle, N8N).
    -   `ia/`: Componentes relacionados con la inteligencia artificial (gestor de IA, modelos, etc.).
-   `config/`: Configuración de la aplicación y logging.
    -   `configuracion.py`: Carga y gestión de variables de entorno y configuraciones.
    -   `registrador.py`: Configuración del sistema de logging.
-   `celery/`: Tareas asíncronas con Celery.
    -   `aplicacion_celery.py`: Creación y configuración de la aplicación Celery.
    -   `tareas.py`: Definición de las tareas asíncronas.
-   `docs/`: Esta misma documentación.
-   `Dockerfile`: Para construir la imagen Docker de la aplicación API.
-   `Dockerfile.celery`: Para construir la imagen Docker del worker Celery.
-   `docker-compose.yml`: Orquestación de todos los servicios (API, worker, BDs, etc.).
-   `Makefile`: Comandos para facilitar tareas de desarrollo (instalar, correr, Docker).
-   `requirements.txt`: Dependencias Python para la API.
-   `requirements.celery.txt`: Dependencias Python para el worker Celery.
-   `README.md`: Descripción general del proyecto refactorizado y guía de inicio rápido.

## Cómo levantar el sistema

Para ejecutar el sistema, asegúrate de estar en el directorio `entrenai_refactor/`.

### Usando Makefile (Recomendado)

El `Makefile` local (`entrenai_refactor/Makefile`) es la forma preferida de gestionar el ciclo de vida de la aplicación:

1.  **Instalar dependencias (desarrollo local):**
    ```bash
    make instalar
    ```
    Esto crea un entorno virtual en `.venv/` e instala `requirements.txt`.

2.  **Ejecutar la API (desarrollo local):**
    ```bash
    make correr
    ```
    Inicia Uvicorn con recarga. Requiere un `.env` en el directorio raíz del proyecto (`../.env`).

3.  **Ejecutar el worker Celery (desarrollo local):**
    ```bash
    make correr-worker-celery
    ```
    Inicia el worker. También requiere `../.env`.

4.  **Levantar todos los servicios con Docker Compose:**
    ```bash
    make servicios-levantar
    ```
    Usa `docker-compose.yml` para construir e iniciar todos los contenedores.

5.  **Detener los servicios Docker Compose:**
    ```bash
    make servicios-bajar
    ```

### Usando Docker Compose directamente

Desde el directorio `entrenai_refactor/`:

```bash
docker compose up --build -d # Para levantar servicios en segundo plano
docker compose down          # Para detener servicios
docker compose logs -f       # Para ver logs
```
Recuerda que el archivo `docker-compose.yml` está configurado para buscar el archivo `.env` en el directorio padre (`../.env`).

## Integración IA-Moodle
- El sistema permite a un profesor de Moodle tener una carpeta de archivos y, por detrás, se arma una inteligencia personalizada usando una base de datos vectorial (pgvector en Postgres).
- El worker Celery gestiona colas y delega tareas a la API principal vía HTTP para el procesamiento de archivos y otras operaciones intensivas.
- El frontend (a través de `api/estaticos/`) es simple y está completamente en español.

## Endpoints principales (Sujetos a revisión durante el refactor)
La API se expone bajo el prefijo `/api/v1`.
- `/salud`: Chequeo de salud básico del servicio API.
- `/cursos`: Listar cursos disponibles desde Moodle para el usuario autenticado.
- `/cursos/{curso_id}/configurar-ia`: Endpoint para iniciar la configuración de la IA para un curso específico. Esto puede implicar la creación de estructuras en Moodle y la preparación para la indexación de archivos.
- `/cursos/{curso_id}/archivos-indexados`: Devuelve una lista de los archivos que han sido procesados e indexados para un curso.
- `/cursos/{curso_id}/refrescar-archivos`: Dispara una tarea para volver a procesar los archivos asociados a un curso, útil si los contenidos en Moodle han cambiado.
- `/tareas/{tarea_id}/estado`: Consulta el estado de una tarea asíncrona (ej. procesamiento de archivos).
- `/cursos/{curso_id}/flujo-n8n`: Podría estar relacionado con la configuración o visualización de flujos de trabajo en N8N asociados al curso. (Este endpoint puede ser revisado o redefinido).

*(Esta sección de endpoints se actualizará a medida que la API se estabilice en la refactorización).*
