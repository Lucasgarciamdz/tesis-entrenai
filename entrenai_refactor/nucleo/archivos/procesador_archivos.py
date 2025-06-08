from pathlib import Path
from typing import Optional, Dict, List, Any

# --- Importaciones opcionales de bibliotecas ---
try:
    import docx
except ImportError:
    docx = None # type: ignore

try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    pytesseract = None # type: ignore
    convert_from_path = None # type: ignore

try:
    from pptx import Presentation
except ImportError:
    Presentation = None # type: ignore

from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

# --- Definición de Excepciones y Clases Base ---

class ErrorProcesamientoArchivo(Exception):
    """Excepción base para errores durante el procesamiento de archivos."""
    pass

class ProcesadorArchivoBase:
    """Clase base para todos los procesadores de archivos específicos."""
    EXTENSIONES_SOPORTADAS: List[str] = []

    def extraer_texto(self, ruta_archivo: Path) -> str:
        """
        Método abstracto para extraer texto de un archivo.
        Debe ser implementado por las subclases.
        """
        raise NotImplementedError("Este método debe ser implementado por las subclases.")

    def puede_procesar(self, ruta_archivo: Path) -> bool:
        """Verifica si este procesador puede manejar la extensión del archivo dado."""
        return ruta_archivo.suffix.lower() in self.EXTENSIONES_SOPORTADAS

# --- Procesadores Específicos ---

class ProcesadorTxt(ProcesadorArchivoBase):
    EXTENSIONES_SOPORTADAS = [".txt"]

    def extraer_texto(self, ruta_archivo: Path) -> str:
        # Intentar con varias codificaciones comunes
        codificaciones_a_intentar = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
        for codificacion in codificaciones_a_intentar:
            try:
                with open(ruta_archivo, "r", encoding=codificacion) as f:
                    texto = f.read()
                registrador.info(f"Texto extraído de '{ruta_archivo}' usando codificación '{codificacion}'.")
                return texto
            except UnicodeDecodeError:
                registrador.debug(f"Falló la decodificación de '{ruta_archivo}' con '{codificacion}'.")
                continue
            except Exception as e:
                registrador.warning(f"Error inesperado leyendo '{ruta_archivo}' con '{codificacion}': {e}")
                continue

        mensaje_error = f"No se pudo extraer texto del archivo TXT '{ruta_archivo}' después de intentar con varias codificaciones."
        registrador.error(mensaje_error)
        raise ErrorProcesamientoArchivo(mensaje_error)

class ProcesadorMarkdown(ProcesadorArchivoBase):
    EXTENSIONES_SOPORTADAS = [".md", ".markdown"]

    def extraer_texto(self, ruta_archivo: Path) -> str:
        try:
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                texto = f.read()
            registrador.info(f"Texto extraído correctamente de '{ruta_archivo}'.")
            return texto
        except Exception as e:
            mensaje_error = f"No se pudo extraer texto del archivo Markdown '{ruta_archivo}': {e}"
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error) from e

class ProcesadorPdf(ProcesadorArchivoBase):
    EXTENSIONES_SOPORTADAS = [".pdf"]

    def extraer_texto(self, ruta_archivo: Path) -> str:
        if pytesseract is None or convert_from_path is None:
            mensaje_error = "Dependencias ('pytesseract' o 'pdf2image') no instaladas. No se puede procesar PDF."
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error)

        partes_texto: List[str] = []
        try:
            imagenes = convert_from_path(ruta_archivo)
            if not imagenes:
                registrador.warning(f"No se pudieron convertir páginas a imágenes desde el PDF '{ruta_archivo}'. El PDF podría estar vacío o corrupto.")
                return ""

            for i, imagen in enumerate(imagenes):
                try:
                    partes_texto.append(pytesseract.image_to_string(imagen, lang="spa+eng"))
                except pytesseract.TesseractError as ocr_error:
                    registrador.warning(f"Error de OCR en página {i+1} de '{ruta_archivo}': {ocr_error}. Se omitirá esta página.")
                except Exception as e_img:
                    registrador.warning(f"Error procesando página {i+1} de '{ruta_archivo}': {e_img}. Se omitirá esta página.")

            if not partes_texto and imagenes:
                 registrador.warning(f"No se extrajo texto de ninguna página del PDF '{ruta_archivo}', podría estar basado en imágenes sin OCR exitoso o ser un PDF escaneado sin capa de texto.")

            texto_completo = "\n\n".join(filter(None, partes_texto))
            registrador.info(f"Texto extraído de '{ruta_archivo}' (páginas procesadas: {len(imagenes)}, fragmentos con texto: {len(partes_texto)}).")
            return texto_completo
        except Exception as e:
            mensaje_error = f"No se pudo extraer texto del PDF '{ruta_archivo}': {e}"
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error) from e

class ProcesadorDocx(ProcesadorArchivoBase):
    EXTENSIONES_SOPORTADAS = [".docx"]

    def extraer_texto(self, ruta_archivo: Path) -> str:
        if docx is None:
            mensaje_error = "Dependencia ('python-docx') no instalada. No se puede procesar DOCX."
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error)

        try:
            documento = docx.Document(str(ruta_archivo))
            texto_parrafos = [parrafo.text for parrafo in documento.paragraphs if parrafo.text]

            texto_tablas = []
            for tabla in documento.tables:
                for fila in tabla.rows:
                    for celda in fila.cells:
                        if celda.text:
                            texto_tablas.append(celda.text.strip())

            texto_completo = "\n\n".join(texto_parrafos + texto_tablas)
            registrador.info(f"Texto extraído correctamente de '{ruta_archivo}'.")
            return texto_completo
        except Exception as e:
            mensaje_error = f"No se pudo extraer texto del archivo DOCX '{ruta_archivo}': {e}"
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error) from e

