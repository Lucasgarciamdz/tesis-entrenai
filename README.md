# Entrenai - Sistema Inteligente de Asistencia al Estudiante

Entrenai es un sistema diseñado para proveer asistencia inteligente a estudiantes dentro de cursos específicos de Moodle. Utiliza un enfoque de Generación Aumentada por Recuperación (RAG) para responder preguntas basadas en el material del curso proporcionado por el profesor.

## Características Principales (Planeadas)

*   Integración con Moodle para la gestión de cursos y archivos.
*   Procesamiento de diversos tipos de archivos (PDF, DOCX, PPTX, etc.) para extraer contenido.
*   Generación de embeddings a partir del contenido y almacenamiento en una base de datos vectorial (Qdrant).
*   Uso de modelos de lenguaje grandes (LLMs) locales a través de Ollama para la generación de respuestas.
*   Un chatbot (implementado con N8N) que permite a los estudiantes realizar preguntas sobre el material del curso.
*   API backend desarrollada con FastAPI para orquestar todas las operaciones.

## Tecnologías

*   **Python 3.9+**
*   **FastAPI:** Para la API backend.
*   **Moodle:** Plataforma LMS.
*   **Qdrant:** Base de datos vectorial.
*   **Ollama:** Para correr LLMs localmente.
*   **N8N:** Para el workflow del chatbot.
*   **Docker & Docker Compose:** Para la gestión de servicios y entorno de desarrollo.
*   **Bibliotecas Python:** `requests`, `qdrant-client`, `ollama`, `python-dotenv`, `pytest`, `pdf2image`, `pytesseract`, `python-pptx`, `python-docx`, `beautifulsoup4`, `pandas`.

## Estructura del Proyecto

```
entrenai_project/
├── src/
│   └── entrenai/
│       ├── core/         # Clientes (Moodle, N8N), Wrappers (Qdrant, Ollama), Procesadores de archivos, etc.
│       ├── api/          # Aplicación FastAPI, endpoints
│       ├── utils/        # Módulos de utilidad
│       ├── config.py     # Clases de configuración para variables de entorno
│       └── __init__.py
├── tests/                # Pruebas Pytest
├── docs/                 # Documentación del proyecto (PROJECT_DESIGN.md, THESIS_REPORT.md)
├── .env.example          # Ejemplo de archivo de variables de entorno
├── docker-compose.yml    # Configuración de Docker Compose para servicios externos
├── Makefile              # Comandos útiles (setup, run, test, lint, etc.)
├── requirements.txt      # Dependencias de Python
├── MEMORY_BANK.md        # Registro de progreso y decisiones
└── README.md             # Este archivo
```

## Instalación y Configuración

1.  **Clonar el repositorio:**
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd entrenai_project
    ```

2.  **Configurar Variables de Entorno:**
    Copiar `.env.example` a `.env` y completar los valores necesarios.
    ```bash
    cp .env.example .env
    # Editar .env con tus configuraciones
    ```

3.  **Construir y Levantar Servicios Docker:**
    Esto levantará Moodle, Qdrant, Ollama, N8N y sus bases de datos.
    ```bash
    make services-up # O directamente: docker-compose up -d --build
    ```
    *Nota: La primera vez que se levante Moodle, puede requerir configuración manual a través de su interfaz web.*

4.  **Crear Entorno Virtual e Instalar Dependencias:**
    ```bash
    make setup
    ```

## Cómo Ejecutar

1.  **Asegurarse que los servicios Docker estén corriendo:**
    ```bash
    docker-compose ps
    # O make services-up si no están corriendo
    ```

2.  **Ejecutar la aplicación FastAPI:**
    ```bash
    make run
    ```
    La API estará disponible en `http://localhost:8000` (o el puerto configurado).

## Cómo Correr Tests

```bash
make test
```

## Contribuir

(Se detallará más adelante si aplica)

## Licencia

(Se definirá más adelante)
