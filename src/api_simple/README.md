# API Simplificada de Entrenai

Esta es una versión simplificada de la API de Entrenai que funciona de forma independiente sin depender de los clientes complejos de Moodle, N8N, etc.

## Instalación y Ejecución

```bash
# Desde el directorio src/
pip install fastapi uvicorn

# Ejecutar la API
uvicorn api_simple.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints Disponibles

### Información General
- `GET /` - Endpoint raíz
- `GET /health` - Health check
- `GET /docs` - Documentación interactiva (Swagger UI)

### Gestión de Cursos
- `GET /api/v1/courses` - Lista todos los cursos disponibles
- `GET /api/v1/courses/{course_id}` - Obtiene un curso específico

### Setup de IA
- `POST /api/v1/courses/{course_id}/setup-ia` - Configura la IA para un curso

### Gestión de Archivos
- `POST /api/v1/courses/{course_id}/files/refresh` - Procesa archivos nuevos del curso
- `GET /api/v1/courses/{course_id}/files` - Lista archivos indexados del curso

## Ejemplos de Uso

### Listar cursos
```bash
curl http://localhost:8000/api/v1/courses
```

### Configurar IA para un curso
```bash
curl -X POST http://localhost:8000/api/v1/courses/1/setup-ia
```

### Procesar archivos de un curso
```bash
curl -X POST http://localhost:8000/api/v1/courses/1/files/refresh
```

### Listar archivos de un curso
```bash
curl http://localhost:8000/api/v1/courses/1/files
```

## Respuestas de Ejemplo

### GET /api/v1/courses
```json
[
  {
    "id": 1,
    "shortname": "math101",
    "fullname": "Matemáticas Básicas",
    "displayname": "Matemáticas Básicas",
    "summary": "Curso introductorio de matemáticas"
  },
  {
    "id": 2,
    "shortname": "phys201",
    "fullname": "Física Avanzada",
    "displayname": "Física Avanzada",
    "summary": "Conceptos avanzados de física"
  }
]
```

### POST /api/v1/courses/1/setup-ia
```json
{
  "curso_id": 1,
  "estado": "exitoso",
  "mensaje": "Setup completado para curso 1",
  "tabla_vectores": "curso_1_vectores",
  "workflow_url": "http://localhost:5678/webhook/curso-1"
}
```

### GET /api/v1/courses/1/files
```json
[
  {
    "nombre": "capitulo1.pdf",
    "tipo": "pdf",
    "tamaño": 524288,
    "url": "http://moodle.example.com/file.php/course1/capitulo1.pdf",
    "procesado": true
  },
  {
    "nombre": "presentacion.pptx",
    "tipo": "pptx",
    "tamaño": 2097152,
    "url": "http://moodle.example.com/file.php/course1/presentacion.pptx",
    "procesado": false
  }
]
```

## Características

- **Independiente**: No requiere Moodle, N8N, ni base de datos
- **Funcional**: Todos los endpoints responden con datos simulados
- **Documentación**: Swagger UI disponible en `/docs`
- **CORS habilitado**: Permite requests desde cualquier origen
- **Estructura RESTful**: Sigue convenciones de diseño de APIs

## Próximos Pasos

Esta API puede ser extendida para:
1. Conectar con clientes reales de Moodle
2. Integrar con N8N para workflows
3. Conectar con base de datos vectorial
4. Agregar autenticación y autorización
5. Implementar procesamiento real de archivos