class ProcesadorPptx(ProcesadorArchivoBase):
    EXTENSIONES_SOPORTADAS = [".pptx"]

    def extraer_texto(self, ruta_archivo: Path) -> str:
        if Presentation is None:
            mensaje_error = "Dependencia ('python-pptx') no instalada. No se puede procesar PPTX."
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error)

        try:
            presentacion = Presentation(str(ruta_archivo))
            texto_diapositivas = []
            for i, diapositiva in enumerate(presentacion.slides):
                texto_formas_diapositiva = []
                for forma in diapositiva.shapes:
                    if hasattr(forma, "text_frame") and forma.text_frame and forma.text_frame.text:
                        texto_formas_diapositiva.append(forma.text_frame.text.strip())
                    elif hasattr(forma, "text") and forma.text:
                        texto_formas_diapositiva.append(forma.text.strip())

                if diapositiva.has_notes_slide and diapositiva.notes_slide.notes_text_frame and diapositiva.notes_slide.notes_text_frame.text:
                    texto_formas_diapositiva.append(f"\n[Notas Diapositiva {i+1}]:\n{diapositiva.notes_slide.notes_text_frame.text.strip()}")

                if texto_formas_diapositiva:
                    texto_diapositivas.append("\n".join(filter(None, texto_formas_diapositiva)))

            texto_completo = "\n\n".join(filter(None, texto_diapositivas))
            registrador.info(f"Texto extraído correctamente de '{ruta_archivo}'.")
            return texto_completo
        except Exception as e:
            mensaje_error = f"No se pudo extraer texto del archivo PPTX '{ruta_archivo}': {e}"
            registrador.error(mensaje_error)
            raise ErrorProcesamientoArchivo(mensaje_error) from e

# --- Gestor de Procesadores ---

class GestorProcesadoresArchivos:
    """Gestiona y delega el procesamiento de archivos a procesadores específicos."""
    def __init__(self):
        self.procesadores: Dict[str, ProcesadorArchivoBase] = {}
        self._registrar_procesadores_por_defecto()

    def _registrar_procesadores_por_defecto(self):
        """Registra los procesadores de archivo por defecto."""
        self.registrar_procesador(ProcesadorTxt())
        self.registrar_procesador(ProcesadorMarkdown())
        if pytesseract and convert_from_path: # Solo registrar si las dependencias están
            self.registrar_procesador(ProcesadorPdf())
        else:
            registrador.warning("Procesador PDF no registrado porque faltan 'pytesseract' o 'pdf2image'.")
        if docx:
            self.registrar_procesador(ProcesadorDocx())
        else:
            registrador.warning("Procesador DOCX no registrado porque falta 'python-docx'.")
        if Presentation:
            self.registrar_procesador(ProcesadorPptx())
        else:
            registrador.warning("Procesador PPTX no registrado porque falta 'python-pptx'.")


    def registrar_procesador(self, procesador: ProcesadorArchivoBase):
        """Registra un nuevo procesador para las extensiones que soporta."""
        for ext in procesador.EXTENSIONES_SOPORTADAS:
            self.procesadores[ext.lower()] = procesador
            registrador.info(f"Procesador para '{ext}' registrado: {type(procesador).__name__}")

    def procesar_archivo(self, ruta_archivo: Path) -> Optional[str]:
        """
        Procesa un archivo utilizando el procesador adecuado según su extensión.

        Args:
            ruta_archivo: Objeto Path al archivo a procesar.

        Returns:
            El texto extraído como string, o None si el archivo no existe,
            no hay procesador para su extensión, o falla el procesamiento.
        """
        if not isinstance(ruta_archivo, Path):
            try:
                ruta_archivo = Path(ruta_archivo)
            except TypeError: # Si ruta_archivo no es compatible con Path (ej. None)
                registrador.error(f"Ruta de archivo inválida proporcionada: {ruta_archivo}")
                return None

        if not ruta_archivo.is_file():
            registrador.warning(f"El archivo '{ruta_archivo}' no existe o no es un archivo.")
            return None

        extension = ruta_archivo.suffix.lower()
        procesador_seleccionado = self.procesadores.get(extension)

        if procesador_seleccionado:
            registrador.info(f"Procesando archivo '{ruta_archivo}' con {type(procesador_seleccionado).__name__}.")
            try:
                return procesador_seleccionado.extraer_texto(ruta_archivo)
            except ErrorProcesamientoArchivo as e:
                registrador.error(f"Error al procesar '{ruta_archivo}': {e}")
                return None
            except Exception as e_inesperado:
                 registrador.error(f"Error inesperado al procesar '{ruta_archivo}' con {type(procesador_seleccionado).__name__}: {e_inesperado}")
                 return None
        else:
            registrador.warning(f"No se encontró un procesador para la extensión '{extension}' del archivo '{ruta_archivo}'.")
            return None
[end of entrenai_refactor/nucleo/archivos/procesador_archivos.py]
