# Documentación de la Refactorización - Proyecto EntrenAI

Este documento sirve como bitácora de los cambios realizados durante la reescritura del proyecto EntrenAI. El objetivo principal es mejorar la calidad del código, la legibilidad y la mantenibilidad, traduciendo todos los componentes posibles al español y siguiendo las mejores prácticas de desarrollo en Python.

## Proceso de Refactorización

El proceso se dividirá en varias fases, abordando sistemáticamente cada componente de la aplicación:

1.  **Configuración Base**: Ajuste de la carga de variables de entorno y el sistema de logging.
2.  **Núcleo de la Aplicación**: Refactorización de la lógica de negocio, incluyendo la interacción con la base de datos, clientes de APIs externas, procesamiento de archivos y los módulos de IA.
3.  **Capa de API**: Reestructuración de los endpoints, modelos de datos y la aplicación principal de FastAPI.
4.  **Tareas Asíncronas con Celery**: Modificación de la arquitectura de Celery para desacoplarlo de la lógica principal.
5.  **Archivos de Despliegue**: Actualización de Dockerfiles, Docker Compose y Makefile.
6.  **Documentación Final**: Consolidación de la documentación técnica y de usuario.

---

## Registro de Cambios

### Fase 1: Configuración y Estructura Inicial

*   **[PENDIENTE]** `configuracion/configuracion.py`: Traducir y simplificar la carga de configuraciones.
*   **[PENDIENTE]** `configuracion/registrador.py`: Estandarizar y traducir el módulo de logging.
*   **[PENDIENTE]** `nucleo/bd/envoltorio_pgvector.py`: Reescribir el wrapper de la base de datos vectorial.
*   **[PENDiente]** ... y así sucesivamente con el resto de los archivos.
