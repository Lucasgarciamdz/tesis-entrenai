"""
Ejemplo de cómo usar el endpoint de búsqueda de contexto en Qdrant.

Uso:
    python -m src.entrenai.examples.search_qdrant --query "mi consulta" --course "nombre_curso"
"""

import argparse
import requests
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()


def search_context(query, course_name, limit=5, threshold=0.7):
    """
    Buscar contexto relevante para una consulta en Qdrant.

    Args:
        query (str): La consulta de texto para la búsqueda.
        course_name (str): El nombre del curso donde buscar.
        limit (int, opcional): Número máximo de resultados. Default: 5.
        threshold (float, opcional): Umbral mínimo de similitud (0-1). Default: 0.7.

    Returns:
        dict: La respuesta JSON del servicio.
    """
    # Obtener URL de la API desde las variables de entorno o usar valor por defecto
    host = os.getenv("FASTAPI_HOST", "localhost")
    port = os.getenv("FASTAPI_PORT", "8000")

    api_url = f"http://{host}:{port}/api/v1/search"

    # Preparar los datos de la solicitud
    data = {
        "query": query,
        "course_name": course_name,
        "limit": limit,
        "threshold": threshold,
    }

    # Enviar la solicitud
    try:
        response = requests.post(api_url, json=data)
        response.raise_for_status()  # Verificar si hubo errores HTTP

        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP: {e}")
        print(f"Detalles: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error de solicitud: {e}")
        return None


def main():
    # Configurar el parser de argumentos
    parser = argparse.ArgumentParser(description="Buscar contexto en Qdrant")
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        required=True,
        help="La consulta de texto para buscar",
    )
    parser.add_argument(
        "--course",
        "-c",
        type=str,
        required=True,
        help="El nombre del curso donde buscar",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=5,
        help="Número máximo de resultados (default: 5)",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.7,
        help="Umbral mínimo de similitud (0-1) (default: 0.7)",
    )

    args = parser.parse_args()

    # Realizar la búsqueda
    results = search_context(
        query=args.query,
        course_name=args.course,
        limit=args.limit,
        threshold=args.threshold,
    )

    # Mostrar los resultados
    if results:
        print(f"\nConsulta: {results['query']}")
        print(f"Total de resultados: {results['total']}\n")

        for i, result in enumerate(results["results"], 1):
            print(f"Resultado {i} (Puntuación: {result['score']:.4f}):")
            print(f"ID: {result['id']}")
            print(
                f"Texto: {result['text'][:200]}..."
                if len(result["text"]) > 200
                else f"Texto: {result['text']}"
            )
            print("Metadatos:")
            for key, value in result["metadata"].items():
                print(f"  - {key}: {value}")
            print()
    else:
        print("No se encontraron resultados o hubo un error en la búsqueda.")


if __name__ == "__main__":
    main()
