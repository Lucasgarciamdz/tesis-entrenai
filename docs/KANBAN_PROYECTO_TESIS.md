# Tablero Kanban: Proyecto Asistente IA para Cátedras Moodle

Este documento detalla el progreso y la planificación de tareas para el proyecto de desarrollo de un asistente de IA personalizado para las cátedras de Moodle en la Universidad de Mendoza.

**Desarrollador Principal:** Lucas García

## Tareas Realizadas (Primer Sprint - Aprox. 6 semanas, 108 horas)

Esta sección cubre las tareas completadas durante el primer ciclo de desarrollo.

---

**Título:** Como desarrollador, quiero un entorno local funcional y un repositorio versionado, para comenzar el desarrollo de manera organizada.
**Descripción:** Se configuraron las herramientas base (Python, Docker, etc.) y se creó el repositorio en GitHub (#2990) junto con el entorno de desarrollo local (#2499) para iniciar el proyecto.
**Horas Estimadas:** 10h

---

**Título:** Como desarrollador, quiero establecer comunicación con Moodle vía API, para acceder a la información de cursos y archivos.
**Descripción:** Se activó el WebService REST de Moodle, se instaló un plugin para la gestión de secciones y se configuró un usuario API con token para la autenticación, permitiendo el acceso a datos de Moodle.
**Horas Estimadas:** 12h

---

**Título:** Como desarrollador, quiero investigar e implementar un sistema RAG inicial, para permitir consultas sobre documentos de la cátedra.
**Descripción:** Se investigó e implementó un sistema RAG (#2500) mediante una prueba de concepto con Quadrant y Ollama. Se crearon scripts en Python (`quadrant-client`) para la gestión de embeddings.
**Horas Estimadas:** 20h

---

**Título:** Como desarrollador, quiero un entorno backend v1, para conectar RAG con modelo local y gestionar archivos.
**Descripción:** Se desarrolló un backend (#2840) para la descarga de archivos de Moodle, su procesamiento, generación de embeddings con Ollama y almacenamiento en Quadrant.
**Horas Estimadas:** 18h

---

**Título:** Como desarrollador, quiero un entorno N8N configurado y refinado, para la interacción del chatbot y la conexión con modelos.
**Descripción:** Se configuró y mejoró un entorno N8N (#2906) para el RAG, manejo de memoria y conexión con modelos. Se actualizó la lógica del workflow y se añadió capacidad de edición de prompts (basado en commits `4021244`, `5895a60`).
**Horas Estimadas:** 18h

---

**Título:** Como profesor, quiero una interfaz intuitiva y mejorada, para configurar el asistente y gestionar archivos.
**Descripción:** Se desarrolló y mejoró significativamente la UI del profesor en términos de UX, responsividad y gestión de archivos (basado en commits `8388705`, `983adc0`, `2d86e65`), incluyendo la creación automática de la sección en Moodle.
**Horas Estimadas:** 20h

---

**Título:** Como desarrollador, quiero optimizar el almacenamiento de embeddings y la gestión de tareas asíncronas, para mejorar la eficiencia del sistema.
**Descripción:** Se optimizó el sistema migrando a PgVector (commits `161294d`, `2f74e06`), configurando Celery con Redis para tareas asíncronas (commit `a82f3ac`), y ajustando el soporte para Google Gemini (posiblemente `c059763`).
**Horas Estimadas:** 22h

---

**Título:** Como desarrollador, quiero documentación actualizada y reestructurada en español, para facilitar su comprensión y mantenimiento.
**Descripción:** Se realizó una actualización y reestructuración integral de la documentación del proyecto en español (basado en commit `aaf24a1` y merge `4c4f311`).
**Horas Estimadas:** 8h

---

## Tareas Pendientes (Segundo Sprint y Futuras)

Esta sección detalla las tareas planificadas para las siguientes fases del proyecto.

---

**Título:** Como profesor, quiero personalizar el chatbot N8N desde Moodle, para adaptar el asistente al tono de mi cátedra.
**Descripción:** Se busca permitir que el profesor pueda configurar aspectos como el mensaje inicial y el prompt del sistema del chatbot directamente desde Moodle, y que estos cambios se reflejen en el workflow de N8N.

---

**Título:** Como desarrollador, quiero que Celery ejecute tareas vía HTTP, para desacoplar workers y simplificar el mantenimiento.
**Descripción:** Se refactorizará Celery para que actúe como un disparador de tareas mediante HTTP requests a la aplicación FastAPI, desacoplando los workers de la lógica principal para simplificar el despliegue y mantenimiento.

---

**Título:** Como profesor, quiero que se eliminen embeddings al borrar archivos, para mantener la consistencia de la base de datos vectorial.
**Descripción:** Se implementará la lógica necesaria para que, al eliminar un archivo en Moodle, sus embeddings asociados se eliminen de la base de datos PgVector, evitando respuestas con contenido obsoleto.

---

**Título:** Como desarrollador, quiero procesadores de archivos robustos, para asegurar la correcta extracción de contenido para embeddings.
**Descripción:** Se verificarán y robustecerán todos los procesadores de archivos (PDF, DOCX, PPTX, Markdown, TXT) para garantizar una extracción de contenido fiable y la correcta generación de embeddings.

---

**Título:** Como profesor, quiero una UI de gestión de archivos más completa y amigable, para administrar eficientemente los recursos del asistente.
**Descripción:** Se mejorará la interfaz de usuario (#2846) para que los profesores puedan administrar los archivos del asistente (visualizar, subir, eliminar) de forma más completa y amigable.

---

**Título:** Como alumno, quiero que los modelos ofrezcan respuestas más específicas y precisas, para mejorar la calidad del aprendizaje.
**Descripción:** Se trabajará en la optimización de los modelos (#2847) para que las respuestas a las consultas de los alumnos sean más relevantes y exactas respecto al contenido de la cátedra.

---

**Título:** Como alumno, quiero un servicio de consultas estable y eficiente, para resolver dudas de la cátedra de forma fiable.
**Descripción:** Se implementará y robustecerá un servicio (#2842) que permita a los alumnos realizar consultas a los modelos de forma estable y eficiente para resolver dudas de la cátedra.

---

**Título:** Como profesor, quiero explorar la actualización dinámica de la cátedra por modelos, para mantenerla actualizada y enriquecida.
**Descripción:** Se investigará la viabilidad (#2845) de que los modelos, con supervisión, puedan sugerir o modificar contenido de la cátedra virtual para mantenerla actualizada.

---

**Título:** Como desarrollador, quiero añadir contexto semántico avanzado a los chunks, para mejorar la calidad del RAG.
**Descripción:** Se explorará la implementación de un sistema para que cada chunk de texto tenga un contexto más personalizado y detallado, potencialmente usando un agente de IA adicional, para mejorar la calidad del RAG.

---

**Título:** Como desarrollador, quiero limpiar código, mejorar documentación y realizar pruebas exhaustivas, para asegurar la calidad y mantenibilidad.
**Descripción:** Se realizará una fase de limpieza de código, mejora de la documentación técnica y de usuario, y la ejecución de un plan de pruebas completo (unitarias, integración, E2E) para asegurar la calidad.

---

**Título:** Como desarrollador, quiero preparar la aplicación para Kubernetes, para facilitar su escalabilidad y gestión en producción.
**Descripción:** Se diseñará y configurará la aplicación para ser desplegable en Kubernetes (#2919), considerando la automatización del despliegue para facilitar su gestión y escalabilidad.

---

## Tareas Descartadas

Esta sección lista las tecnologías o enfoques que se consideraron pero finalmente no se implementaron.

---

**Título:** Utilizar Quadrant como base de datos vectorial principal
**Descripción:** Se evaluó y probó Quadrant, pero se descartó a favor de PostgreSQL con PgVector debido a una mejor integración con N8N y el ecosistema Python del proyecto.

---

**Título:** Implementar arquitectura compleja con MongoDB, RabbitMQ y ByteWax
**Descripción:** Se consideró una arquitectura basada en MongoDB para el almacenamiento de archivos, RabbitMQ para la cola de mensajes y ByteWax para el procesamiento de datos. Se descartó por su complejidad en favor de una solución más simple con Celery y Redis.

---

**Título:** Utilizar OpenWebUI para la interfaz de chat
**Descripción:** Se evaluó OpenWebUI como posible interfaz para el chatbot, pero se optó por integrar la funcionalidad de chat directamente dentro de N8N para una mayor cohesión con el workflow de procesamiento.

---
