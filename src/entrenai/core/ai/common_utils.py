import os
import re
from pathlib import Path

from src.entrenai.config.logger import get_logger

logger = get_logger(__name__)


def postprocess_markdown_content(markdown: str) -> str:
    """
    Realiza limpieza final en el contenido markdown generado.

    Args:
        markdown: El contenido markdown retornado por el LLM

    Returns:
        Markdown limpio y bien formateado.
    """
    # Validar que markdown sea un string válido
    if not isinstance(markdown, str):
        logger.warning(f"postprocess_markdown_content recibió un valor no-string: {type(markdown)}")
        return ""
    
    if not markdown.strip():
        logger.warning("postprocess_markdown_content recibió un string vacío")
        return ""
    
    # Remover etiquetas <think> que puedan haber sido generadas
    cleaned_markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)

    # Remover texto explicativo del inicio como "I've converted this to markdown..."
    cleaned_markdown = re.sub(
        r"^.*?(#|---|```)", r"\1", cleaned_markdown, flags=re.DOTALL, count=1
    )

    # Corregir problemas de formato comunes
    # Asegurar espaciado apropiado después de encabezados
    cleaned_markdown = re.sub(r"(#{1,6}.*?)(\n(?!\n))", r"\1\n\n", cleaned_markdown)

    # Asegurar que los bloques de código estén bien formateados con saltos de línea
    cleaned_markdown = re.sub(
        r"```(\w*)\n?([^`]+)```", r"```\1\n\2\n```", cleaned_markdown
    )

    return cleaned_markdown.strip()


def preprocess_text_content(text: str) -> str:
    """
    Preprocesa el contenido de texto antes de enviar al LLM.

    Args:
        text: Texto crudo a procesar

    Returns:
        Texto limpio y preparado para el LLM.
    """
    # Limpiar caracteres de control y espacios excesivos
    cleaned_text = re.sub(r"\r\n|\r|\n", "\n", text)
    cleaned_text = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_text)
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)

    # Remover líneas de metadata
    cleaned_text = re.sub(r"^\s*#\s*metadata:.*$", "", cleaned_text, flags=re.MULTILINE)

    return cleaned_text.strip()


def save_markdown_to_file(markdown_content: str, save_path: Path) -> bool:
    """
    Guarda contenido markdown a un archivo.

    Args:
        markdown_content: Contenido markdown a guardar
        save_path: Ruta donde guardar el archivo

    Returns:
        True si se guardó exitosamente, False en caso contrario.
    """
    try:
        # Crear directorio si no existe
        if os.path.isdir(save_path):
            save_path = save_path / "output.md"

        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Escribir contenido al archivo
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Markdown guardado exitosamente en: {save_path}")
        return True

    except Exception as e:
        logger.error(f"Error al guardar markdown en {save_path}: {e}")
        return False


def extract_markdown_content(response_text: str) -> str:
    """
    Extrae contenido markdown de una respuesta del LLM.

    Args:
        response_text: Texto de respuesta del LLM

    Returns:
        Contenido markdown extraído y limpio.
    """
    # Buscar bloques de markdown entre ```markdown y ```
    markdown_match = re.search(
        r"```markdown\s*\n(.*?)\n```", response_text, re.DOTALL | re.IGNORECASE
    )

    if markdown_match:
        return markdown_match.group(1).strip()

    # Si no hay bloques explícitos, buscar contenido que parezca markdown
    # (empieza con # o contiene elementos markdown)
    if re.search(r"^#|^\*|^-|\[.*\]\(.*\)|```", response_text, re.MULTILINE):
        return response_text.strip()

    # Como último recurso, retornar el texto completo
    return response_text.strip()


def validate_markdown_content(markdown: str) -> bool:
    """
    Valida que el contenido sea markdown válido básico.

    Args:
        markdown: Contenido markdown a validar

    Returns:
        True si es markdown válido básico, False en caso contrario.
    """
    if not markdown or not markdown.strip():
        return False

    # Verificar que tenga al menos alguna estructura de markdown
    has_headers = bool(re.search(r"^#+\s+", markdown, re.MULTILINE))
    has_lists = bool(re.search(r"^[\*\-]\s+", markdown, re.MULTILINE))
    has_links = bool(re.search(r"\[.*?\]\(.*?\)", markdown))
    has_emphasis = bool(re.search(r"\*.*?\*|_.*?_", markdown))

    return has_headers or has_lists or has_links or has_emphasis
