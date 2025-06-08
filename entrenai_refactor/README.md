# Refactor de EntrenAI

Este proyecto es una reescritura completa y simplificada de la aplicación original Entrenai, orientada a la gestión de inteligencia artificial personalizada para cátedras de Moodle. Todo el código, documentación y estructura están en español.

## Entrenai - Asistente Inteligente para Cursos en Moodle (Descripción Original)

Entrenai es una herramienta innovadora diseñada para ayudar a estudiantes y profesores en la plataforma Moodle. Imagina que tienes un asistente personal para cada uno de tus cursos: Entrenai analiza los materiales que subes (como documentos PDF, Word, PowerPoint) y luego responde las preguntas de los estudiantes basándose únicamente en esa información.

**¿Cuál es el objetivo de Entrenai?** Facilitar que los estudiantes encuentren la información que necesitan de manera rápida y sencilla, directamente en Moodle, a través de un chat amigable. Esto les ayuda a comprender mejor los temas del curso y a ti, como profesor, te permite ofrecer un apoyo constante.

## Objetivo de esta Refactorización

El objetivo principal de esta refactorización es:
*   Simplificar la base de código original.
*   Mejorar la organización general del proyecto.
*   Mantener toda la funcionalidad clave de Entrenai.
*   Traducir completamente el código, los comentarios y la documentación al español.
*   Adherirse a las buenas prácticas de desarrollo en Python.
*   Facilitar la mantenibilidad y futuras expansiones.

## Estructura Principal del Proyecto Refactorizado (`entrenai_refactor`)

El proyecto se organiza de la siguiente manera dentro del directorio `entrenai_refactor/`:

-   `api/`: Contiene todos los endpoints y la lógica de la API desarrollada con FastAPI. Es el punto de entrada para las interacciones con el sistema.
-   `nucleo/`: Es el corazón de la aplicación. Aquí reside la lógica de negocio principal, incluyendo:
    *   Interacción con modelos de Inteligencia Artificial.
    *   Clientes para servicios externos (como Moodle, N8N).
    *   Gestión y acceso a la base de datos (PGVector).
    *   Procesamiento y análisis de archivos.
-   `config/`: Módulos para la carga de configuración de la aplicación y la gestión de logs.
-   `celery/`: Implementación de tareas asíncronas utilizando Celery, permitiendo que procesos largos (como el procesamiento de documentos) se ejecuten en segundo plano sin bloquear la API.
-   `docs/`: Documentación técnica y funcional del proyecto refactorizado.
-   `Dockerfile`, `Dockerfile.celery`: Archivos para construir las imágenes de Docker para la aplicación API y el worker de Celery, respectivamente.
-   `docker-compose.yml`: Define los servicios, redes y volúmenes para orquestar la aplicación completa con Docker Compose (API, worker, bases de datos, etc.).
-   `Makefile`: Proporciona comandos útiles para automatizar tareas comunes como instalación, ejecución local, gestión de servicios Docker, etc.
-   `requirements.txt`, `requirements.celery.txt`: Listados de dependencias Python para la aplicación principal y el worker de Celery.

## ¿Qué puede hacer Entrenai por ti y tus estudiantes? (Características Principales)

*   **Se integra fácilmente con tus cursos de Moodle:** Puedes activar Entrenai para los cursos que elijas. El sistema preparará automáticamente un espacio en tu curso Moodle para los materiales y el chat.
*   **Entiende los documentos de tu curso:** Sube tus archivos (PDF, DOCX, PPTX, TXT, etc.) y Entrenai leerá y procesará el texto.
*   **Organiza la información de forma inteligente:** Entrenai utiliza una técnica especial para catalogar y encontrar la información relevante dentro de los documentos cuando un estudiante hace una pregunta.
*   **Un Chatbot siempre disponible para los estudiantes:** Los alumnos pueden hacer preguntas en un chat y Entrenai usará la información de los documentos del curso para generar respuestas claras y contextualizadas. ¡Es como tener un tutor disponible 24/7 para resolver dudas sobre el material!
*   **Fácil de usar para el profesor:** Incluye una interfaz sencilla para que puedas seleccionar tus cursos y activar la inteligencia artificial para ellos.

