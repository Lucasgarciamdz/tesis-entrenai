# Documentación Técnica y Registro de Cambios - EntrenAI Refactorizado

Este documento detalla la estructura técnica, la configuración y el registro de cambios del proyecto EntrenAI refactorizado.

## Registro de Cambios

### Refactorización Principal (Completa a Fecha de la Última Refactorización)

Esta sección resume los cambios más significativos realizados durante la refactorización completa del proyecto en el directorio `entrenai_refactor`.

*   **Estructura del Proyecto y Autocontención:**
    *   Todo el código fuente, configuración, Dockerfiles, Makefile y documentación relevante del proyecto se han consolidado dentro del directorio `entrenai_refactor` para que sea autocontenido.
    *   Los archivos de entorno (`.env.example`, `.env.docker`) y de ignorar Docker (`.dockerignore`) ahora residen y se gestionan desde `entrenai_refactor`.
    *   Los Dockerfiles y `docker-compose.yml` han sido actualizados para funcionar correctamente desde el contexto de `entrenai_refactor`.

*   **Traducción Integral al Español:**
    *   Todo el código fuente (nombres de variables, funciones, clases, métodos), comentarios y docstrings han sido traducidos al español.
    *   Los modelos Pydantic (en `api/modelos.py`) y sus descripciones de campos están en español.
    *   Los mensajes de log y las respuestas de error de la API se han traducido al español.
    *   Los archivos estáticos HTML (`api/estaticos/`) ya se encontraban mayormente en español.

*   **Mejoras en Configuración y Logging:**
    *   Configuración centralizada en `config/configuracion.py` (`configuracion_global`), cargando desde `entrenai_refactor/.env`. Todos los campos de configuración fueron traducidos al español, lo que requirió actualizar sus referencias en todo el proyecto.
    *   Sistema de logging mejorado y estandarizado mediante `config/registrador.py`, configurable mediante `configuracion_global.nivel_registro_log`.

*   **Refactorización del Núcleo (`nucleo/`):**
    *   **Clientes (`nucleo/clientes/`):** `ClienteMoodle` y `ClienteN8N` refactorizados, traducidos, con mejor manejo de errores y uso de `configuracion_global`. Lógica de plantillas N8N verificada.
    *   **Base de Datos (`nucleo/bd/`):** `EnvoltorioPgVector` refactorizado, traducido, con manejo de errores mejorado y uso de `configuracion_global`. Script `init.sql` actualizado.
    *   **Inteligencia Artificial (`nucleo/ia/`):**
        *   `EnvoltorioGemini` y `EnvoltorioOllama` refactorizados, traducidos, con manejo de errores y logging mejorados, y uso de `configuracion_global`.
        *   `GestorEmbeddings` y `ProveedorInteligencia` refactorizados y traducidos, asegurando la correcta interacción y selección de proveedores de IA.
        *   `UtilidadesComunesIA` refactorizadas y traducidas.
    *   **Archivos (`nucleo/archivos/`):** `ProcesadorArchivos` (ahora `GestorMaestroDeProcesadoresArchivos` con `ProcesadorArchivoInterfaz` y procesadores específicos) refactorizado, traducido, con manejo de errores mejorado para diversos tipos de archivo.

*   **Refactorización de la API (`api/`):**
    *   `principal.py`: Código de inicio de FastAPI, configuración de CORS, inclusión de routers y montaje de archivos estáticos revisado y traducido.
    *   `rutas/`: Todos los endpoints en `ruta_busqueda.py`, `ruta_configuracion_curso.py`, y `ruta_procesamiento_interno.py` han sido traducidos (nombres de funciones, parámetros, variables, respuestas de error), y actualizados para usar los modelos Pydantic y componentes del núcleo refactorizados.
    *   `modelos.py`: Modelos Pydantic completamente traducidos (nombres de clases y campos, descripciones).

*   **Refactorización de Celery (`celery/`):**
    *   `aplicacion_celery.py`: Configuración de la app Celery actualizada para usar `configuracion_global.celery` y con nombres/logging en español.
    *   `tareas.py`: Tareas de Celery simplificadas para delegar la lógica de procesamiento principal a la API de FastAPI mediante peticiones HTTP, con manejo de errores y logging mejorados.

*   **Documentación (`README.md`, `docs/documentacion.md`):**
    *   `README.md` actualizado para reflejar la nueva estructura, instrucciones de configuración y ejecución dentro de `entrenai_refactor`.
    *   Este archivo (`docs/documentacion.md`) sirve como registro de cambios detallado.

---
## Registro de Cambios (Refactorización Inicial - Previo)

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
