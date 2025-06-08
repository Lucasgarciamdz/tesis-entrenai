# EntrenAI - Refactorización del Proyecto

Este proyecto es una reescritura y mejora de la aplicación original Entrenai, enfocada en la gestión de inteligencia artificial personalizada para cursos en la plataforma Moodle. Todo el código, la documentación interna y la estructura del proyecto están en español.

## Entrenai: Asistente Inteligente para Cursos en Moodle (Descripción General)

Entrenai es una herramienta innovadora diseñada para asistir a estudiantes y docentes en Moodle. Funciona como un asistente personal para cada curso: Entrenai analiza los materiales de estudio proporcionados por el docente (documentos PDF, Word, PowerPoint, etc.) y luego responde las preguntas de los estudiantes basándose exclusivamente en dicha información.

**Objetivo Principal de Entrenai:** Facilitar a los estudiantes el acceso rápido y sencillo a la información que necesitan, directamente desde Moodle, a través de una interfaz de chat intuitiva. Esto promueve una mejor comprensión de los temas del curso y permite a los docentes ofrecer un apoyo continuo y eficiente.

## Objetivos de esta Refactorización

La refactorización de Entrenai busca:
*   Simplificar y modernizar la base de código original.
*   Mejorar la organización y modularidad del proyecto.
*   Mantener y optimizar la funcionalidad clave de Entrenai.
*   Estandarizar el idioma del código, comentarios y documentación interna al español.
*   Adherirse a las mejores prácticas de desarrollo en Python y FastAPI.
*   Facilitar el mantenimiento futuro y la escalabilidad del proyecto.

## Estructura del Proyecto (`entrenai_refactor/`)

El proyecto refactorizado se organiza de la siguiente manera dentro del directorio `entrenai_refactor/`:

-   `api/`: Contiene todos los endpoints HTTP y la lógica de la API REST, desarrollada con FastAPI. Es el punto de entrada principal para las interacciones con el sistema.
    -   `rutas/`: Módulos que definen los diferentes grupos de rutas (endpoints).
    -   `modelos.py`: Define los modelos de datos Pydantic para la validación de solicitudes y respuestas.
    -   `principal.py`: Archivo principal de la aplicación FastAPI, donde se inicializa y configura la API.
    -   `estaticos/`: Archivos para una interfaz de usuario web simple (HTML, JS, CSS).
-   `nucleo/`: Es el corazón de la aplicación ("core"). Aquí reside la lógica de negocio y las funcionalidades principales:
    *   `ia/`: Componentes para la interacción con modelos de Inteligencia Artificial (Ollama, Gemini), gestión de embeddings, etc.
    *   `clientes/`: Clientes para comunicarse con servicios externos como Moodle y N8N.
    *   `bd/`: Lógica para la interacción con la base de datos vectorial (PGVector).
    *   `archivos/`: Utilidades para el procesamiento y extracción de texto de diversos tipos de archivos.
-   `config/`: Módulos para la carga de la configuración de la aplicación (desde variables de entorno y archivos `.env`) y para la configuración del sistema de logging.
-   `celery/`: Implementación de tareas asíncronas utilizando Celery y Redis. Permite que procesos largos (como el procesamiento de documentos de un curso) se ejecuten en segundo plano sin bloquear la API.
    *   `aplicacion_celery.py`: Configuración de la instancia de Celery.
    *   `tareas.py`: Definición de las tareas asíncronas.
-   `docs/`: Contiene documentación técnica adicional, como este `README.md` y el `documentacion.md` (changelog/resumen de refactorización).
-   `Dockerfile`, `Dockerfile.celery`: Archivos para construir las imágenes Docker para la aplicación API y el worker de Celery.
-   `docker-compose.yml`: Define y orquesta los servicios, redes y volúmenes para desplegar la aplicación completa (API, worker, bases de datos, N8N, etc.) utilizando Docker Compose.
-   `Makefile`: Proporciona comandos de utilidad para desarrolladores (ej. `make instalar`, `make levantar-servicios`).
-   `requirements.txt`, `requirements.celery.txt`: Listas de dependencias Python.
-   `.env.example`, `.env.docker`: Archivos de ejemplo para las variables de entorno.

## Funcionalidades Clave de Entrenai

