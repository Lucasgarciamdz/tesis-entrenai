# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.api.rutas
# Descripción:
# Este archivo __init__.py inicializa el submódulo 'rutas' del paquete 'api'.
# Su función es importar y opcionalmente re-exportar los enrutadores (APIRouter)
# definidos en los módulos de este paquete, facilitando su inclusión en la aplicación FastAPI principal.

from .ruta_busqueda import enrutador_busqueda
from .ruta_configuracion_curso import enrutador_config_curso
from .ruta_procesamiento_interno import enrutador_procesamiento_interno

# Define la interfaz pública del paquete 'api.rutas'.
# Estos son los nombres que se exportarán con 'from entrenai_refactor.api.rutas import *'.
__all__ = [
    "enrutador_busqueda",                # Enrutador para endpoints de búsqueda.
    "enrutador_config_curso",            # Enrutador para configuración de cursos.
    "enrutador_procesamiento_interno",   # Enrutador para tareas internas/asíncronas.
]

# Logging opcional para confirmar la carga de este paquete.
try:
    from entrenai_refactor.config.registrador import obtener_registrador
    registrador_init_pkg_rutas = obtener_registrador(__name__)
    registrador_init_pkg_rutas.debug(f"Paquete 'api.rutas' (__init__.py) cargado. Enrutadores disponibles: {', '.join(__all__)}.")
except ImportError:
    import logging
    logging.getLogger(__name__).debug(f"Paquete 'api.rutas' (__init__.py) cargado (registrador básico). Enrutadores: {', '.join(__all__)}.")