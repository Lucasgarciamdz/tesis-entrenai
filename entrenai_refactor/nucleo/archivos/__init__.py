# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.nucleo.archivos
# Descripción:
# Este archivo __init__.py inicializa el submódulo 'archivos' del paquete 'nucleo'.
# Su propósito es facilitar la importación de las clases y excepciones principales
# relacionadas con el procesamiento y gestión de archivos dentro de la aplicación EntrenAI.

# Importar la clase principal para la gestión del procesamiento de archivos.
# GestorMaestroDeProcesadoresArchivos centraliza la lógica para delegar
# el procesamiento de archivos al procesador específico según el tipo de archivo.
from .procesador_archivos import GestorMaestroDeProcesadoresArchivos

# Importar excepciones personalizadas definidas en 'procesador_archivos.py'.
# Estas excepciones permiten un manejo de errores más granular y específico
# para problemas encontrados durante el procesamiento de archivos.
from .procesador_archivos import (
    ErrorProcesamientoArchivo,      # Excepción base para errores generales de procesamiento.
    ErrorTipoArchivoNoSoportado,  # Lanzada cuando no hay un procesador para un tipo de archivo.
    ErrorDependenciaFaltante,     # Lanzada si falta una biblioteca externa necesaria.
)

# La lista __all__ define la interfaz pública de este paquete.
# Especifica qué nombres se importarán cuando se use 'from .archivos import *'.
__all__ = [
    "GestorMaestroDeProcesadoresArchivos",
    "ErrorProcesamientoArchivo",
    "ErrorTipoArchivoNoSoportado",
    "ErrorDependenciaFaltante",
]