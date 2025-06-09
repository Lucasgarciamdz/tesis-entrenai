# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.nucleo.clientes
# Descripción:
# Este archivo __init__.py inicializa el submódulo 'clientes' del núcleo de EntrenAI.
# Define la interfaz pública del paquete, facilitando la importación de los
# clientes de servicios externos (Moodle, N8N) y sus excepciones asociadas.

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