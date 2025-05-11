# Project Design - Entrenai

## 1. Introducción

Este documento detalla la arquitectura, decisiones de diseño, estructura de datos y flujos del proyecto Entrenai.

## 2. Arquitectura General

(Se detallará más adelante)

### Componentes Principales:
*   **Frontend (Interfaz de Profesor):** (Aún por definir si se construye o se simula)
*   **Backend (FastAPI):** Orquesta las operaciones.
*   **Moodle:** Plataforma LMS.
*   **Qdrant:** Base de datos vectorial para embeddings.
*   **Ollama:** Para ejecución local de LLMs.
*   **N8N:** Para el workflow del chat de estudiantes.

## 3. Flujo de Datos y Procesos

(Se detallará según las especificaciones del usuario)

### 3.1. Configuración Inicial (Profesor)
### 3.2. Subida y Procesamiento de Archivos
### 3.3. Interacción con el Chat (Estudiante)

## 4. Estructura de Directorios

(Se detallará la estructura final)

## 5. Clases y Módulos Principales

(Se describirán las responsabilidades de cada uno)

### 5.1. `src/entrenai/config.py`
### 5.2. `src/entrenai/core/moodle_client.py`
### 5.3. `src/entrenai/core/n8n_client.py`
### 5.4. `src/entrenai/core/qdrant_wrapper.py`
### 5.5. `src/entrenai/core/ollama_wrapper.py`
### 5.6. `src/entrenai/core/file_processor.py`
### 5.7. `src/entrenai/core/embedding_manager.py`
### 5.8. `src/entrenai/core/file_tracker.py`
### 5.9. `src/entrenai/api/main.py`

## 6. Decisiones de Diseño

(Se registrarán las decisiones importantes y sus justificaciones)

## 7. Esquema de la Base de Datos (Qdrant)

(Se describirá la estructura de las colecciones y los puntos)

## 8. Configuración de N8N

(Se detallará el workflow del chat)

## 9. Variables de Entorno

(Se listarán las variables necesarias)
