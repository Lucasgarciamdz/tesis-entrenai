import os
import re
from pathlib import Path

# No se importa el logger aquí, ya que estas son funciones de utilidad pura.
# El logging se manejará en las clases que las utilicen.


def postprocesar_contenido_markdown(markdown: str) -> str:
    """
    Realiza limpieza final en el contenido markdown generado.
    """
    # Remover etiquetas <think> que puedan haber sido generadas
    contenido_limpio = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)

    # Remover texto explicativo del inicio como "I've converted this to markdown..."
    contenido_limpio = re.sub(
        r"^.*?(#|---|```)", r"\1", contenido_limpio, flags=re.DOTALL, count=1
    )

    # Asegurar espaciado apropiado después de encabezados
    contenido_limpio = re.sub(r"(#{1,6}.*?)(\n(?!\n))", r"\1\n\n", contenido_limpio)

    # Asegurar que los bloques de código estén bien formateados con saltos de línea
    contenido_limpio = re.sub(
        r"```(\w*)\n?([^`]+)```", r"```\1\n\2\n```", contenido_limpio
    )

    return contenido_limpio.strip()


def preprocesar_contenido_texto(texto: str) -> str:
    """
    Preprocesa el contenido de texto antes de enviar al LLM.
    """
    # Limpiar caracteres de control y espacios excesivos
    texto_limpio = re.sub(r"\r\n|\r|\n", "\n", texto)
    texto_limpio = re.sub(r"\n\s*\n\s*\n", "\n\n", texto_limpio)
    texto_limpio = re.sub(r"[ \t]+", " ", texto_limpio)

    # Remover líneas de metadata
    texto_limpio = re.sub(r"^\s*#\s*metadata:.*$", "", texto_limpio, flags=re.MULTILINE)

    return texto_limpio.strip()


def guardar_markdown_en_archivo(contenido_markdown: str, ruta_guardado: Path) -> bool:
    """
    Guarda contenido markdown a un archivo.
    """
    try:
        if os.path.isdir(ruta_guardado):
            ruta_guardado = ruta_guardado / "salida.md"

        ruta_guardado.parent.mkdir(parents=True, exist_ok=True)

        with open(ruta_guardado, "w", encoding="utf-8") as f:
            f.write(contenido_markdown)

        # No se usa logger aquí, se asume que la función que llama manejará el logging
        return True

    except Exception:
        # No se usa logger aquí, se asume que la función que llama manejará el logging
        return False


def extraer_contenido_markdown(texto_respuesta: str) -> str:
    """
    Extrae contenido markdown de una respuesta del LLM.
    """
    # Buscar bloques de markdown entre ```markdown y ```
    coincidencia_markdown = re.search(
        r"```markdown\s*\n(.*?)\n```", texto_respuesta, re.DOTALL | re.IGNORECASE
    )

    if coincidencia_markdown:
        return coincidencia_markdown.group(1).strip()

    # Si no hay bloques explícitos, buscar contenido que parezca markdown
    if re.search(r"^#|^\*|^-|\[.*\]\(.*\)|```", texto_respuesta, re.MULTILINE):
        return texto_respuesta.strip()

    return texto_respuesta.strip()


def validar_contenido_markdown(markdown: str) -> bool:
    """
    Valida que el contenido sea markdown válido básico.
    """
    if not markdown or not markdown.strip():
        return False

    # Verificar que tenga al menos alguna estructura de markdown
    tiene_encabezados = bool(re.search(r"^#+\s+", markdown, re.MULTILINE))
    tiene_listas = bool(re.search(r"^[\*\-]\s+", markdown, re.MULTILINE))
    tiene_enlaces = bool(re.search(r"\[.*?\]\(.*?\)", markdown))
    tiene_enfasis = bool(re.search(r"\*.*?\*|_.*?_", markdown))

    return tiene_encabezados or tiene_listas or tiene_enlaces or tiene_enfasis
