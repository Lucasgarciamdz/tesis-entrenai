# Inicialización del submódulo de rutas de la API de EntrenAI

# Importar los enrutadores (APIRouter) definidos en los módulos de este paquete.
# Estos enrutadores contienen los endpoints específicos de la API.

from .ruta_busqueda import enrutador_busqueda
from .ruta_configuracion_curso import enrutador_config_curso
from .ruta_procesamiento_interno import enrutador_procesamiento_interno

# Opcionalmente, se puede definir una lista __all__ para controlar
# lo que se importa con 'from .rutas import *', aunque es más común
# que el módulo principal de la API importe explícitamente cada enrutador.
__all__ = [
    "enrutador_busqueda",
    "enrutador_config_curso",
    "enrutador_procesamiento_interno",
]

# Añadir un log para confirmar que este __init__ se ejecuta.
# Esto requiere que 'registrador' esté definido en este alcance,
# lo cual no es común para __init__.py a menos que se importe.
# Por simplicidad, omitiré el log directo aquí y asumiré que la
# importación exitosa en 'principal.py' es suficiente confirmación.
# import logging
# logging.getLogger(__name__).info("Módulo de rutas API inicializado y enrutadores importados.")