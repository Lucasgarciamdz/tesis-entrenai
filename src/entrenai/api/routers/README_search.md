# Endpoint de Búsqueda de Contexto

Este módulo proporciona un endpoint para buscar contexto relevante en la base de datos vectorial Qdrant.

## Endpoint `/api/v1/search`

El endpoint `POST /api/v1/search` permite buscar contexto relevante para una consulta de texto en la base de datos vectorial Qdrant.

### Cuerpo de la solicitud

```json
{
  "query": "¿Cuál es el tema principal del curso?",
  "course_name": "nombre_del_curso",
  "limit": 5,
  "threshold": 0.7
}
```

Donde:
- `query`: La consulta de texto para buscar contexto.
- `course_name`: El nombre del curso donde buscar. Este valor se usa para construir el nombre de la colección en Qdrant.
- `limit`: (Opcional) Número máximo de resultados a devolver. Por defecto: 5.
- `threshold`: (Opcional) Umbral mínimo de similitud (0-1). Por defecto: 0.7.

### Respuesta

```json
{
  "results": [
    {
      "id": "12345-67890-abcde",
      "score": 0.9234,
      "text": "El tema principal del curso es la inteligencia artificial aplicada a la educación...",
      "metadata": {
        "course_id": 123,
        "document_id": "doc_456",
        "document_title": "Programa del Curso",
        "source_filename": "programa.pdf"
      }
    },
    // ... más resultados
  ],
  "total": 5,
  "query": "¿Cuál es el tema principal del curso?"
}
```

Donde:
- `results`: Lista de resultados de la búsqueda.
  - `id`: ID único del chunk en Qdrant.
  - `score`: Puntuación de similitud (0-1).
  - `text`: Texto del chunk encontrado.
  - `metadata`: Metadatos adicionales del chunk.
- `total`: Número total de resultados encontrados.
- `query`: La consulta original.

## Ejemplo de uso con cURL

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
     -H "Content-Type: application/json" \
     -d '{
           "query": "¿Cuál es el tema principal del curso?",
           "course_name": "nombre_del_curso",
           "limit": 5,
           "threshold": 0.7
         }'
```

## Ejemplo de uso con Python

Ver el archivo `src/entrenai/examples/search_qdrant.py` para un ejemplo completo de cómo usar este endpoint desde Python.

```python
import requests

def search_context(query, course_name, limit=5, threshold=0.7):
    api_url = "http://localhost:8000/api/v1/search"
    
    data = {
        "query": query,
        "course_name": course_name,
        "limit": limit,
        "threshold": threshold
    }
    
    response = requests.post(api_url, json=data)
    response.raise_for_status()
    
    return response.json()

# Ejemplo de uso
results = search_context(
    query="¿Cuál es el tema principal del curso?",
    course_name="nombre_del_curso"
)
```

## Flujo interno

1. El endpoint recibe una consulta de texto y el nombre del curso.
2. Genera un embedding para la consulta utilizando el modelo de embedding configurado.
3. Busca en la colección de Qdrant correspondiente al curso los chunks más similares.
4. Devuelve los resultados formateados con el texto y metadatos asociados.

## Consideraciones

- El servicio debe tener acceso a Qdrant y al servicio de embeddings (Ollama o Gemini).
- El curso debe existir en la base de datos de Qdrant y tener documentos indexados.
- La calidad de los resultados depende de la calidad de los embeddings y de los documentos indexados. 