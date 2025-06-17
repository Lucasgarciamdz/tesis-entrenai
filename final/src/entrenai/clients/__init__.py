"""Clientes simplificados para servicios externos."""

from .moodle import MoodleClient, get_moodle_client
from .n8n import N8NClient, get_n8n_client
from .vector_store import VectorStoreClient, get_vector_store_client

__all__ = [
    "MoodleClient",
    "get_moodle_client", 
    "N8NClient",
    "get_n8n_client",
    "VectorStoreClient", 
    "get_vector_store_client"
]
