# Inicialización del submódulo de IA de EntrenAI

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
    preprocesar_texto_para_llm,
    guardar_contenido_markdown_en_archivo, # Corregido nombre de función si fue traducido
    extraer_bloque_markdown_de_respuesta,
    es_contenido_markdown_valido_basico, # Corregido nombre de función si fue traducido
)

# Definir qué se exporta cuando se hace 'from .ia import *'
__all__ = [
    # Envoltorios y sus Errores
    "EnvoltorioGemini", # Clase ya estaba en español
    "ErrorEnvoltorioGemini", # Clase ya estaba en español
    "EnvoltorioOllama", # Clase ya estaba en español
    "ErrorEnvoltorioOllama", # Clase ya estaba en español

    # Gestor de Embeddings y su Error
    "GestorEmbeddings", # Clase ya estaba en español
    "ErrorGestorEmbeddings", # Clase ya estaba en español

    # Proveedor de Inteligencia y su Error
    "ProveedorInteligencia", # Clase ya estaba en español
    "ErrorProveedorInteligencia", # Clase ya estaba en español

    # Funciones de Utilidad (asegurar que los nombres coincidan con los exportados por el módulo)
    "postprocesar_contenido_markdown", # Función ya estaba en español
    "preprocesar_texto_para_llm", # Función ya estaba en español
    "guardar_contenido_markdown_en_archivo", # Nombre corregido a lo que se usó en la refactorización
    "extraer_bloque_markdown_de_respuesta", # Función ya estaba en español
    "es_contenido_markdown_valido_basico", # Nombre corregido
]