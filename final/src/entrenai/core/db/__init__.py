# Base de datos simplificada para Entrenai
from .pgvector_wrapper import PgvectorWrapper, PgvectorWrapperError

__all__ = ["PgvectorWrapper", "PgvectorWrapperError"]
