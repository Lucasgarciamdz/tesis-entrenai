import re
from pathlib import Path
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

def postprocesar_contenido_markdown(contenido_markdown: str) -> str:
    """
    Realiza una limpieza y formateo final sobre el contenido Markdown generado por un LLM.
    El objetivo es obtener un Markdown más limpio y estándar.

    Args:
        contenido_markdown: El string de Markdown tal como fue retornado por el modelo de lenguaje.

    Returns:
        Un string con el Markdown limpio y mejor formateado.
    """
    if not contenido_markdown or not contenido_markdown.strip():
        registrador.debug("Contenido Markdown de entrada para postprocesar está vacío o solo son espacios.")
        return ""

    registrador.debug(f"Iniciando postprocesamiento de Markdown (longitud original: {len(contenido_markdown)}).")

    # Remover etiquetas XML/SGML comunes que algunos modelos podrían generar por error (ej. <think>, </thinking>)
    # Estas etiquetas a veces son usadas por los modelos para "pensar" antes de generar la respuesta final.
    markdown_limpio = re.sub(r"<think>.*?</think>", "", contenido_markdown, flags=re.DOTALL | re.IGNORECASE)
    markdown_limpio = re.sub(r"<\/?thinking>", "", markdown_limpio, flags=re.IGNORECASE)
    markdown_limpio = re.sub(r"<\/?rationale>", "", markdown_limpio, flags=re.IGNORECASE) # Otra etiqueta común de "razonamiento"
    markdown_limpio = re.sub(r"<\/?scratchpad>", "", markdown_limpio, flags=re.IGNORECASE) # Similar a un "borrador"

    # Intentar eliminar frases introductorias comunes que los LLMs añaden antes del Markdown.
    # Busca la primera línea que parezca contenido Markdown real (ej. un encabezado, una lista, un enlace).
    # Expresión regular para detectar inicios de Markdown comunes:
    # - `#+\s`: Encabezados (ej. # Titulo)
    # - `[\*\-]\s`: Elementos de lista (ej. * item, - item)
    # - `\d+\.\s`: Elementos de lista numerada (ej. 1. item)
    # - `\[.*\]\(.*\)`: Enlaces Markdown (ej. [texto](url))
    # - ```: Bloques de código
    # - `\|.*\|`: Tablas (una línea de tabla)
    # - `(\S.*?\n(={3,}|-{3,})): Encabezados Setext (ej. Titulo\n===)
    patron_inicio_markdown = re.compile(
        r"^(#+\s|[\*\-]\s|\d+\.\s|\[.*\]\(.*\)|```|\|.*\||(\S.*?\n(={3,}|-{3,})))",
        re.MULTILINE
    )
    coincidencia_contenido_valido = patron_inicio_markdown.search(markdown_limpio)

    if coincidencia_contenido_valido:
        # Si se encuentra un patrón de inicio de Markdown, se toma el texto desde ese punto.
        # Esto ayuda a eliminar frases como "Aquí está el Markdown:" o "Claro, aquí tienes:"
        posicion_inicio_real = coincidencia_contenido_valido.start()
        if posicion_inicio_real > 0:
            texto_prefijo_eliminado = markdown_limpio[:posicion_inicio_real].strip()
            # Solo eliminar si el prefijo no es muy largo, para evitar borrar contenido real por error.
            if texto_prefijo_eliminado and len(texto_prefijo_eliminado) < 150:
                 registrador.debug(f"Prefijo eliminado del Markdown: '{texto_prefijo_eliminado}'")
                 markdown_limpio = markdown_limpio[posicion_inicio_real:]
            else:
                registrador.debug(f"No se eliminó ningún prefijo o el prefijo era demasiado largo para ser considerado una introducción espuria (longitud: {len(texto_prefijo_eliminado)}).")
    else:
        registrador.debug("No se detectó un inicio de Markdown estándar con el patrón; se procesará el texto tal cual.")

    # Asegurar espaciado apropiado después de encabezados (ej. "# Encabezado\n\nTexto" en lugar de "# Encabezado\nTexto")
    # Solo añade un salto de línea si no hay ya dos (o más) saltos de línea después del encabezado.
    markdown_limpio = re.sub(r"(#{1,6}[^\n]+?)(\n)(?!\n)", r"\1\n\n", markdown_limpio)

    # Formateo de bloques de código: asegurar saltos de línea antes y después de los delimitadores ```
    # y remover espacios extra alrededor.
    # \s*```: cero o más espacios antes de ```
    # (\w*): captura el lenguaje especificado (opcional)
    # \n?: un salto de línea opcional después de la apertura del bloque
    # (.*?): captura el contenido del bloque (no goloso)
    # \n?```: un salto de línea opcional antes del cierre del bloque
    # \s*: cero o más espacios después de ```
    markdown_limpio = re.sub(r"\s*```(\w*)\n?(.*?)\n?```\s*", r"\n\n```\1\n\2\n```\n\n", markdown_limpio, flags=re.DOTALL)

    # Limpiar múltiples saltos de línea consecutivos, reduciéndolos a un máximo de dos.
    markdown_limpio = re.sub(r"\n{3,}", "\n\n", markdown_limpio)

    markdown_final = markdown_limpio.strip() # Eliminar espacios/saltos de línea al inicio/final del todo.
    registrador.debug(f"Postprocesamiento de Markdown finalizado (longitud final: {len(markdown_final)}).")
    return markdown_final