## ¿Cómo funciona? (Flujo Simplificado)

**Para el Profesor:**

1.  **Configuración Sencilla:** Desde una pantalla simple, seleccionas el curso de Moodle para el que quieres activar Entrenai. Con un clic, el sistema prepara todo lo necesario en tu curso Moodle: una nueva sección, una carpeta para que subas los documentos que la IA analizará, y un enlace al chat para los estudiantes.
2.  **Subida de Materiales:** Simplemente sube los archivos del curso (PDFs, presentaciones, apuntes) a la carpeta creada por Entrenai en Moodle.
3.  **¡Listo!** Entrenai procesará estos archivos. Si actualizas o añades nuevos documentos, puedes pedirle a Entrenai que los "refresque" para que siempre tenga la información más reciente.

**Para el Estudiante:**

1.  **Acceso al Chat:** El estudiante encontrará un enlace en el curso de Moodle para acceder al chat de Entrenai.
2.  **Realizar Preguntas:** Escribe sus dudas o preguntas sobre el material del curso en el chat.
3.  **Respuestas Basadas en el Contenido:** Entrenai buscará en los documentos proporcionados por el profesor y generará una respuesta lo más precisa posible, ayudando al estudiante a entender mejor el tema.

## Beneficios Clave

*   **Para Estudiantes:**
    *   Acceso rápido a información específica del curso.
    *   Resolución de dudas al instante, incluso fuera del horario de clase.
    *   Mejora la comprensión del material de estudio.
*   **Para Profesores:**
    *   Reduce la carga de trabajo respondiendo preguntas frecuentes.
    *   Proporciona una herramienta de apoyo adicional para los estudiantes.
    *   Fomenta un aprendizaje más autónomo.

## Cómo ejecutar este proyecto refactorizado

Para trabajar con este proyecto refactorizado, asegúrate de estar en el directorio `entrenai_refactor/`.

### Usando Makefile (Recomendado para desarrollo local)

El `Makefile` dentro de `entrenai_refactor/` proporciona varios comandos útiles:

1.  **Instalar dependencias en un entorno virtual:**
    ```bash
    make instalar
    ```
    Esto creará un entorno virtual `.venv` dentro de `entrenai_refactor/` e instalará las dependencias de `requirements.txt`.

2.  **Ejecutar la aplicación API localmente:**
    ```bash
    make correr
    ```
    Esto iniciará el servidor FastAPI (usando Uvicorn) con recarga automática. Necesitarás tener un archivo `.env` configurado en la raíz del proyecto (un nivel arriba de `entrenai_refactor/`).

3.  **Ejecutar el worker de Celery localmente:**
    ```bash
    make correr-worker-celery
    ```
    Esto iniciará un worker de Celery. También requiere el `.env` configurado.

4.  **Levantar todos los servicios con Docker Compose:**
    ```bash
    make servicios-levantar
    ```
    Esto utilizará `entrenai_refactor/docker-compose.yml` para construir y levantar todos los servicios (API, worker, bases de datos, etc.).

5.  **Bajar los servicios de Docker Compose:**
    ```bash
    make servicios-bajar
    ```

### Usando Docker Compose directamente

Si prefieres no usar `make`, puedes ejecutar los comandos de Docker Compose directamente desde el directorio `entrenai_refactor/`:

1.  **Levantar servicios:**
    ```bash
    docker compose up --build -d
    ```
2.  **Bajar servicios:**
    ```bash
    docker compose down
    ```
3.  **Ver logs:**
    ```bash
    docker compose logs -f
    ```

Asegúrate de tener un archivo `.env` configurado en la raíz del proyecto, ya que `entrenai_refactor/docker-compose.yml` está configurado para usar `../.env`.

## Documentación Adicional

Entrenai busca ser un aliado tanto para profesores como para estudiantes, haciendo el proceso de enseñanza y aprendizaje en Moodle más eficiente y interactivo.

Para más detalles técnicos sobre la refactorización y el registro de cambios específico de esta versión, consulte `docs/documentacion.md`.
La documentación original del proyecto (informe de tesis, manuales) se encuentra en el directorio `docs/` del repositorio raíz.
