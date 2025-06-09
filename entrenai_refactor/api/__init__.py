# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.api
# Descripción:
# Este archivo __init__.py marca el directorio 'api' como un paquete de Python.
# Puede utilizarse para inicializaciones a nivel del paquete 'api' o para definir
# la interfaz pública del paquete si se importan aquí elementos de submódulos.

# Logging opcional para confirmar la carga de este paquete.
try:
    from entrenai_refactor.config.registrador import obtener_registrador
    registrador_init_pkg_api = obtener_registrador(__name__)
    registrador_init_pkg_api.debug(f"Paquete 'api' (__init__.py) cargado.")
except ImportError:
    import logging
    logging.getLogger(__name__).debug(f"Paquete 'api' (__init__.py) cargado (registrador básico).")