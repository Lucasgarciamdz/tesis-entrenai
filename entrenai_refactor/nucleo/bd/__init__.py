# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.nucleo.bd
# Descripción:
# Este archivo __init__.py inicializa el submódulo 'bd' (base de datos)
# del paquete 'nucleo'. Su función es exponer las clases y excepciones
# principales relacionadas con la base de datos vectorial para facilitar su uso
# en otras partes de la aplicación EntrenAI.

# Importar las clases refactorizadas para que estén disponibles
# al importar el paquete 'bd'.
from .envoltorio_pgvector import EnvoltorioPgVector, ErrorBaseDeDatosVectorial

__all__ = [
    "EnvoltorioPgVector",
    "ErrorBaseDeDatosVectorial",
]