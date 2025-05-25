<!-- CARÁTULA -->
<!-- Esta sección simula la carátula. La conversión a PDF permitirá aplicar tipografías y tamaños específicos. -->

<!-- Logo de la Facultad de Ingeniería (centrado) -->
<!-- Reemplazar con la imagen o instrucción para el logo -->
<p align="center">[Logo de la Facultad de Ingeniería]</p>

<!-- Título (Tipografía calibri / Cuerpo 28) -->
# <p align="center">[Título del Proyecto: Ej. "Desarrollo de un Sistema de Asistencia Docente con IA Personalizada mediante RAG en Moodle"]</p>

<!-- Apellido - Nombre - DNI del estudiante (Tipografía calibri / Cuerpo 22) -->
## <p align="center">[Apellido del Estudiante, Nombre del Estudiante] - DNI: [DNI del Estudiante]</p>

<!-- Apellido - Nombre del docente a cargo (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Docente a Cargo: [Apellido del Docente, Nombre del Docente]</p>

<!-- Cátedra: Trabajo Integrador Final 3 (TIF) (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Cátedra: Trabajo Integrador Final 3 (TIF)</p>

<!-- Carrera (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Carrera: Ingeniería en Informática</p>

<!-- Año de cursado (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Año de cursado: [Año de Cursado]</p>

<!-- Sede (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Sede: [Sede]</p>

<!-- Fecha de entrega (Tipografía calibri / Cuerpo 18) -->
### <p align="center">Fecha de entrega: [Fecha de Entrega]</p>

<!-- FIN CARÁTULA -->

---
<!-- Salto de página para el cuerpo del texto (en PDF) -->
---

<!-- CUERPO DEL TEXTO -->
<!-- Tipografía: calibri, Cuerpo: 14, Espacio: 1,15, Márgenes: 3cm (izq, sup) 2cm (der, inf), Texto justificado -->
<!-- Títulos: calibri / Cuerpo 16 / Negrita -->

# **Metodología**

## **1. Introducción**

El presente capítulo detalla la metodología seguida para el diseño, desarrollo e implementación del Trabajo Final Integrador (TIF) titulado "Entrenai - Sistema Inteligente de Asistencia al Estudiante Basado en RAG para Cursos de Moodle". Este proyecto se enfoca en la creación de un sistema innovador que potencia la plataforma de gestión del aprendizaje Moodle mediante la integración de una capacidad de asistencia inteligente y contextualizada, utilizando la técnica de Generación Aumentada por Recuperación (RAG). El objetivo primordial de Entrenai es dotar a los docentes de una herramienta que les permita configurar una inteligencia artificial (IA) personalizada para sus cátedras, capaz de procesar el material del curso y ofrecer respuestas precisas y relevantes a las consultas de los estudiantes, mejorando así la experiencia de aprendizaje y la eficiencia en el acceso a la información.

La motivación subyacente es abordar el desafío común en entornos virtuales de aprendizaje donde la abundancia de información puede dificultar la localización de respuestas específicas. Entrenai busca ser un puente entre el vasto contenido del curso y la necesidad del estudiante de obtener aclaraciones puntuales, actuando como un tutor virtual disponible permanentemente.

La metodología de desarrollo adoptada se inspira en los principios ágiles, priorizando la entrega de valor incremental a través de ciclos iterativos, la colaboración constante con el tutor del proyecto y la flexibilidad para adaptarse a los descubrimientos y desafíos técnicos emergentes. Se ha mantenido un registro cronológico de los avances, las decisiones arquitectónicas y las herramientas tecnológicas empleadas en cada fase, lo cual se expondrá detalladamente en las secciones subsiguientes.

### **1.1. Tipo de Investigación**

El trabajo realizado se enmarca predominantemente dentro de la **investigación aplicada**. El proyecto no busca generar conocimiento teórico fundamental per se, sino aplicar y combinar conocimientos y tecnologías existentes en los campos de la Inteligencia Artificial (específicamente Procesamiento de Lenguaje Natural y Modelos de Lenguaje Grandes), desarrollo de software, e integración de sistemas, para resolver un problema práctico y específico en el contexto educativo: la creación de una herramienta de asistencia inteligente personalizada para cursos en la plataforma Moodle. Se investigaron, evaluaron y adaptaron diversas tecnologías y enfoques para construir una solución funcional y efectiva.

### **1.2. Alcance del Proyecto**

El alcance de Entrenai, tal como se definió y desarrolló, abarca las siguientes funcionalidades principales:

*   **Integración con Moodle:** Listado de cursos disponibles para un profesor y la capacidad de seleccionar uno para la configuración de la IA.
*   **Configuración Automatizada:** Creación automática de los elementos necesarios en el curso de Moodle seleccionado (una nueva sección, una carpeta designada para los documentos del curso, enlaces al chat de la IA y a una función para refrescar el contenido).
*   **Base de Conocimiento Vectorial:** Creación y gestión de una base de datos vectorial específica para el curso (utilizando PostgreSQL con la extensión PGVector) para almacenar los contenidos procesados.
*   **Workflow de Chat:** Despliegue y configuración de un flujo de trabajo en N8N que gestiona la interacción del chat.
*   **Procesamiento de Archivos:** Capacidad para procesar archivos en formatos comunes (PDF, DOCX, PPTX, TXT, MD) subidos por el profesor a la carpeta designada en Moodle. Este procesamiento incluye:
    *   Descarga de archivos nuevos o modificados.
    *   Extracción de texto.
    *   Formateo del texto extraído a un formato Markdown limpio.
    *   División del texto en fragmentos (chunks) semánticamente coherentes.
    *   Generación de representaciones vectoriales (embeddings) para cada fragmento utilizando modelos de lenguaje.
    *   Almacenamiento de los fragmentos y sus embeddings en la base de datos PGVector.
*   **Interfaz de Chat RAG:** Interfaz accesible para los estudiantes (a través de N8N) donde pueden realizar preguntas en lenguaje natural y recibir respuestas generadas por el sistema RAG, utilizando el material del curso como única fuente de verdad y modelos de lenguaje auto-alojados (vía Ollama).
*   **Procesamiento Asíncrono:** La descarga y el procesamiento de archivos se realizan de forma asíncrona (utilizando Celery y Redis) para no bloquear la interfaz de usuario y mejorar la eficiencia.
*   **API de Gestión:** Una API robusta (construida con FastAPI) que orquesta todas las operaciones del sistema.

Las limitaciones actuales y funcionalidades no cubiertas se detallan en el informe de tesis principal y pueden incluir aspectos como una interfaz de profesor más avanzada para la gestión post-configuración, soporte para una gama más amplia de tipos de archivo, o analíticas de uso detalladas.

## **2. Arquitectura General del Sistema**

Entrenai está diseñado como un sistema modular compuesto por varios servicios interconectados que colaboran para ofrecer la funcionalidad de asistencia inteligente. La arquitectura se centra en la integración con Moodle y la implementación de un pipeline RAG.

```mermaid
graph TD
    Profesor -->|Interactúa con| UI_Admin(UI Admin Entrenai - HTML/JS en /api/static)
    UI_Admin -->|Llama a| API_FastAPI(Backend FastAPI - Python, src/entrenai/api)

    API_FastAPI -->|Comandos WS| Moodle_Service(Moodle 4.5.4 - Bitnami Docker, src/entrenai/core/clients/moodle_client.py)
    API_FastAPI -->|CRUD & Vector Search| Pgvector_Service(PostgreSQL 16 + PGVector, src/entrenai/core/db/pgvector_wrapper.py)
    API_FastAPI -->|Configura Workflow vía API| N8N_Service(N8N 1.91.3 - Docker, src/entrenai/core/clients/n8n_client.py)
    
    Profesor -->|Sube Archivos a| Moodle_Service
    
    API_FastAPI -->|Despacha Tareas de Procesamiento| Celery_Service(Celery Workers 5.3.6 - Python/Docker, src/entrenai/core/tasks.py)
    Celery_Service <-->|Broker/Backend| Redis_Service(Redis - Docker)
    Celery_Service -->|Descarga Archivos de| Moodle_Service
    Celery_Service -->|Procesa Archivos (src/entrenai/core/files/file_processor.py) y Genera Embeddings (src/entrenai/core/ai/embedding_manager.py) con| Ollama_Service(Ollama 0.6.8 - LLMs Locales - Docker, src/entrenai/core/ai/ollama_wrapper.py)
    Celery_Service -->|Guarda Chunks/Embeddings en| Pgvector_Service

    Estudiante -->|Interactúa con| Chat_N8N(Chat en N8N - src/entrenai/n8n_workflow.json)
    Chat_N8N -->|Recupera Chunks de| Pgvector_Service
    Chat_N8N -->|Genera Respuesta con| Ollama_Service
```

**Descripción de Componentes Clave:**

*   **UI Admin Entrenai:** Interfaz web simple (HTML, CSS, JavaScript), servida por FastAPI desde `src/entrenai/api/static/`, que permite al profesor autenticarse (implícito), listar sus cursos de Moodle e iniciar la configuración de la IA para un curso seleccionado.
*   **Backend FastAPI (`src/entrenai/api/`):** El núcleo del sistema, desarrollado en Python. Expone una API REST (definida en `src/entrenai/api/routers/course_setup.py` y otros routers) que orquesta la comunicación entre Moodle, Pgvector, Ollama, N8N y Celery, además de gestionar la lógica de negocio. Utiliza configuración centralizada desde `src/entrenai/config/`.
*   **Moodle (`src/entrenai/core/clients/moodle_client.py`):** Plataforma LMS (versión 4.5.4 de Bitnami en Docker). El `MoodleClient` interactúa con Moodle mediante sus Web Services para listar cursos, crear secciones, carpetas, enlaces y descargar archivos.
*   **Ollama (`src/entrenai/core/ai/ollama_wrapper.py`, `src/entrenai/core/ai/gemini_wrapper.py`, `src/entrenai/core/ai/ai_provider.py`):** Servicio (versión 0.6.8 en Docker) que permite ejecutar LLMs localmente. El `OllamaWrapper` y `GeminiWrapper`, gestionados por `AIProvider`, se utilizan para la generación de embeddings (ej. `nomic-embed-text`) y la formulación de respuestas del chatbot. La selección del proveedor (Ollama/Gemini) se basa en `base_config.ai_provider`.
*   **Pgvector (`src/entrenai/core/db/pgvector_wrapper.py`):** Base de datos PostgreSQL (versión 16 con extensión PGVector en Docker). El `PgvectorWrapper` gestiona la creación de tablas específicas por curso, el almacenamiento de fragmentos de texto (chunks) y sus embeddings, y las búsquedas semánticas. También maneja el seguimiento de archivos procesados.
*   **N8N (`src/entrenai/core/clients/n8n_client.py`, `src/entrenai/n8n_workflow.json`):** Plataforma de automatización de workflows (versión 1.91.3 en Docker). El `N8NClient` despliega y configura dinámicamente un workflow (basado en `n8n_workflow.json`) que implementa la lógica del chatbot.
*   **Celery (`src/entrenai/celery_app.py`, `src/entrenai/core/tasks.py`):** Sistema de colas de tareas distribuidas (versión 5.3.6). `celery_app.py` configura la instancia de Celery, y `tasks.py` define las tareas asíncronas como `process_moodle_file_task` para el procesamiento de archivos.
*   **Redis:** Almacén de datos en memoria (en Docker) que actúa como intermediario de mensajes (broker) para Celery y como backend para almacenar los resultados de las tareas.

## **3. Fases del Desarrollo y Cronología de Reuniones**

El desarrollo del proyecto se articuló mediante una serie de reuniones con el tutor, que sirvieron como puntos de control, planificación y reorientación. A continuación, se describe la evolución cronológica del proyecto, integrando los detalles técnicos de lo que se diseñó y construyó en cada etapa.

### **3.1. Fase 1: Planificación Inicial y Definición del Alcance (Reunión 1)**

Esta fase inicial se centró en la conceptualización y validación de la idea del proyecto.
*   **Actividades:** Se presentó la propuesta de valor de Entrenai al tutor. Se realizó una sesión de brainstorming para identificar las funcionalidades esenciales y los requerimientos generales. Esto culminó en la creación de un backlog inicial de tareas en un formato similar a historias de usuario, cubriendo aspectos desde la interacción con Moodle hasta las capacidades básicas de la IA.
*   **Entregables Conceptuales:** Un conjunto de tarjetas de requerimientos y una comprensión compartida de los objetivos del proyecto.

### **3.2. Fase 2: Revisión de Requerimientos y Planificación del Primer Sprint (Reunión 2)**

Se procedió a una revisión detallada del backlog inicial.
*   **Actividades:** Se analizaron las tarjetas de requerimientos para validar su necesidad, estimar el esfuerzo de implementación y priorizarlas. Se seleccionó un subconjunto de estas tareas para conformar el primer sprint de desarrollo, enfocándose en un MVP (Producto Mínimo Viable) que demostrara la funcionalidad central. Se discutieron las primeras ideas sobre la arquitectura tecnológica, incluyendo la evaluación inicial de OpenWebUI para el chat, que posteriormente se descartaría en favor de N8N por su flexibilidad en la orquestación de flujos complejos.
*   **Decisiones Clave:** Priorización de la integración con Moodle y un primer prototipo de RAG.

### **3.3. Fase 3: Desarrollo del Primer Prototipo - Acceso a Datos de Moodle (Reunión 3)**

El primer sprint de desarrollo (aproximadamente dos semanas) se concentró en establecer la comunicación con Moodle y la recuperación de datos.
*   **Desarrollo Técnico:**
    *   Configuración del entorno de desarrollo: Python, FastAPI, y Docker para gestionar una instancia local de Moodle (Bitnami Moodle 4.5.4 sobre PostgreSQL 17.5, según `docker-compose.yml`).
    *   Implementación del `MoodleClient` (ubicado en `src/entrenai/core/clients/moodle_client.py`), responsable de interactuar con los Web Services de Moodle para autenticación, listado de cursos y recuperación de archivos.
    *   Desarrollo de los primeros endpoints en la API FastAPI (en `src/entrenai/api/routers/`) para exponer estas funcionalidades: listar cursos y descargar archivos de un curso específico.
*   **Resultado Presentado:** Una demostración funcional donde el sistema podía conectarse a Moodle, listar los cursos de un profesor y descargar los archivos asociados a una carpeta local. Este avance fue bien recibido por el tutor.

### **3.4. Fase 4: Integración de IA (Embeddings y LLM Local) y Automatización Inicial (Reunión 4)**

Se avanzó en la integración de los componentes de IA y la automatización de procesos.
*   **Desarrollo Técnico:**
    *   **Procesamiento de Documentos y Embeddings:** Implementación del `EmbeddingManager` (en `src/entrenai/core/ai/embedding_manager.py`) para procesar los archivos descargados. Esto incluía la extracción de texto (utilizando librerías como `python-docx`, `python-pptx`, `pdf2image` con `pytesseract` según `requirements.txt`), la división en chunks y la generación de embeddings utilizando un modelo local a través de `OllamaWrapper` (en `src/entrenai/core/ai/ollama_wrapper.py`), que interactuaba con el servicio Ollama (versión 0.6.8).
    *   **Base de Datos Vectorial:** Configuración inicial de Qdrant (mencionado como primera opción) para almacenar los embeddings. Se desarrolló un `QdrantWrapper` (en `src/entrenai/core/db/qdrant_wrapper.py`) para esta interacción.
    *   **Automatización con N8N:** Inicio del desarrollo de un workflow en N8N (versión 1.91.3, con backend PostgreSQL 17.5) para orquestar el flujo de chat. Esto implicaba recibir una pregunta, consultar la base de datos vectorial y obtener una respuesta del LLM local.
*   **Resultado Presentado:** Una primera versión del sistema RAG donde se podían cargar archivos a Moodle, estos se descargaban, procesaban (generando embeddings), y se podía realizar una consulta básica a través de una interfaz preliminar de N8N, obteniendo una respuesta del LLM local basada en los documentos.

### **3.5. Fase 5: Desarrollo de la Interfaz de Profesor, Mejoras en IA y Flujo Completo (Reunión 5 - Fin del Primer Sprint)**

Esta fase se centró en consolidar un flujo de usuario completo y mejorar la usabilidad y robustez.
*   **Desarrollo Técnico:**
    *   **Interfaz de Usuario para el Profesor:** Creación de una interfaz web básica (HTML, CSS, JavaScript, servida desde `src/entrenai/api/static/index.html`) que permitía al profesor autenticarse (implícito), listar sus cursos de Moodle (endpoint `/api/v1/courses`) y seleccionar uno para activar la IA (endpoint `/api/v1/courses/{course_id}/setup-ia`).
    *   **Automatización de la Configuración del Curso (`setup_ia_for_course`):** El backend FastAPI fue extendido para que, al seleccionar un curso:
        *   Determinara el nombre del curso (intentando desde query param, luego Moodle, luego fallback a `Curso_{course_id}`).
        *   Llamara a `pgvector_db.ensure_table(course_name_str, vector_size)` para preparar la tabla en Pgvector.
        *   Utilizara `N8NClient` (en `src/entrenai/core/clients/n8n_client.py`) para invocar `n8n.configure_and_deploy_chat_workflow`. Este método recibía `course_id`, `course_name_str`, el nombre de la tabla Pgvector y `ai_params` (un diccionario con la configuración del proveedor de IA seleccionado, sea Ollama o Gemini, basado en `base_config.ai_provider`).
        *   Utilizara `MoodleClient` para invocar `moodle.create_course_section` y luego `moodle._make_request("local_wsmanagesections_update_sections", payload)` para crear una nueva sección en el curso de Moodle. El `payload` incluía un `summary` HTML dinámico con el nombre de la carpeta de documentos (`Documentos Entrenai`), un enlace al chat de N8N y un enlace a la página de gestión de archivos (`/static/manage_files.html?course_id={course_id}`).
    *   **Mejoras en Embeddings y N8N:** Se optimizó el proceso de generación de embeddings y se robusteció el workflow de N8N.
    *   **Integración de Google Gemini:** Se añadió `GeminiWrapper` (en `src/entrenai/core/ai/gemini_wrapper.py`) y la lógica en `AIProvider` (en `src/entrenai/core/ai/ai_provider.py`) para permitir la selección y fallback entre Ollama y Gemini como proveedores de IA.
*   **Resultado Presentado:** Una demo funcional del flujo completo: el profesor accedía a la UI, seleccionaba un curso, y el sistema configuraba automáticamente la IA. Se podían subir archivos a la carpeta designada en Moodle, refrescar el contenido (lo que disparaba el procesamiento asíncrono), y los estudiantes (simulados) podían interactuar con el chat. El primer sprint concluyó (duración aproximada: 1 mes y 1 semana), con una recepción positiva por parte del tutor.

### **3.6. Fase 6: Inicio del Segundo Sprint - Mejoras y Preparación para MVP Final**

El segundo sprint se enfocó en refinar el MVP, abordar limitaciones y mejorar la robustez y escalabilidad.
*   **Desarrollo Técnico Planificado/En Curso:**
    *   **Mejora de la Interfaz Gráfica:** Refinamiento de la UI del profesor (`src/entrenai/api/static/index.html`, `script.js`, `style.css`).
    *   **Optimización del Workflow de N8N:** Mejorar la interacción con la base de datos vectorial y el manejo de errores.
    *   **Migración a PGVector:** Decisión estratégica de migrar de Qdrant a PostgreSQL con la extensión PGVector. Esto implicó desarrollar `PgvectorWrapper` (en `src/entrenai/core/db/pgvector_wrapper.py`) y adaptar la lógica de almacenamiento y consulta de embeddings. El `PgvectorWrapper` también asumió la responsabilidad de rastrear los archivos procesados y sus `timemodified` (reemplazando un `FileTracker` separado), como se evidencia en métodos como `is_file_new_or_modified` y `delete_file_from_tracker`.
    *   **Procesamiento Asíncrono (`refresh_course_files` endpoint y `process_moodle_file_task` Celery task):** Implementación del procesamiento de archivos de forma asíncrona. El endpoint `/api/v1/courses/{course_id}/refresh-files` identifica archivos nuevos o modificados en Moodle (comparando `timemodified` con los registros en `PgvectorWrapper`) y despacha tareas `process_moodle_file_task` a Celery. Cada tarea recibe una configuración completa (detalles del archivo de Moodle, directorios, configuración de IA, Pgvector, Moodle y base) para ser autónoma. El estado de las tareas se puede consultar mediante `/api/v1/task/{task_id}/status`.
    *   **Gestión Avanzada de Archivos:** Desarrollo de la interfaz `src/entrenai/api/static/manage_files.html` (y `manage_files.js`) y los endpoints API `/api/v1/courses/{course_id}/indexed-files` (para listar archivos) y `/api/v1/courses/{course_id}/indexed-files/{file_identifier}` (para eliminar archivos y sus chunks de Pgvector y el tracker).
    *   **Pruebas Exhaustivas:** Incremento de la cobertura de pruebas unitarias y de integración (en `tests/`), utilizando `pytest` y `pytest-asyncio`.
    *   **Mejora de la Documentación:** Actualización de `MANUAL_TECNICO.md`, `MANUAL_USUARIO.md` e `INFORME_TESIS.md`.
    *   **Preparación para el Despliegue:** Refinamiento de `docker-compose.yml` y `Makefile` para facilitar el despliegue.

*   **Desafíos Abordados:**
    *   La complejidad inicial de sistemas de colas avanzados llevó a la simplificación con Celery.
    *   Limitaciones de la API de Moodle para la creación programática de carpetas en secciones específicas requirieron instructivos para la creación manual por parte del profesor, con el sistema luego identificando la carpeta por su nombre (`Documentos Entrenai`) dentro de la sección creada (`moodle_config.course_folder_name`).
    *   Continua refactorización del código para mantener la organización y mantenibilidad del proyecto, como la consolidación de la lógica de seguimiento de archivos dentro del `PgvectorWrapper`.

## **4. Diseño Detallado de Componentes Clave**

Esta sección profundiza en el diseño de los elementos más críticos del sistema Entrenai, basándose en la información de `INFORME_TESIS.md`, `MANUAL_TECNICO.md` y el análisis del código fuente en `src/entrenai/`.

### **4.1. Flujo de Datos y Procesos**

El sistema opera a través de tres flujos principales, implementados en gran medida dentro de `src/entrenai/api/routers/course_setup.py` y las tareas Celery.

1.  **Configuración Inicial por el Profesor (Endpoint `POST /api/v1/courses/{course_id}/setup-ia`):**
    *   El profesor, a través de la UI (`index.html`), selecciona un curso.
    *   La API FastAPI recibe la solicitud.
    *   Se determina el `course_name_for_pgvector` (nombre de tabla/colección).
    *   Se llama a `pgvector_db.ensure_table()` para crear/verificar la tabla en Pgvector.
    *   Se llama a `n8n_client.configure_and_deploy_chat_workflow()` con parámetros que incluyen `course_id`, `course_name_for_pgvector`, nombre de la tabla Pgvector, y `ai_params` (configuración de Ollama/Gemini).
    *   Se utiliza `moodle_client.create_course_section()` y luego `moodle_client._make_request("local_wsmanagesections_update_sections", ...)` para crear la sección en Moodle y actualizarla con un sumario HTML que contiene el nombre de la carpeta (`Documentos Entrenai`), el enlace al chat N8N y el enlace a la página de gestión de archivos (`/static/manage_files.html?course_id={course_id}`).

2.  **Subida y Procesamiento de Archivos (Endpoint `GET /api/v1/courses/{course_id}/refresh-files`):**
    *   El profesor sube archivos a la carpeta "Documentos Entrenai" en Moodle y activa el refresco.
    *   La API FastAPI:
        *   Obtiene el `course_name_for_pgvector`.
        *   Asegura la existencia de la tabla Pgvector.
        *   Localiza la sección y la carpeta "Documentos Entrenai" en Moodle.
        *   Lista los archivos en dicha carpeta usando `moodle_client.get_folder_files()`.
        *   Para cada archivo, verifica si es nuevo o modificado usando `pgvector_db.is_file_new_or_modified(course_id, mf.filename, mf.timemodified)`.
        *   Si es nuevo/modificado, despacha una tarea Celery `process_moodle_file_task.delay()` con todos los parámetros necesarios (info del archivo Moodle, directorio de descarga, configuraciones de IA, Pgvector, Moodle y base).
        *   Retorna una lista de IDs de las tareas despachadas.
    *   **Tarea Celery (`process_moodle_file_task` en `src/entrenai/core/tasks.py`):**
        *   Descarga el archivo de Moodle.
        *   Utiliza `FileProcessor` para extraer texto.
        *   Utiliza `OllamaWrapper` (o `GeminiWrapper` según `ai_provider_config`) para formatear el texto a Markdown.
        *   Utiliza `EmbeddingManager` para dividir en chunks y generar embeddings (vía el proveedor de IA).
        *   Utiliza `PgvectorWrapper` para guardar los chunks/embeddings y actualizar el timestamp del archivo en el tracker.

3.  **Interacción del Estudiante con el Chatbot (Workflow N8N):**
    *   El estudiante accede al chat N8N (enlace en Moodle).
    *   N8N recibe la pregunta.
    *   Genera embedding de la pregunta (usando el proveedor de IA configurado, ej. Ollama).
    *   Busca chunks relevantes en la tabla Pgvector específica del curso.
    *   Genera una respuesta RAG (usando el proveedor de IA con la pregunta y los chunks).
    *   Devuelve la respuesta al estudiante.

```mermaid
sequenceDiagram
    actor Profesor
    actor Estudiante
    participant UI_Admin as "UI Admin Entrenai (/static/index.html)"
    participant FastAPI as "Backend FastAPI (course_setup.py)"
    participant Moodle as "MoodleClient"
    participant Pgvector as "PgvectorWrapper"
    participant N8N as "N8NClient & Workflow"
    participant Celery as "Celery (tasks.py)"
    participant Ollama_Gemini as "AIProvider (Ollama/Gemini)"
    participant FileTracker_in_Pgvector as "File Tracking (in PgvectorWrapper)"

    box rgb(230, 245, 255) Flujo 1: Configuración Inicial por el Profesor
        Profesor->>UI_Admin: Accede y selecciona curso
        UI_Admin->>FastAPI: POST /api/v1/courses/{course_id}/setup-ia
        activate FastAPI
        FastAPI->>Moodle: create_course_section(), _make_request("local_wsmanagesections_update_sections", ...)
        Moodle-->>FastAPI: Confirmación/Datos creación
        FastAPI->>Pgvector: ensure_table()
        Pgvector-->>FastAPI: Confirmación tabla
        FastAPI->>N8N: configure_and_deploy_chat_workflow(..., ai_params)
        N8N-->>FastAPI: Confirmación/Datos workflow (ej. URL webhook)
        FastAPI-->>UI_Admin: Confirmación de configuración
        deactivate FastAPI
        UI_Admin-->>Profesor: Muestra confirmación y links
    end

    box rgb(230, 255, 230) Flujo 2: Subida y Procesamiento de Archivos
        Profesor->>Moodle: Sube archivos a carpeta "Documentos Entrenai"
        Profesor->>FastAPI: GET /api/v1/courses/{course_id}/refresh-files (desde /static/manage_files.html)
        activate FastAPI
        FastAPI->>Moodle: get_folder_files()
        Moodle-->>FastAPI: Lista de archivos (moodle_files)
        loop Para cada mf en moodle_files
            FastAPI->>FileTracker_in_Pgvector: is_file_new_or_modified(course_id, mf.filename, mf.timemodified)
            alt Archivo nuevo o modificado
                FastAPI->>Celery: process_moodle_file_task.delay(..., ai_provider_config, ...)
            end
        end
        FastAPI-->>Profesor: Lista de IDs de tareas despachadas
        deactivate FastAPI

        activate Celery
        Note over Celery: Worker toma process_moodle_file_task(self, course_id, course_name_for_pgvector, moodle_file_info_dict, download_dir_str, ai_provider_config_dict, pgvector_config_dict, moodle_config_dict, base_config_dict)
        Celery->>Moodle: moodle_client.download_file(file_url, download_dir_path, filename)
        Moodle-->>Celery: Contenido del archivo (downloaded_path)
        Celery->>Ollama_Gemini: file_processor.process_file(downloaded_path) # Extrae raw_text
        Celery->>Ollama_Gemini: ai_client.format_to_markdown(raw_text, save_path) # Formatea y guarda Markdown
        Celery->>Ollama_Gemini: embedding_manager.split_text_into_chunks(markdown_text)
        Celery->>Ollama_Gemini: embedding_manager.contextualize_chunk(chunk_text, filename) # Para cada chunk
        Celery->>Ollama_Gemini: embedding_manager.generate_embeddings_for_chunks(contextualized_chunks)
        Ollama_Gemini-->>Celery: Chunks y embeddings
        Celery->>Pgvector: embedding_manager.prepare_document_chunks_for_vector_db(...)
        Celery->>Pgvector: pgvector_db.upsert_chunks(course_name_for_pgvector, db_chunks)
        Pgvector-->>Celery: Confirmación guardado
        Celery->>FileTracker_in_Pgvector: pgvector_db.mark_file_as_processed(course_id, filename, timemodified)
        FileTracker_in_Pgvector-->>Celery: Confirmación actualización
        Note over Celery: downloaded_path.unlink() y pgvector_db.close_connection() en finally
        deactivate Celery
        
        opt Consulta Estado de Tareas (Endpoint /api/v1/task/{task_id}/status)
            Profesor->>FastAPI: GET /api/v1/task/{task_id}/status
            activate FastAPI
            FastAPI->>Celery: AsyncResult(task_id, app=celery_app).status / .result / .traceback
            Celery-->>FastAPI: Estado de la tarea
            FastAPI-->>Profesor: Estado de la tarea
            deactivate FastAPI
        end
    end

    box rgb(255, 245, 230) Flujo 3: Interacción del Estudiante con el Chatbot
        Estudiante->>N8N: Envía pregunta (vía Chat en Moodle)
        activate N8N
        N8N->>Ollama_Gemini: Genera embedding de la pregunta
        Ollama_Gemini-->>N8N: Embedding de la pregunta
        N8N->>Pgvector: Busca chunks relevantes con embedding
        Pgvector-->>N8N: Chunks relevantes
        N8N->>Ollama_Gemini: Genera respuesta (RAG) con pregunta y chunks
        Ollama_Gemini-->>N8N: Respuesta generada
        N8N-->>Estudiante: Devuelve respuesta al chat
        deactivate N8N
    end
```

### **4.2. Base de Datos Vectorial (Pgvector)**

La persistencia y búsqueda de información vectorial, así como el seguimiento del estado de los archivos procesados, son gestionadas por la clase `PgvectorWrapper` (ubicada en `src/entrenai/core/db/pgvector_wrapper.py`). Esta clase interactúa con una instancia de PostgreSQL (versión 16) que tiene habilitada la extensión PGVector, ejecutándose en un contenedor Docker (`pgvector/pgvector:pg16`).

*   **Conexión y Configuración:**
    *   El `PgvectorWrapper` se inicializa con un objeto `PgvectorConfig` que contiene los detalles de conexión (host, puerto, usuario, contraseña, nombre de la base de datos).
    *   Utiliza la librería `psycopg2` para la conexión y `register_vector` de `pgvector.psycopg2` para el manejo del tipo de dato vectorial.
    *   Al inicializarse, asegura que la extensión `vector` esté creada en la base de datos (`CREATE EXTENSION IF NOT EXISTS vector;`).
    *   Implementa manejo de errores con una excepción personalizada `PgvectorWrapperError` y gestiona la conexión (`self.conn`, `self.cursor`), incluyendo un método `close_connection()` y un `__del__` para asegurar el cierre.

*   **Gestión de Tablas Específicas por Curso:**
    *   **Normalización de Nombres:** El método `_normalize_name_for_table(name: str)` convierte el nombre del curso en un identificador válido para tablas PostgreSQL (minúsculas, reemplazo de espacios por guiones bajos, eliminación de caracteres no alfanuméricos, truncamiento).
    *   **Nombre de Tabla Dinámico:** El método `get_table_name(course_name: str)` utiliza el nombre normalizado y el prefijo definido en `pgvector_config.collection_prefix` (ej. `entrenai_`) para generar un nombre de tabla único para los embeddings de cada curso (ej. `entrenai_nombre_del_curso`).
    *   **Creación de Tablas (`ensure_table`):** El método `ensure_table(course_name: str, vector_size: int)` verifica la existencia de la tabla del curso. Si no existe, la crea con la siguiente estructura:
        *   `id` (TEXT PRIMARY KEY): Identificador único del chunk.
        *   `course_id` (TEXT): ID del curso de Moodle.
        *   `document_id` (TEXT): Identificador del documento original (generalmente el nombre del archivo).
        *   `text` (TEXT): El contenido textual del chunk.
        *   `metadata` (JSONB): Metadatos adicionales asociados al chunk.
        *   `embedding` (vector(vector_size)): El vector de embedding del chunk.
        *   Adicionalmente, crea un índice HNSW (`CREATE INDEX ON {table_name} USING hnsw (embedding vector_cosine_ops);`) sobre la columna `embedding` para optimizar las búsquedas por similitud de coseno.

*   **Seguimiento de Archivos Procesados:**
    *   **Tabla de Seguimiento Global (`FILE_TRACKER_TABLE_NAME = "file_tracker"`):** El método `ensure_file_tracker_table()` crea una tabla global llamada `file_tracker` si no existe, con la siguiente estructura:
        *   `course_id` (INTEGER NOT NULL)
        *   `file_identifier` (TEXT NOT NULL): Nombre del archivo.
        *   `moodle_timemodified` (BIGINT NOT NULL): Timestamp de la última modificación del archivo en Moodle.
        *   `processed_at` (BIGINT NOT NULL): Timestamp del último procesamiento por Entrenai.
        *   PRIMARY KEY (`course_id`, `file_identifier`).
    *   **Verificación de Modificaciones (`is_file_new_or_modified`):** Este método consulta la tabla `file_tracker` para un `course_id` y `file_identifier` dados, comparando el `moodle_timemodified` proporcionado con el almacenado para determinar si el archivo es nuevo o ha sido modificado.
    *   **Marcado de Archivos (`mark_file_as_processed`):** Después de procesar un archivo, este método inserta o actualiza (upsert) el registro del archivo en la tabla `file_tracker` con el `moodle_timemodified` actual y el nuevo `processed_at` (timestamp actual).
    *   **Gestión de Archivos Indexados:**
        *   `get_processed_files_timestamps(course_id: int)`: Recupera un diccionario de archivos procesados y sus `moodle_timemodified` para un curso.
        *   `delete_file_chunks(course_name: str, document_id: str)`: Elimina todos los chunks asociados a un `document_id` de la tabla de embeddings del curso.
        *   `delete_file_from_tracker(course_id: int, file_identifier: str)`: Elimina el registro de un archivo de la tabla `file_tracker`.

*   **Operaciones con Chunks:**
    *   **Inserción/Actualización (`upsert_chunks`):** Este método toma una lista de objetos `DocumentChunk` y los inserta o actualiza en la tabla del curso correspondiente. Utiliza una sentencia `INSERT ... ON CONFLICT (id) DO UPDATE SET ...` para manejar la lógica de upsert basada en el `id` del chunk. Los metadatos del chunk (si son un diccionario) se serializan a JSON antes de la inserción.
    *   **Búsqueda por Similitud (`search_chunks`):** Realiza una búsqueda semántica en la tabla del curso.
        *   Utiliza el operador de distancia coseno de PGVector (`<=>`).
        *   Calcula un `score` de similitud como `(1 - (embedding <=> %s))`, donde un valor más cercano a 1 indica mayor similitud.
        *   Ordena los resultados por distancia (`ORDER BY embedding <=> %s`) y los limita.
        *   Formatea los resultados en una estructura similar a la de `ScoredPoint` de Qdrant, con `id`, `score`, y un `payload` que incluye `course_id`, `document_id`, `text` y `metadata`.

### **4.3. Workflow de Chat (N8N)**

*   **Plantilla:** Un workflow base se define en `src/entrenai/n8n_workflow.json`.
*   **Despliegue Dinámico:** El `N8NClient.configure_and_deploy_chat_workflow` (en `src/entrenai/core/clients/n8n_client.py`) importa y activa esta plantilla. Crucialmente, parametriza el workflow con `course_id`, `course_name_str` (para el nombre de la tabla Pgvector), y `ai_params` (que contiene la configuración del host/API key y modelos para Ollama o Gemini). Esto permite que el workflow de N8N sepa a qué tabla Pgvector consultar y qué servicio de IA usar.
*   **Lógica del Workflow:**
    1.  **Webhook Trigger:** Recibe la pregunta del estudiante.
    2.  **Generación de Embedding de Pregunta:** Llama al proveedor de IA configurado (Ollama/Gemini) para vectorizar la pregunta.
    3.  **Búsqueda de Contexto en Pgvector:** Ejecuta una consulta SQL contra la tabla Pgvector específica del curso para encontrar los N chunks más similares.
    4.  **Construcción del Prompt RAG:** Combina la pregunta original y los chunks recuperados.
    5.  **Generación de Respuesta:** Envía el prompt RAG al proveedor de IA (Ollama/Gemini).
    6.  **Devolución de Respuesta:** Envía la respuesta generada al estudiante.

### **4.4. Procesamiento de Contenido y Gestión de Embeddings (Tarea Celery `process_moodle_file_task`)**

La tarea Celery `process_moodle_file_task`, definida en `src/entrenai/core/tasks.py`, es el núcleo del pipeline de ingesta de datos. Su ejecución detallada es la siguiente:

1.  **Inicialización:**
    *   Recibe como argumentos `course_id`, `course_name_for_pgvector`, un diccionario `moodle_file_info` (con `filename`, `fileurl`, `timemodified`), `download_dir_str`, y diccionarios de configuración para `ai_provider`, `pgvector`, `moodle` y `base`.
    *   Instancia los clientes y wrappers necesarios: `MoodleClient`, `PgvectorWrapper`, `FileProcessor`, el `AIWrapper` apropiado (Ollama o Gemini basado en `ai_provider_config['selected_provider']`) y `EmbeddingManager` (este último inicializado con el `ai_wrapper` y valores por defecto para `default_chunk_size` y `default_chunk_overlap`). Las configuraciones se reconstruyen a partir de los diccionarios recibidos.
    *   Asegura que el directorio de descarga (`download_dir_path`) exista.

2.  **Descarga del Archivo:**
    *   Utiliza `moodle_client.download_file(file_url, download_dir_path, filename)` para descargar el archivo desde Moodle.

3.  **Extracción y Formateo de Texto:**
    *   `file_processor.process_file(downloaded_path)` extrae el texto crudo del archivo.
    *   `ai_client.format_to_markdown(raw_text, save_path=markdown_file_path)` convierte el texto crudo a formato Markdown, guardándolo en una ruta (`markdown_file_path`) derivada de `base_config.data_dir` y el `course_id`.

4.  **Chunking y Contextualización (realizado por `EmbeddingManager`):**
    *   **División en Chunks:** `embedding_manager.split_text_into_chunks(markdown_text, chunk_size, chunk_overlap)` divide el texto Markdown en fragmentos. Utiliza un método de división basado en caracteres, con `chunk_size` (por defecto 1000 caracteres) y `chunk_overlap` (por defecto 200 caracteres) configurables. Si el texto es más corto que `chunk_size`, se devuelve como un solo chunk.
    *   Si no se generan chunks (ej. archivo vacío), se llama a `pgvector_db.mark_file_as_processed` y la tarea concluye para ese archivo.
    *   **Contextualización de Chunks:** Para cada chunk de texto, `embedding_manager.contextualize_chunk(chunk_text, document_title, source_filename, extra_metadata)` antepone información contextual como "Fuente del Archivo: {filename}" y "Título del Documento: {document_title}" al contenido del chunk.

5.  **Generación de Embeddings (realizado por `EmbeddingManager`):**
    *   `embedding_manager.generate_embeddings_for_chunks(contextualized_chunks, embedding_model)` itera sobre los chunks contextualizados.
    *   Para cada chunk, invoca `self.ai_wrapper.generate_embedding(text=chunk_text, model=embedding_model)` para obtener el vector de embedding del proveedor de IA configurado.
    *   Maneja errores durante la generación de embeddings para chunks individuales, permitiendo que el proceso continúe para los demás.

6.  **Preparación y Almacenamiento en Base de Datos (realizado por `EmbeddingManager` y `PgvectorWrapper`):**
    *   `embedding_manager.prepare_document_chunks_for_vector_db(...)` crea una lista de objetos `DocumentChunk` (modelo Pydantic). Cada `DocumentChunk` incluye:
        *   `id`: Un UUIDv4 único para el chunk.
        *   `course_id`, `document_id` (nombre del archivo).
        *   `text`: El texto original del chunk (no el contextualizado para el embedding).
        *   `embedding`: El vector de embedding generado.
        *   `metadata`: Un diccionario que contiene `course_id`, `document_id`, `source_filename`, `original_text`, y opcionalmente `document_title` y cualquier `additional_metadatas`.
    *   `pgvector_db.upsert_chunks(course_name_for_pgvector, db_chunks)` inserta o actualiza estos `DocumentChunk` en la tabla Pgvector correspondiente al curso.

7.  **Actualización del Tracker y Limpieza:**
    *   `pgvector_db.mark_file_as_processed(course_id, filename, timemodified)` actualiza la tabla de seguimiento de archivos con el timestamp de Moodle y el timestamp actual del procesamiento.
    *   El archivo descargado localmente (`downloaded_path`) se elimina (`downloaded_path.unlink(missing_ok=True)`).

8.  **Finalización y Manejo de Errores:**
    *   La tarea retorna un diccionario con el estado del procesamiento (`filename`, `status`, `chunks_upserted`, `task_id`).
    *   Un bloque `try...except...finally` robusto asegura que los errores se registren detalladamente (incluyendo traceback) y que la conexión a `PgvectorWrapper` (`pgvector_db.close_connection()`) se cierre siempre, independientemente del éxito o fallo de la tarea.

## **5. Herramientas y Tecnologías Clave del Proyecto**

El desarrollo de Entrenai se apoyó en un conjunto de tecnologías cuidadosamente seleccionadas, detalladas en `docker-compose.yml` y `requirements.txt`:

*   **Lenguaje de Programación:** Python 3.9+.
*   **Framework Backend:** FastAPI, con Uvicorn para el servidor ASGI.
*   **Plataforma LMS:** Moodle (Bitnami Moodle 4.5.4 sobre PostgreSQL 17.5).
*   **Modelos de Lenguaje (LLMs) y Embeddings:**
    *   **Ollama (0.6.8):** Para auto-alojar modelos de código abierto (ej. `nomic-embed-text` para embeddings, modelos tipo Llama/Mistral para generación de respuestas y formateo de texto). Cliente Python: `ollama`.
    *   **Google Gemini:** Como alternativa en la nube para generación de respuestas. Cliente Python: `google-genai`.
*   **Base de Datos Vectorial:** PostgreSQL (versión 16) con la extensión PGVector (imagen `pgvector/pgvector:pg16`). Cliente Python: `pgvector`.
*   **Automatización de Workflows:** N8N (versión 1.91.3, con backend PostgreSQL 17.5).
*   **Procesamiento Asíncrono de Tareas:**
    *   **Celery (5.3.6):** Para la gestión de colas y ejecución de tareas en segundo plano.
    *   **Redis (Alpine):** Como message broker para Celery y backend de resultados. Cliente Python: `redis==5.0.1`.
*   **Contenerización:** Docker y Docker Compose para definir, ejecutar y gestionar todos los servicios de la aplicación en entornos aislados.
*   **Procesamiento de Archivos (Bibliotecas Python):** `pdf2image`, `pytesseract`, `python-pptx`, `python-docx`, `beautifulsoup4`, `pandas`, `lxml`, `chardet`.
*   **Gestión de Entorno y Dependencias:** `python-dotenv` para variables de entorno, `requirements.txt` para dependencias.
*   **Herramientas de Desarrollo y Calidad:** `pytest`, `pytest-asyncio` para pruebas; `ruff` para linting y formateo; `uv` como gestor de paquetes y entorno virtual.
*   **Comunicación HTTP:** `requests` (síncrono), `aiohttp` (asíncrono).

## **6. Consideraciones sobre la Metodología Ágil**

El proyecto Entrenai adoptó un enfoque de desarrollo iterativo e incremental, alineado con los principios de las metodologías ágiles. Si bien no se siguió un framework ágil formal (como Scrum con todos sus roles y ceremonias), se aplicaron los siguientes aspectos clave:

*   **Desarrollo Iterativo e Incremental:** El sistema se construyó en ciclos cortos (sprints), añadiendo funcionalidades de manera progresiva y permitiendo la validación temprana.
*   **Colaboración Continua:** Las reuniones periódicas con el tutor del proyecto fueron fundamentales para obtener feedback, discutir avances, resolver bloqueos y re-priorizar tareas según fuera necesario.
*   **Adaptabilidad y Flexibilidad:** El equipo demostró capacidad para ajustar los planes y las tecnologías en respuesta a los desafíos y aprendizajes. Ejemplos de esto incluyen:
    *   La decisión de migrar de Qdrant a PGVector para la base de datos vectorial.
    *   La evaluación y posterior descarte de OpenWebUI en favor de N8N para el chat.
    *   La simplificación del sistema de procesamiento asíncrono, optando por Celery en lugar de una arquitectura más compleja con RabbitMQ y ByteWax.
*   **Enfoque en el Producto Mínimo Viable (MVP):** Se priorizaron las funcionalidades esenciales para entregar valor tangible rápidamente y obtener retroalimentación temprana.
*   **Pruebas Continuas:** Aunque no se detalla un framework de CI/CD completo, la existencia de un directorio `tests/` y el uso de `pytest` sugieren una intención de realizar pruebas regulares.

Esta aproximación metodológica permitió navegar la incertidumbre inherente a un proyecto de desarrollo con componentes de investigación, facilitando una evolución constante y la entrega de un producto funcional.

## **7. Desafíos y Soluciones Implementadas**

Durante el ciclo de vida del proyecto, se presentaron diversos desafíos técnicos y de diseño, los cuales fueron abordados de la siguiente manera:

*   **Complejidad de la Integración de Múltiples Servicios:** La interconexión de Moodle, Ollama, PGVector, N8N, Celery y Redis requirió una cuidadosa configuración y orquestación.
    *   **Solución:** El uso extensivo de Docker y Docker Compose fue crucial para estandarizar los entornos y simplificar el despliegue y la comunicación entre servicios. La API de FastAPI actuó como el principal orquestador.
*   **Limitaciones de la API de Moodle:** La API de Moodle presentó restricciones, como la incapacidad de crear carpetas programáticamente dentro de secciones de cursos de manera directa y sencilla.
    *   **Solución:** Se optó por un enfoque mixto donde el sistema crea la sección y los enlaces, pero se provee un instructivo al profesor para la creación manual de la carpeta designada para los documentos.
*   **Gestión del Procesamiento Asíncrono:** Inicialmente se consideraron arquitecturas más complejas para el procesamiento de archivos (RabbitMQ, ByteWax).
    *   **Solución:** Se simplificó el enfoque utilizando Celery con Redis, lo cual proporcionó la robustez necesaria para el procesamiento en segundo plano sin una sobrecarga excesiva de configuración.
*   **Optimización del Flujo RAG:** Asegurar que los chunks recuperados fueran relevantes y que los prompts generaran respuestas precisas fue un proceso iterativo.
    *   **Solución:** Experimentación con diferentes estrategias de chunking, modelos de embedding (vía Ollama), y refinamiento de los prompts enviados al LLM generador. La elección de modelos específicos como `nomic-embed-text` fue parte de esta optimización.
*   **Manejo de Diversos Formatos de Archivo:** La extracción de texto de manera consistente y precisa desde PDF (especialmente escaneados), DOCX y PPTX.
    *   **Solución:** Uso de un conjunto de bibliotecas especializadas (`pdf2image`, `pytesseract`, `python-docx`, `python-pptx`) y la implementación de una capa de formateo de texto (posiblemente usando un LLM vía Ollama) para normalizar el contenido extraído a Markdown antes del chunking.

## **8. Conclusión de la Metodología**

La metodología empleada en el proyecto Entrenai, caracterizada por su naturaleza iterativa, la adaptación continua y la integración de feedback constante, ha demostrado ser efectiva para abordar la complejidad del desarrollo de un sistema de IA integrado. La combinación de una planificación inicial seguida de sprints de desarrollo enfocados, junto con la selección estratégica de tecnologías de código abierto y la robusta orquestación mediante Docker, permitió la construcción progresiva de un sistema funcional que cumple con los objetivos principales del proyecto.

Las decisiones de diseño, como la migración a PGVector o la simplificación del procesamiento asíncrono, reflejan un proceso de aprendizaje y adaptación continuo, fundamental en proyectos de esta índole. La documentación detallada en cada fase y la estructura modular del sistema sientan las bases para futuras expansiones y el mantenimiento del producto. El enfoque metodológico ha permitido no solo desarrollar el software, sino también generar un conocimiento profundo sobre la integración de estas tecnologías en el contexto educativo.
