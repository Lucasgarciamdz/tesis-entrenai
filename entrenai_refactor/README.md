# EntrenAI - Plataforma Inteligente para Cursos (Refactorizado)

Bienvenido a EntrenAI, una plataforma diseñada para potenciar la experiencia de aprendizaje en Moodle mediante la creación de inteligencias artificiales personalizadas basadas en el contenido de los cursos.

Este proyecto es una versión refactorizada, enfocada en la claridad del código, la mantenibilidad y el uso extensivo del español en su desarrollo.

## Descripción General

EntrenAI permite a los profesores subir archivos y materiales de curso a Moodle. Por detrás, estos materiales se procesan y se utilizan para alimentar una base de datos vectorial. Luego, se proporciona un chatbot (a través de N8n) que los estudiantes pueden usar para hacer preguntas y obtener respuestas basadas en el contenido del curso, facilitando así una herramienta de aprendizaje interactiva y personalizada.

## Funcionalidades Principales (Objetivo de la Refactorización)

*   **Integración con Moodle:** Conexión con Moodle para gestionar cursos y archivos.
*   **Procesamiento de Archivos:** Capacidad para procesar diversos formatos de archivo (PDF, Word, PowerPoint, Markdown, texto).
*   **Base de Datos Vectorial:** Uso de PostgreSQL con la extensión pgvector para almacenar embeddings de los contenidos.
*   **Inteligencia Artificial:** Integración con modelos de lenguaje como Gemini y Ollama para generar respuestas y embeddings.
*   **Chatbot Interactivo:** Interfaz de chatbot proporcionada a través de N8n.
*   **API Robusta:** Un backend desarrollado con FastAPI para gestionar todas las operaciones.
*   **Tareas Asíncronas:** Uso de Celery para manejar procesos largos (como el procesamiento de archivos) de forma eficiente, delegando la lógica principal a la API mediante peticiones HTTP.

## Estructura del Proyecto (en `entrenai_refactor/`)

*   `/api`: Contiene la lógica de la API FastAPI (rutas, modelos, lógica principal).
*   `/celery`: Configuración y tareas del worker Celery.
*   `/config`: Módulos de configuración y logging.
*   `/docs`: Documentación del proyecto (como este README y el changelog).
*   `/nucleo`: El corazón de la aplicación, con la lógica de negocio (IA, clientes externos, BD, procesamiento de archivos).
*   `Dockerfile`, `Dockerfile.celery`: Para construir las imágenes Docker de la aplicación y el worker.
*   `docker-compose.yml`: Para orquestar todos los servicios necesarios (API, worker, bases de datos, Moodle, N8n, Ollama).
*   `Makefile`: Comandos útiles para desarrollo, pruebas y gestión de servicios.
*   `requirements.txt`, `requirements.celery.txt`: Dependencias del proyecto.

## Puesta en Marcha (Próximamente)

Las instrucciones detalladas para la configuración del entorno de desarrollo y el despliegue de la aplicación se añadirán aquí una vez la refactorización avance.

## Contribuciones

Este proyecto está actualmente en una fase de refactorización intensiva.

---
*Este README se irá actualizando conforme avance la refactorización.*
