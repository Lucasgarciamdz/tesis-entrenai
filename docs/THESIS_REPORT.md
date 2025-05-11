# Título de la Tesis: Entrenai - Sistema Inteligente de Asistencia al Estudiante Basado en RAG para Cursos de Moodle

## Resumen

(Se completará al final del proyecto)

## 1. Introducción

### 1.1. Contexto y Motivación
### 1.2. Problema a Resolver
### 1.3. Objetivos
    *   Objetivo General
    *   Objetivos Específicos
### 1.4. Justificación
### 1.5. Alcance y Limitaciones
### 1.6. Estructura del Documento

## 2. Marco Teórico

### 2.1. Plataformas LMS (Moodle)
### 2.2. Modelos de Lenguaje Grandes (LLMs)
### 2.3. Generación Aumentada por Recuperación (RAG)
### 2.4. Bases de Datos Vectoriales (Qdrant)
### 2.5. Herramientas de Automatización de Workflows (N8N)
### 2.6. Procesamiento de Lenguaje Natural (NLP) y Embeddings
### 2.7. Tecnologías Relacionadas (FastAPI, Ollama, Docker)

## 3. Diseño y Metodología del Sistema "Entrenai"

### 3.1. Arquitectura General del Sistema
    *   Diagrama de Arquitectura
    *   Descripción de Componentes
### 3.2. Flujo de Usuario y Datos
    *   Configuración Inicial por el Profesor
    *   Subida y Procesamiento de Archivos
    *   Interacción del Estudiante con el Chatbot
### 3.3. Tecnologías Utilizadas
    *   Listado y justificación
### 3.4. Diseño de la Base de Datos Vectorial (Qdrant)
    *   Estructura de Colecciones
    *   Formato de los Puntos (Chunks y Metadatos)
### 3.5. Diseño del Workflow de Chat (N8N)
### 3.6. Procesamiento y Extracción de Contenido de Archivos
### 3.7. Generación y Gestión de Embeddings
### 3.8. Metodología de Desarrollo
    *   Iterativa e Incremental
    *   Pruebas (Testing)

## 4. Implementación

### 4.1. Configuración del Entorno de Desarrollo
    *   Dockerización de Servicios (Moodle, Qdrant, Ollama, N8N)
### 4.2. Desarrollo del Backend (FastAPI)
    *   Endpoints de la API
    *   Integración con Moodle Web Services (`MoodleClient`)
    *   Integración con Qdrant (`QdrantWrapper`)
    *   Integración con Ollama (`OllamaWrapper`)
    *   Integración con N8N API (`N8NClient`)
### 4.3. Implementación del Procesamiento de Archivos
    *   `FileProcessor`, `EmbeddingManager`, `FileTracker`
### 4.4. Configuración del Workflow en N8N
### 4.5. Desafíos Encontrados y Soluciones Aplicadas

## 5. Pruebas y Resultados

### 5.1. Estrategia de Pruebas
    *   Pruebas Unitarias
    *   Pruebas de Integración (con servicios reales)
### 5.2. Casos de Prueba
### 5.3. Resultados Obtenidos
    *   Funcionalidad del sistema
    *   Calidad de las respuestas del chatbot (evaluación cualitativa/cuantitativa si es posible)
    *   Rendimiento (tiempos de procesamiento, respuesta del chat)

## 6. Conclusiones y Trabajo Futuro

### 6.1. Conclusiones Principales
### 6.2. Cumplimiento de Objetivos
### 6.3. Limitaciones del Sistema Desarrollado
### 6.4. Líneas de Trabajo Futuro
    *   Mejoras en el RAG (re-ranking, contextualización avanzada)
    *   Soporte para más tipos de archivo
    *   Interfaz de profesor más elaborada
    *   Mecanismos de feedback del estudiante
    *   Escalabilidad

## 7. Referencias Bibliográficas

## Apéndices

### Apéndice A: Manual de Usuario (Profesor y Estudiante)
### Apéndice B: Configuración de Variables de Entorno
### Apéndice C: Código Fuente Relevante (Fragmentos)