def preprocesar_contenido_texto(texto_entrada: str) -> str: # Renombrado desde preprocesar_texto_para_llm por claridad de uso general
    """
    Preprocesa contenido de texto para limpieza general antes de su uso,
    sea para LLMs, embeddings, u otras operaciones.
    Realiza limpieza básica como normalización de saltos de línea y eliminación de espacios excesivos.

    Args:
        texto_entrada: Texto crudo a procesar.

    Returns:
        Texto limpio y preparado.
    """
    if not texto_entrada:
        return ""

    registrador.debug(f"Iniciando preprocesamiento de texto (longitud original: {len(texto_entrada)}).")
    # Normalizar saltos de línea (CRLF y CR a LF)
    texto_limpio = texto_entrada.replace("\r\n", "\n").replace("\r", "\n")

    # Reducir múltiples saltos de línea consecutivos a un máximo de dos.
    # Esto ayuda a mantener párrafos separados pero evita espaciado excesivo.
    texto_limpio = re.sub(r"\n\s*\n(\s*\n)*", "\n\n", texto_limpio)

    # Reemplazar múltiples espacios o tabs dentro de una línea por un solo espacio.
    texto_limpio = re.sub(r"[ \t]+", " ", texto_limpio)

    # Opcional: Remover líneas que consistan únicamente en espacios en blanco.
    texto_limpio = re.sub(r"^\s+$", "", texto_limpio, flags=re.MULTILINE)

    texto_final = texto_limpio.strip() # Eliminar espacios en blanco al inicio y final del texto completo.
    registrador.debug(f"Preprocesamiento de texto finalizado (longitud final: {len(texto_final)}).")
    return texto_final


def guardar_markdown_en_archivo(contenido_markdown_a_guardar: str, ruta_completa_archivo: Path) -> bool:
    """
    Guarda un string de contenido Markdown en un archivo especificado.
    Crea directorios padres si no existen.

    Args:
        contenido_markdown_a_guardar: El string de Markdown que se va a guardar.
        ruta_completa_archivo: Objeto Path completo del archivo donde se guardará el Markdown.

    Returns:
        True si el archivo se guardó exitosamente, False en caso contrario.
    """
    if not isinstance(ruta_completa_archivo, Path):
        registrador.error(f"La ruta de guardado debe ser un objeto Path, se recibió {type(ruta_completa_archivo)}.")
        # Considerar lanzar TypeError para errores de tipo.
        return False

    # Es importante que ruta_completa_archivo sea un archivo, no un directorio.
    if ruta_completa_archivo.is_dir():
        registrador.error(f"La ruta de guardado '{ruta_completa_archivo}' es un directorio. Se requiere una ruta a un archivo.")
        return False

    try:
        # Crear directorios padres si no existen.
        ruta_completa_archivo.parent.mkdir(parents=True, exist_ok=True)

        with open(ruta_completa_archivo, "w", encoding="utf-8") as archivo_salida:
            archivo_salida.write(contenido_markdown_a_guardar)

        registrador.info(f"Contenido Markdown guardado exitosamente en: {ruta_completa_archivo}")
        return True
    except IOError as e_io: # Errores específicos de entrada/salida (permisos, disco lleno, etc.)
        registrador.error(f"Error de E/S al guardar Markdown en '{ruta_completa_archivo}': {e_io}")
    except Exception as e_general: # Otros errores inesperados (ej. problemas con mkdir)
        registrador.exception(f"Error inesperado al guardar Markdown en '{ruta_completa_archivo}': {e_general}")
    return False

