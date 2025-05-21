# Export PgvectorWrapper and its custom error for easier access
from .pgvector_wrapper import PgvectorWrapper, PgvectorWrapperError

__all__ = [
    "PgvectorWrapper",
    "PgvectorWrapperError",
]
