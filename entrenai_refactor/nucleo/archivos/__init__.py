# Inicialización del submódulo de archivos de EntrenAI

# Importar la clase principal para la gestión de procesamiento de archivos
from .procesador_archivos import GestorMaestroDeProcesadoresArchivos

# Importar excepciones personalizadas para el manejo de errores
from .procesador_archivos import (
    ErrorProcesamientoArchivo,
    ErrorTipoArchivoNoSoportado,
    ErrorDependenciaFaltante
)

# Definir qué se exporta cuando se hace 'from .archivos import *'
__all__ = [
    "GestorMaestroDeProcesadoresArchivos",
    "ErrorProcesamientoArchivo",
    "ErrorTipoArchivoNoSoportado",
    "ErrorDependenciaFaltante",
]