def extraer_bloque_markdown_de_respuesta(texto_respuesta_llm: str) -> str:
    """
    Intenta extraer el contenido principal de un bloque de código Markdown
    de una respuesta de un LLM.
    Busca bloques delimitados por ```markdown ... ``` o, como fallback, ``` ... ```.

    Args:
        texto_respuesta_llm: El texto completo de la respuesta del LLM.

    Returns:
        El contenido Markdown extraído y limpio (sin los delimitadores ```).
        Si no se encuentran bloques claros, devuelve el texto original (después de un strip)
        asumiendo que la respuesta podría ser Markdown directo sin delimitadores.
    """
    if not texto_respuesta_llm or not texto_respuesta_llm.strip():
        return ""

    registrador.debug("Intentando extraer bloque Markdown de la respuesta del LLM.")
    # Priorizar la búsqueda de bloques ```markdown ... ```
    # re.DOTALL hace que '.' coincida también con saltos de línea.
    # re.IGNORECASE para 'markdown'.
    coincidencia_bloque_markdown_explicito = re.search(r"```markdown\s*(.*?)\s*```", texto_respuesta_llm, re.DOTALL | re.IGNORECASE)
    if coincidencia_bloque_markdown_explicito:
        contenido_extraido = coincidencia_bloque_markdown_explicito.group(1).strip()
        registrador.info(f"Bloque Markdown explícito (```markdown) extraído (longitud: {len(contenido_extraido)}).")
        return contenido_extraido

    # Como fallback, buscar bloques de código genéricos ``` ... ```
    # Esto es útil si el LLM no especifica 'markdown' pero aun así usa los delimitadores.
    coincidencia_bloque_codigo_generico = re.search(r"```\s*(.*?)\s*```", texto_respuesta_llm, re.DOTALL)
    if coincidencia_bloque_codigo_generico:
        contenido_extraido = coincidencia_bloque_codigo_generico.group(1).strip()
        registrador.info(f"Bloque de código genérico (```) extraído (longitud: {len(contenido_extraido)}). Se asume que es Markdown.")
        return contenido_extraido

    registrador.debug("No se encontraron bloques de Markdown delimitados por ```. Se devolverá el texto original limpio, asumiendo que es Markdown directo.")
    # Si no se encuentran bloques delimitados, se devuelve el texto original después de un strip.
    # La función `postprocesar_contenido_markdown` puede ser llamada después para limpiar más a fondo.
    return texto_respuesta_llm.strip()


def es_contenido_markdown_valido_basico(contenido_markdown: str) -> bool:
    """
    Realiza una validación muy básica para determinar si un string parece ser Markdown.
    Esta función no es un validador completo de la sintaxis Markdown, solo busca
    algunos indicadores comunes para una verificación rápida. Es útil para decidir
    si un texto genérico podría ser tratado o procesado como Markdown.

    Args:
        contenido_markdown: El string de contenido a validar.

    Returns:
        True si el contenido tiene algunos indicadores de Markdown, False en caso contrario.
    """
    if not contenido_markdown or not contenido_markdown.strip():
        registrador.debug("Validación de Markdown: Contenido vacío o solo espacios, no se considera Markdown válido.")
        return False

    # Verificar la presencia de algunas estructuras comunes de Markdown.
    # Se considera válido si al menos uno de estos patrones comunes está presente.
    # re.MULTILINE (o ^\s* para inicio de línea) es importante para cabeceras y listas.
    tiene_cabeceras = bool(re.search(r"^\s*#+\s+", contenido_markdown, re.MULTILINE))
    tiene_listas_simples = bool(re.search(r"^\s*[\*\-]\s+|\d+\.\s+", contenido_markdown, re.MULTILINE))
    tiene_enlaces_markdown = bool(re.search(r"\[.*?\]\(.*?\)", contenido_markdown))
    # (\*\*|__): Doble asterisco o doble guion bajo para negrita.
    # (\*|_): Asterisco simple o guion bajo simple para cursiva.
    # (.+?): Cualquier caracter, uno o más veces, de forma no golosa.
    # \1: Referencia al grupo de captura (delimitador de apertura).
    tiene_enfasis_markdown = bool(re.search(r"(\*\*|__|\*|_)(.+?)\1", contenido_markdown))
    tiene_bloques_de_codigo = bool(re.search(r"```", contenido_markdown)) # Delimitadores de bloque de código

    es_valido = tiene_cabeceras or tiene_listas_simples or tiene_enlaces_markdown or tiene_enfasis_markdown or tiene_bloques_de_codigo

    if es_valido:
        registrador.debug("Validación de Markdown: El contenido presenta indicadores básicos de ser Markdown.")
    else:
        registrador.debug("Validación de Markdown: El contenido no presenta indicadores comunes de Markdown.")

    return es_valido
