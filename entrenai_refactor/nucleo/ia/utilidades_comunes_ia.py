import os
import re
from pathlib import Path
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

def postprocesar_contenido_markdown(markdown: str) -> str:
    """
    Realiza limpieza final en el contenido markdown generado.

    Args:
        markdown: El contenido markdown retornado por el LLM.

    Returns:
        Markdown limpio y bien formateado.
    """
    # Remover etiquetas <think> o similares que puedan haber sido generadas por algunos modelos
    markdown_limpio = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)
    markdown_limpio = re.sub(r"<\/?thinking>", "", markdown_limpio, flags=re.IGNORECASE)


    # Remover texto explicativo del inicio como "I've converted this to markdown..." o "Aquí está el markdown:"
    # Busca la primera línea que realmente parezca contenido markdown (empieza con #, ---, ```, o es un título)
    match_contenido_real = re.search(r"^(#+\s|\*\s|\-\s|\[.*\]\(.*\)|```|.*?\n={3,}|.*?\n-{3,})", markdown_limpio, flags=re.MULTILINE)
    if match_contenido_real:
        markdown_limpio = markdown_limpio[match_contenido_real.start():]

    # Corregir problemas de formato comunes
    # Asegurar espaciado apropiado después de encabezados
    markdown_limpio = re.sub(r"(#{1,6}[^\n]+?)(\n)(?!\n)", r"\1\n\n", markdown_limpio)

    # Asegurar que los bloques de código estén bien formateados con saltos de línea
    # y que no haya saltos de línea extraños antes o después de los delimitadores ```
    markdown_limpio = re.sub(r"\s*```(\w*)\n?(.*?)\n?```\s*", r"\n```\1\n\2\n```\n", markdown_limpio, flags=re.DOTALL)

    return markdown_limpio.strip()


def preprocesar_contenido_texto(texto: str) -> str:
    """
    Preprocesa el contenido de texto antes de enviarlo al LLM.

    Args:
        texto: Texto crudo a procesar.

    Returns:
        Texto limpio y preparado para el LLM.
    """
    # Limpiar caracteres de control y espacios excesivos
    texto_limpio = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto_limpio = re.sub(r"\n\s*\n\s*\n+", "\n\n", texto_limpio) # Múltiples saltos a solo dos
    texto_limpio = re.sub(r"[ \t]+", " ", texto_limpio) # Múltiples espacios/tabs a uno solo

    # Remover líneas de metadata si se encuentran (ejemplo: # metadata: {"key": "value"})
    texto_limpio = re.sub(r"^\s*#\s*metadata:.*$", "", texto_limpio, flags=re.MULTILINE)

    return texto_limpio.strip()


def guardar_markdown_en_archivo(contenido_markdown: str, ruta_guardado: Path) -> bool:
    """
    Guarda contenido markdown en un archivo.

    Args:
        contenido_markdown: Contenido markdown a guardar.
        ruta_guardado: Ruta donde guardar el archivo. Si es un directorio, se usa 'output.md'.

    Returns:
        True si se guardó exitosamente, False en caso contrario.
    """
    try:
        if ruta_guardado.is_dir():
            ruta_guardado = ruta_guardado / "output.md"

        ruta_guardado.parent.mkdir(parents=True, exist_ok=True)

        with open(ruta_guardado, "w", encoding="utf-8") as f:
            f.write(contenido_markdown)

        registrador.info(f"Markdown guardado exitosamente en: {ruta_guardado}")
        return True
    except Exception as e:
        registrador.error(f"Error al guardar markdown en {ruta_guardado}: {e}")
        return False

def extraer_contenido_markdown(texto_respuesta: str) -> str:
    """
    Extrae contenido markdown de una respuesta del LLM.
    Busca bloques delimitados por ```markdown ... ``` o simplemente ``` ... ```.

    Args:
        texto_respuesta: Texto de respuesta del LLM.

    Returns:
        Contenido markdown extraído y limpio, o el texto original si no se encuentran bloques.
    """
    # Intentar encontrar bloques ```markdown ... ```
    match_markdown_bloque = re.search(r"```markdown\s*(.*?)\s*```", texto_respuesta, re.DOTALL | re.IGNORECASE)
    if match_markdown_bloque:
        return match_markdown_bloque.group(1).strip()

    # Intentar encontrar bloques ``` ... ``` (genéricos)
    match_bloque_codigo = re.search(r"```\s*(.*?)\s*```", texto_respuesta, re.DOTALL)
    if match_bloque_codigo:
        # Esto podría ser código, pero si es la única estructura de bloque, podría ser markdown.
        # Se devuelve tal cual, el postprocesado podría limpiarlo más si es necesario.
        return match_bloque_codigo.group(1).strip()

    # Si no hay bloques explícitos, pero el contenido parece markdown (ej. empieza con '#')
    # Esta heurística es menos fiable y podría llevar a falsos positivos.
    # Considerar si se debe eliminar o hacer más robusta.
    # if re.search(r"^#|^\*|^-|\[.*\]\(.*\)", texto_respuesta.strip(), re.MULTILINE):
    #    return texto_respuesta.strip()

    # Por defecto, si no se encuentran bloques claros, se devuelve el texto original limpio.
    # La función postprocesar_contenido_markdown intentará limpiarlo después.
    return texto_respuesta.strip()


def validar_contenido_markdown(markdown: str) -> bool:
    """
    Valida de forma básica que el contenido sea markdown.
    No es un validador completo, solo busca algunos indicadores comunes.

    Args:
        markdown: Contenido a validar.

    Returns:
        True si parece ser markdown básico, False en caso contrario.
    """
    if not markdown or not markdown.strip():
        return False

    # Verificar algunas estructuras comunes de markdown.
    tiene_cabeceras = bool(re.search(r"^#+\s+", markdown, re.MULTILINE))
    tiene_listas = bool(re.search(r"^[\*\-]\s+|\d+\.\s+", markdown, re.MULTILINE))
    tiene_enlaces = bool(re.search(r"\[.*?\]\(.*?\)", markdown))
    tiene_enfasis = bool(re.search(r"(\*\*|__|\*|_)(.+?)\1", markdown)) # Doble o simple * o _
    tiene_bloques_codigo = bool(re.search(r"```", markdown))

    return tiene_cabeceras or tiene_listas or tiene_enlaces or tiene_enfasis or tiene_bloques_codigo

[end of entrenai_refactor/nucleo/ia/utilidades_comunes_ia.py]
