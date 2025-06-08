from pathlib import Path
from typing import Optional, Dict, List, Any

# --- Importaciones opcionales de bibliotecas de terceros ---
# Estas dependencias deben estar listadas en requirements.txt
try:
    import docx # Para .docx
except ImportError:
    docx = None

try:
    import pytesseract # Para OCR en PDFs
    from pdf2image import convert_from_path # Para convertir PDF a imágenes
except ImportError:
    pytesseract = None
    convert_from_path = None

try:
    from pptx import Presentation # Para .pptx
except ImportError:
    Presentation = None

from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

# --- Definiciones de Excepciones Personalizadas ---

class ErrorProcesamientoArchivo(Exception):
    """Excepción base para errores ocurridos durante el procesamiento de archivos."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorProcesamientoArchivo creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()

class ErrorTipoArchivoNoSoportado(ErrorProcesamientoArchivo):
    """Excepción para cuando se intenta procesar un tipo de archivo no soportado."""
    pass

class ErrorDependenciaFaltante(ErrorProcesamientoArchivo):
    """Excepción para cuando falta una dependencia necesaria para procesar un tipo de archivo."""
    pass

# --- Clase Base para Procesadores de Archivos ---

class ProcesadorArchivoInterfaz: # Renombrado para reflejar que es más una interfaz
    """Clase base abstracta que define la interfaz para los procesadores de archivos específicos."""

    # Lista de extensiones de archivo (en minúsculas, con punto) que este procesador maneja.
    EXTENSIONES_ARCHIVOS_SOPORTADAS: List[str] = []

    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        """
        Método abstracto para extraer contenido textual de un archivo.
        Debe ser implementado obligatoriamente por todas las subclases concretas.
        """
        nombre_clase_actual = self.__class__.__name__
        registrador.error(f"El método 'extraer_texto_de_archivo' no ha sido implementado en la clase '{nombre_clase_actual}'.")
        raise NotImplementedError(
            f"El método 'extraer_texto_de_archivo' debe ser implementado por las subclases de {self.__class__.__bases__[0].__name__}."
        )

    def puede_procesar_extension(self, ruta_del_archivo: Path) -> bool:
        """
        Verifica si este procesador es capaz de manejar la extensión del archivo proporcionado.
        La comparación es insensible a mayúsculas/minúsculas.
        """
        extension_archivo = ruta_del_archivo.suffix.lower()
        puede = extension_archivo in self.EXTENSIONES_ARCHIVOS_SOPORTADAS
        registrador.debug(f"Procesador '{self.__class__.__name__}': ¿Puede procesar '{extension_archivo}'? {'Sí' if puede else 'No'}.")
        return puede

# --- Implementaciones de Procesadores Específicos por Tipo de Archivo ---

class ProcesadorArchivosTextoPlano(ProcesadorArchivoInterfaz):
    """Procesador para archivos de texto plano (ej. .txt)."""
    EXTENSIONES_ARCHIVOS_SOPORTADAS = [".txt", ".text"] # Añadido .text por si acaso

    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        registrador.info(f"Intentando extraer texto del archivo de texto plano: '{ruta_del_archivo}'.")
        # Lista de codificaciones comunes a intentar en orden de probabilidad o preferencia.
        codificaciones_comunes = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]

        for codificacion_actual in codificaciones_comunes:
            try:
                with open(ruta_del_archivo, "r", encoding=codificacion_actual) as archivo:
                    texto_extraido = archivo.read()
                registrador.info(f"Texto extraído de '{ruta_del_archivo}' utilizando la codificación '{codificacion_actual}'.")
                return texto_extraido
            except UnicodeDecodeError:
                registrador.debug(f"Falló la decodificación del archivo '{ruta_del_archivo}' con la codificación '{codificacion_actual}'. Intentando siguiente.")
                continue # Intenta la siguiente codificación
            except IOError as e_io: # Errores de lectura del archivo
                mensaje_error_io = f"Error de I/O al leer el archivo TXT '{ruta_del_archivo}' con codificación '{codificacion_actual}': {e_io}"
                registrador.error(mensaje_error_io)
                raise ErrorProcesamientoArchivo(mensaje_error_io, e_io) from e_io
            except Exception as e_inesperado: # Otros errores
                registrador.warning(f"Error inesperado leyendo '{ruta_del_archivo}' con '{codificacion_actual}': {e_inesperado}. Se intentará con otra codificación si es posible.")
                continue

        mensaje_error_final = f"No se pudo extraer texto del archivo TXT '{ruta_del_archivo}' después de intentar con las codificaciones: {', '.join(codificaciones_comunes)}."
        registrador.error(mensaje_error_final)
        raise ErrorProcesamientoArchivo(mensaje_error_final)


class ProcesadorArchivosMarkdown(ProcesadorArchivoInterfaz):
    """Procesador para archivos Markdown (ej. .md, .markdown)."""
    EXTENSIONES_ARCHIVOS_SOPORTADAS = [".md", ".markdown"]

    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        registrador.info(f"Extrayendo texto del archivo Markdown: '{ruta_del_archivo}'.")
        try:
            with open(ruta_del_archivo, "r", encoding="utf-8") as archivo: # Markdown usualmente es UTF-8
                texto_extraido = archivo.read()
            registrador.info(f"Texto extraído correctamente del archivo Markdown '{ruta_del_archivo}'.")
            return texto_extraido
        except IOError as e_io:
            mensaje_error = f"Error de I/O al leer el archivo Markdown '{ruta_del_archivo}': {e_io}"
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error, e_io) from e_io
        except Exception as e_inesperado:
            mensaje_error = f"Error inesperado al extraer texto del archivo Markdown '{ruta_del_archivo}': {e_inesperado}"
            registrador.exception(mensaje_error) # Usar exception para incluir traceback
            raise ErrorProcesamientoArchivo(mensaje_error, e_inesperado) from e_inesperado


class ProcesadorArchivosPDF(ProcesadorArchivoInterfaz):
    """Procesador para archivos PDF. Utiliza OCR (Tesseract) si el texto no es extraíble directamente."""
    EXTENSIONES_ARCHIVOS_SOPORTADAS = [".pdf"]

    def __init__(self, lenguaje_ocr: str = "spa+eng"): # Español e Inglés por defecto para OCR
        if pytesseract is None or convert_from_path is None:
            mensaje_error_dependencia = "Las dependencias 'pytesseract' y/o 'pdf2image' no están instaladas. El procesamiento de PDF no estará disponible."
            registrador.error(mensaje_error_dependencia)
            # No lanzar error aquí permite que la app inicie, pero extraer_texto fallará.
            # Se podría lanzar ErrorDependenciaFaltante si se prefiere un fallo temprano.
        self.lenguaje_ocr = lenguaje_ocr
        registrador.debug(f"ProcesadorArchivosPDF inicializado con lenguaje OCR: '{lenguaje_ocr}'.")


    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        if pytesseract is None or convert_from_path is None:
            # Esta comprobación se repite por si el __init__ no lanzó error.
            mensaje_error_dep = "Faltan dependencias ('pytesseract' o 'pdf2image') para procesar archivos PDF."
            registrador.error(mensaje_error_dep)
            raise ErrorDependenciaFaltante(mensaje_error_dep)

        registrador.info(f"Iniciando extracción de texto del PDF: '{ruta_del_archivo}' usando OCR.")
        fragmentos_texto_extraido: List[str] = []
        try:
            # Convertir páginas del PDF a imágenes
            registrador.debug(f"Convirtiendo PDF '{ruta_del_archivo}' a imágenes...")
            lista_imagenes_pagina = convert_from_path(ruta_del_archivo, timeout=60) # Timeout para conversión

            if not lista_imagenes_pagina:
                registrador.warning(f"No se pudieron convertir páginas a imágenes desde el PDF '{ruta_del_archivo}'. El PDF podría estar vacío, corrupto o protegido.")
                return "" # Devolver string vacío si no hay imágenes

            registrador.info(f"PDF convertido a {len(lista_imagenes_pagina)} imágenes. Procediendo con OCR...")
            for i, imagen_pagina_actual in enumerate(lista_imagenes_pagina):
                try:
                    registrador.debug(f"Procesando OCR para página {i + 1} de '{ruta_del_archivo}'...")
                    # Extraer texto de la imagen usando Tesseract OCR
                    texto_pagina_actual = pytesseract.image_to_string(imagen_pagina_actual, lang=self.lenguaje_ocr, timeout=30) # Timeout para OCR por página
                    if texto_pagina_actual and texto_pagina_actual.strip():
                        fragmentos_texto_extraido.append(texto_pagina_actual.strip())
                        registrador.debug(f"Texto extraído de página {i + 1} (longitud: {len(texto_pagina_actual.strip())}).")
                    else:
                        registrador.debug(f"No se extrajo texto de la página {i + 1} de '{ruta_del_archivo}' (posiblemente vacía o sin texto detectable).")
                except pytesseract.TesseractError as error_ocr:
                    registrador.warning(f"Error de Tesseract OCR en página {i + 1} de '{ruta_del_archivo}': {error_ocr}. Se omitirá esta página.")
                except Exception as e_procesando_imagen:
                    registrador.warning(f"Error inesperado procesando la imagen de la página {i + 1} de '{ruta_del_archivo}': {e_procesando_imagen}. Se omitirá esta página.")

            if not fragmentos_texto_extraido and lista_imagenes_pagina:
                 registrador.warning(f"No se extrajo texto de ninguna página del PDF '{ruta_del_archivo}' mediante OCR. El PDF podría no contener texto legible o el OCR falló consistentemente.")

            texto_completo_pdf = "\n\n".join(filter(None, fragmentos_texto_extraido)) # Unir fragmentos con doble salto de línea
            registrador.info(f"Extracción de texto de PDF '{ruta_del_archivo}' completada. Páginas procesadas: {len(lista_imagenes_pagina)}, fragmentos con texto: {len(fragmentos_texto_extraido)}.")
            return texto_completo_pdf

        except Exception as e_general_pdf: # Captura errores de convert_from_path o cualquier otro no previsto
            mensaje_error = f"No se pudo extraer texto del PDF '{ruta_del_archivo}' debido a un error general: {e_general_pdf}"
            registrador.exception(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error, e_general_pdf) from e_general_pdf


class ProcesadorArchivosDocx(ProcesadorArchivoInterfaz):
    """Procesador para archivos DOCX (Microsoft Word)."""
    EXTENSIONES_ARCHIVOS_SOPORTADAS = [".docx"]

    def __init__(self):
        if docx is None:
            # Esta comprobación en __init__ podría ser útil si se quiere fallar temprano.
            # mensaje_error_dep = "Dependencia 'python-docx' no instalada. El procesamiento de DOCX no estará disponible."
            # registrador.error(mensaje_error_dep)
            # raise ErrorDependenciaFaltante(mensaje_error_dep)
            pass # Permitir instanciación, fallará en extraer_texto_de_archivo

    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        if docx is None:
            mensaje_error_dep = "La dependencia 'python-docx' no está instalada. No se puede procesar el archivo DOCX."
            registrador.error(mensaje_error_dep)
            raise ErrorDependenciaFaltante(mensaje_error_dep)

        registrador.info(f"Extrayendo texto del archivo DOCX: '{ruta_del_archivo}'.")
        try:
            documento_word = docx.Document(str(ruta_del_archivo)) # python-docx espera un string o un stream

            # Extraer texto de párrafos
            textos_de_parrafos = [parrafo.text.strip() for parrafo in documento_word.paragraphs if parrafo.text and parrafo.text.strip()]

            # Extraer texto de tablas
            textos_de_tablas = []
            for tabla_actual in documento_word.tables:
                for fila_actual in tabla_actual.rows:
                    for celda_actual in fila_actual.cells:
                        if celda_actual.text and celda_actual.text.strip():
                            textos_de_tablas.append(celda_actual.text.strip())

            # Combinar todo el texto extraído
            texto_completo_docx = "\n\n".join(textos_de_parrafos + textos_de_tablas)
            registrador.info(f"Texto extraído correctamente del archivo DOCX '{ruta_del_archivo}'. Longitud: {len(texto_completo_docx)}.")
            return texto_completo_docx
        except Exception as e_docx: # Capturar excepciones específicas de python-docx si se conocen, o genéricas
            mensaje_error = f"No se pudo extraer texto del archivo DOCX '{ruta_del_archivo}': {e_docx}"
            registrador.exception(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error, e_docx) from e_docx


class ProcesadorArchivosPptx(ProcesadorArchivoInterfaz):
    """Procesador para archivos PPTX (Microsoft PowerPoint)."""
    EXTENSIONES_ARCHIVOS_SOPORTADAS = [".pptx"]

    def __init__(self):
        if Presentation is None:
            pass # Permitir instanciación, fallará en extraer_texto_de_archivo


    def extraer_texto_de_archivo(self, ruta_del_archivo: Path) -> str:
        if Presentation is None:
            mensaje_error_dep = "La dependencia 'python-pptx' no está instalada. No se puede procesar el archivo PPTX."
            registrador.error(mensaje_error_dep)
            raise ErrorDependenciaFaltante(mensaje_error_dep)

        registrador.info(f"Extrayendo texto del archivo PPTX: '{ruta_del_archivo}'.")
        try:
            presentacion_powerpoint = Presentation(str(ruta_del_archivo)) # python-pptx espera un string o un stream

            textos_de_diapositivas = []
            for i, diapositiva_actual in enumerate(presentacion_powerpoint.slides):
                texto_formas_en_diapositiva = []
                # Extraer texto de las formas (shapes) en cada diapositiva
                for forma_actual in diapositiva_actual.shapes:
                    if hasattr(forma_actual, "text_frame") and forma_actual.text_frame and forma_actual.text_frame.text:
                        texto_formas_en_diapositiva.append(forma_actual.text_frame.text.strip())
                    elif hasattr(forma_actual, "text") and forma_actual.text: # Algunas formas simples tienen .text directamente
                        texto_formas_en_diapositiva.append(forma_actual.text.strip())

                # Extraer texto de las notas de la diapositiva, si existen
                if diapositiva_actual.has_notes_slide and \
                   diapositiva_actual.notes_slide.notes_text_frame and \
                   diapositiva_actual.notes_slide.notes_text_frame.text:
                    notas_diapositiva = diapositiva_actual.notes_slide.notes_text_frame.text.strip()
                    if notas_diapositiva:
                        texto_formas_en_diapositiva.append(f"\n[Notas de Diapositiva {i + 1}]:\n{notas_diapositiva}")

                texto_consolidado_diapositiva = "\n".join(filter(None, texto_formas_en_diapositiva))
                if texto_consolidado_diapositiva:
                    textos_de_diapositivas.append(f"[Contenido Diapositiva {i + 1}]:\n{texto_consolidado_diapositiva}")

            texto_completo_pptx = "\n\n".join(filter(None, textos_de_diapositivas))
            registrador.info(f"Texto extraído correctamente del archivo PPTX '{ruta_del_archivo}'. Longitud: {len(texto_completo_pptx)}.")
            return texto_completo_pptx
        except Exception as e_pptx: # Capturar excepciones específicas de python-pptx si se conocen
            mensaje_error = f"No se pudo extraer texto del archivo PPTX '{ruta_del_archivo}': {e_pptx}"
            registrador.exception(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error, e_pptx) from e_pptx

# --- Gestor Principal de Procesadores de Archivos ---

class GestorMaestroDeProcesadoresArchivos:
    """
    Clase central que gestiona una colección de procesadores de archivos
    y delega la tarea de procesamiento al procesador adecuado según la extensión del archivo.
    """
    def __init__(self):
        self.mapeo_procesadores_por_extension: Dict[str, ProcesadorArchivoInterfaz] = {}
        self._registrar_procesadores_disponibles_por_defecto()
        registrador.info("GestorMaestroDeProcesadoresArchivos inicializado con procesadores por defecto.")

    def _registrar_procesadores_disponibles_por_defecto(self):
        """Registra instancias de los procesadores de archivo por defecto que están disponibles (dependencias cumplidas)."""
        self.intentar_registrar_procesador(ProcesadorArchivosTextoPlano())
        self.intentar_registrar_procesador(ProcesadorArchivosMarkdown())

        if pytesseract and convert_from_path:
            self.intentar_registrar_procesador(ProcesadorArchivosPDF())
        else:
            registrador.warning("Procesador de PDF no será registrado debido a que faltan las dependencias 'pytesseract' o 'pdf2image'.")

        if docx:
            self.intentar_registrar_procesador(ProcesadorArchivosDocx())
        else:
            registrador.warning("Procesador de DOCX no será registrado porque falta la dependencia 'python-docx'.")

        if Presentation: # Clase Presentation de python-pptx
            self.intentar_registrar_procesador(ProcesadorArchivosPptx())
        else:
            registrador.warning("Procesador de PPTX no será registrado porque falta la dependencia 'python-pptx'.")

    def intentar_registrar_procesador(self, procesador_a_registrar: ProcesadorArchivoInterfaz):
        """
        Registra un procesador de archivos para cada una de las extensiones que soporta.
        Si una extensión ya tiene un procesador registrado, será sobrescrito.
        """
        if not isinstance(procesador_a_registrar, ProcesadorArchivoInterfaz):
            registrador.error(f"Intento de registrar un objeto que no es instancia de ProcesadorArchivoInterfaz: {type(procesador_a_registrar)}")
            return

        for extension_soportada in procesador_a_registrar.EXTENSIONES_ARCHIVOS_SOPORTADAS:
            extension_normalizada = extension_soportada.lower()
            self.mapeo_procesadores_por_extension[extension_normalizada] = procesador_a_registrar
            registrador.info(f"Procesador para extensión '{extension_normalizada}' registrado: {type(procesador_a_registrar).__name__}")

    def procesar_archivo_segun_tipo(self, ruta_del_archivo_a_procesar: Path) -> Optional[str]:
        """
        Procesa un archivo utilizando el procesador adecuado según su extensión.

        Args:
            ruta_del_archivo_a_procesar: Objeto Path que apunta al archivo a procesar.

        Returns:
            El texto extraído como un string, o None si el archivo no existe,
            no hay un procesador registrado para su extensión, o si ocurre un error
            durante el procesamiento.
        """
        if not isinstance(ruta_del_archivo_a_procesar, Path):
            try:
                # Intentar convertir a Path si es un string
                ruta_del_archivo_a_procesar = Path(ruta_del_archivo_a_procesar)
            except TypeError:
                registrador.error(f"La ruta del archivo proporcionada es inválida: '{ruta_del_archivo_a_procesar}' (tipo: {type(ruta_del_archivo_a_procesar)}).")
                return None

        registrador.info(f"Solicitud para procesar archivo: '{ruta_del_archivo_a_procesar}'.")
        if not ruta_del_archivo_a_procesar.is_file():
            registrador.error(f"El archivo especificado '{ruta_del_archivo_a_procesar}' no existe o no es un archivo.")
            return None

        extension_archivo_actual = ruta_del_archivo_a_procesar.suffix.lower()
        procesador_seleccionado = self.mapeo_procesadores_por_extension.get(extension_archivo_actual)

        if procesador_seleccionado:
            registrador.info(f"Procesando archivo '{ruta_del_archivo_a_procesar}' con el procesador: {type(procesador_seleccionado).__name__}.")
            try:
                texto_extraido = procesador_seleccionado.extraer_texto_de_archivo(ruta_del_archivo_a_procesar)
                registrador.info(f"Procesamiento de '{ruta_del_archivo_a_procesar}' finalizado. Longitud del texto extraído: {len(texto_extraido) if texto_extraido else 0}.")
                return texto_extraido
            except ErrorDependenciaFaltante as e_dep: # Capturar error de dependencia específica
                registrador.error(f"Error de dependencia al procesar '{ruta_del_archivo_a_procesar}' con {type(procesador_seleccionado).__name__}: {e_dep}")
                # No relanzar, simplemente devolver None para indicar fallo de procesamiento.
                return None
            except ErrorProcesamientoArchivo as e_proc: # Otros errores de procesamiento definidos
                registrador.error(f"Error específico de procesamiento al procesar '{ruta_del_archivo_a_procesar}' con {type(procesador_seleccionado).__name__}: {e_proc}")
                return None
            except Exception as e_inesperado: # Errores completamente inesperados
                 registrador.exception(f"Error inesperado y no capturado durante el procesamiento de '{ruta_del_archivo_a_procesar}' con {type(procesador_seleccionado).__name__}: {e_inesperado}")
                 return None # Devolver None para indicar fallo
        else:
            mensaje_no_soporte = f"No se encontró un procesador adecuado para la extensión '{extension_archivo_actual}' del archivo '{ruta_del_archivo_a_procesar}'."
            registrador.warning(mensaje_no_soporte)
            # Considerar si se debe lanzar ErrorTipoArchivoNoSoportado aquí o simplemente devolver None.
            # Devolver None es más suave para el flujo general si se esperan archivos no soportados.
            # Si se espera que todos los archivos sean soportados, lanzar una excepción sería mejor.
            # Por ahora, se devuelve None.
            return None
[end of entrenai_refactor/nucleo/archivos/procesador_archivos_refactorizado.py]
