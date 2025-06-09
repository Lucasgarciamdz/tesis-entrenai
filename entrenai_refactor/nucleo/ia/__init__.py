# -*- coding: utf-8 -*-
# Paquete: entrenai_refactor.nucleo.ia
# Descripción:
# Inicializa el submódulo 'ia' del núcleo de EntrenAI.
# Este archivo define la interfaz pública del paquete 'ia', especificando
# qué módulos, clases y funciones se exportan cuando se importa este paquete.
# Facilita el acceso a los componentes de inteligencia artificial de la aplicación.

# Importar clases principales de los envoltorios de IA
from .envoltorio_gemini import EnvoltorioGemini, ErrorEnvoltorioGemini
from .envoltorio_ollama import EnvoltorioOllama, ErrorEnvoltorioOllama

# Importar el gestor de embeddings
from .gestor_embeddings import GestorEmbeddings, ErrorGestorEmbeddings

# Importar el proveedor de inteligencia unificado
from .proveedor_inteligencia import ProveedorInteligencia, ErrorProveedorInteligencia

# Importar funciones de utilidad comunes
from .utilidades_comunes_ia import (
    postprocesar_contenido_markdown,
    preprocesar_contenido_texto, # Nombre actualizado para reflejar el cambio en el módulo de utilidades
    guardar_markdown_en_archivo,
    extraer_bloque_markdown_de_respuesta,
    es_contenido_markdown_valido_basico,
)

# Define la interfaz pública del paquete 'ia' mediante la lista __all__.
# Esto afecta a las importaciones con 'from entrenai_refactor.nucleo.ia import *'.
__all__ = [
    # Envoltorios de Proveedores de IA y sus Errores
    "EnvoltorioGemini",
    "ErrorEnvoltorioGemini",
    "EnvoltorioOllama",
    "ErrorEnvoltorioOllama",

    # Gestor de Embeddings y su Error
    "GestorEmbeddings",
    "ErrorGestorEmbeddings",

    # Proveedor de Inteligencia Unificado y su Error
    "ProveedorInteligencia",
    "ErrorProveedorInteligencia",

    # Funciones de Utilidad Comunes para IA
    "postprocesar_contenido_markdown",
    "preprocesar_contenido_texto", # Nombre actualizado
    "guardar_markdown_en_archivo",
    "extraer_bloque_markdown_de_respuesta",
    "es_contenido_markdown_valido_basico",
]