*   **Integración con Moodle:** Activación selectiva de Entrenai para cursos específicos, preparando automáticamente el entorno en Moodle.
*   **Procesamiento de Documentos:** Extracción de texto de diversos formatos de archivo (PDF, DOCX, PPTX, TXT, MD).
*   **Base de Conocimiento Vectorial:** Almacenamiento inteligente de la información extraída para búsquedas semánticas eficientes.
*   **Chatbot Interactivo:** Interfaz de chat para que los estudiantes realicen preguntas y reciban respuestas contextualizadas basadas en el material del curso.
*   **Interfaz de Gestión:** Panel para que los docentes configuren la IA para sus cursos y supervisen los archivos procesados.

## Flujo de Funcionamiento Simplificado

**Para el Docente:**
1.  **Configuración Inicial:** Desde el panel de Entrenai, selecciona un curso de Moodle. Con un clic, el sistema configura la sección de IA en Moodle, incluyendo una carpeta para documentos y enlaces al chat y herramientas de refresco.
2.  **Carga de Materiales:** Sube los archivos del curso a la carpeta designada en Moodle.
3.  **Procesamiento:** Solicita a Entrenai que procese los archivos. Esto puede ser una acción manual (ej. "refrescar") o automática.

**Para el Estudiante:**
1.  **Acceso al Chat:** Encuentra un enlace en Moodle para acceder al chat de IA del curso.
2.  **Consulta:** Realiza preguntas sobre el material del curso.
3.  **Respuesta Contextualizada:** Entrenai responde utilizando la información extraída de los documentos.

## Instrucciones de Configuración y Ejecución (Directorio `entrenai_refactor/`)

Asegúrate de estar en el directorio `entrenai_refactor/` para ejecutar los siguientes comandos.

### Archivos de Entorno

1.  Copia `entrenai_refactor/.env.example` a `entrenai_refactor/.env`.
2.  Modifica `entrenai_refactor/.env` con tu configuración local (tokens, URLs, etc.). Este archivo será usado para la ejecución local de la API y el worker de Celery.
3.  Para Docker Compose, copia `entrenai_refactor/.env.example` a `entrenai_refactor/.env.docker` y ajústalo. `docker-compose.yml` está configurado para usar este archivo.

### Usando Makefile (Recomendado para Desarrollo)

El `Makefile` en este directorio (`entrenai_refactor/Makefile`) facilita las operaciones comunes:

1.  **Crear entorno virtual e instalar dependencias:**
    ```bash
    make instalar
    ```
    (Crea `.venv` e instala de `requirements.txt` y `requirements.celery.txt`)

2.  **Ejecutar API de FastAPI localmente (para desarrollo):**
    ```bash
    make correr-api
    ```
    (Usa Uvicorn con recarga automática. Requiere `entrenai_refactor/.env`)

3.  **Ejecutar Worker de Celery localmente (para desarrollo):**
    ```bash
    make correr-worker-celery
    ```
    (Requiere `entrenai_refactor/.env` y un broker Redis accesible)

4.  **Levantar todos los servicios con Docker Compose:**
    ```bash
    make levantar-servicios
    ```
    (Usa `docker-compose.yml` y `entrenai_refactor/.env.docker`)

5.  **Bajar los servicios de Docker Compose:**
    ```bash
    make bajar-servicios
    ```

6.  **Ver logs de los servicios Docker:**
    ```bash
    make logs-servicios
    ```

### Usando Docker Compose Directamente

Desde el directorio `entrenai_refactor/`:

1.  **Levantar servicios en segundo plano (detached) y construir imágenes si es necesario:**
    ```bash
    docker compose up --build -d
    ```
2.  **Bajar servicios:**
    ```bash
    docker compose down
    ```
3.  **Ver logs de todos los servicios (en tiempo real):**
    ```bash
    docker compose logs -f
    ```

## Documentación Adicional

Para un registro de los cambios y decisiones tomadas durante esta refactorización, consulta `entrenai_refactor/docs/documentacion.md`.
La documentación original del proyecto (informe de tesis, manuales de usuario/técnico previos a esta refactorización) se encuentra en el directorio `docs/` en la raíz del repositorio principal.

---

Este `README.md` proporciona una guía actualizada para el proyecto refactorizado `entrenai_refactor`.
