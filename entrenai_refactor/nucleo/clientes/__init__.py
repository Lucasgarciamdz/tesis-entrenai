# Inicialización del submódulo de clientes

# Importar las clases refactorizadas para que estén disponibles
# al importar el paquete 'clientes'.
from .cliente_moodle import ClienteMoodle, ErrorAPIMoodle
from .cliente_n8n import ClienteN8N, ErrorClienteN8N

__all__ = [
    "ClienteMoodle",
    "ErrorAPIMoodle",
    "ClienteN8N",
    "ErrorClienteN8N",
]