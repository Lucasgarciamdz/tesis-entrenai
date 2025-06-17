# EntrenAI - Versión Simplificada

EntrenAI simplificado y refactorizado para configurar asistentes de IA en cursos de Moodle.

## Características

- **Simplificado**: Código limpio, fácil de entender y mantener
- **Modular**: Arquitectura basada en servicios independientes
- **Flexible**: Soporte para múltiples proveedores de IA (Ollama, Gemini)
- **Eficiente**: Vector store con pgvector para búsquedas semánticas
- **Fácil deployment**: Docker Compose incluido

## Arquitectura

```
src/entrenai/
├── config.py           # Configuración centralizada
├── models.py           # Modelos de datos
├── clients/            # Clientes para servicios externos
│   ├── moodle.py      # Cliente de Moodle
│   └── n8n.py         # Cliente de N8N
├── ai/                 # Proveedores de IA
│   └── providers.py   # Ollama y Gemini
├── db/                 # Base de datos
│   └── vector_store.py # Store de vectores
├── core/               # Lógica de negocio
│   ├── setup.py       # Setup de cursos
│   ├── chat.py        # Servicio de chat
│   └── document_processor.py # Procesador de documentos
└── api/                # API REST
    └── main.py        # Endpoints principales
```

## Instalación Rápida

1. **Clonar y configurar**:
```bash
cd final/
cp .env.example .env
# Editar .env con tu configuración
```

2. **Levantar servicios**:
```bash
make services-up  # PostgreSQL + Redis
```

3. **Instalar dependencias**:
```bash
make install
```

4. **Ejecutar en desarrollo**:
```bash
make dev
```

## Uso Principal

### 1. Configurar IA para un curso

```bash
curl -X POST "http://localhost:8000/courses/123/setup" \
  -H "Content-Type: application/json" \
  -d '{"course_name": "Mi Curso"}'
```

### 2. Subir documentos

```bash
curl -X POST "http://localhost:8000/courses/123/documents/upload" \
  -F "files=@documento.pdf" \
  -F "files=@otro_archivo.txt"
```

### 3. Chat con contexto del curso

```bash
curl -X POST "http://localhost:8000/courses/123/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuáles son los objetivos del curso?"}'
```

## Configuración

### Variables de Entorno

- `AI_PROVIDER`: Proveedor de IA (`ollama` o `gemini`)
- `OLLAMA_HOST`: URL de Ollama (ej: `http://localhost:11434`)
- `GEMINI_API_KEY`: API Key de Google Gemini
- `MOODLE_URL`: URL de tu Moodle
- `MOODLE_TOKEN`: Token de API de Moodle

### Providers de IA

**Ollama (Local)**:
```env
AI_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

**Google Gemini**:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=tu_api_key
GEMINI_MODEL=gemini-pro
```

## Docker

**Todo en Docker**:
```bash
make up
```

**Solo servicios auxiliares**:
```bash
make services-up
make dev
```

## API Endpoints

- `POST /courses/{id}/setup` - Configurar IA para curso
- `GET /courses/{id}/status` - Estado de configuración
- `POST /courses/{id}/chat` - Chat con contexto
- `POST /courses/{id}/documents/upload` - Subir documentos
- `POST /courses/{id}/documents/text` - Añadir texto directo
- `DELETE /courses/{id}/cleanup` - Limpiar configuración

## Comparación con Versión Original

| Aspecto | Original | Simplificado |
|---------|----------|--------------|
| Líneas de código | ~3000+ | ~800 |
| Archivos | 20+ | 8 principales |
| Configuración | Múltiples archivos | 1 archivo |
| Manejo de errores | Muy complejo | Esencial |
| Dependencias | 30+ | 10 |
| Setup básico | 100+ líneas | 30 líneas |

## Características Mantenidas

✅ Setup automático de cursos
✅ Chat con contexto
✅ Vector store para documentos  
✅ Múltiples proveedores IA
✅ Integración con Moodle
✅ Procesamiento de documentos

## Simplificaciones Realizadas

🔹 Manejo de errores esencial (no exhaustivo)
🔹 Clientes HTTP directos (sin capas extra)
🔹 Configuración unificada
🔹 Menos validaciones complejas
🔹 Código más directo y legible
