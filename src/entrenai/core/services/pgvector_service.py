from src.entrenai.config.logger import get_logger
from src.entrenai.core.db import PgvectorWrapper

logger = get_logger(__name__)


class PgvectorService:
    """Servicio para manejo de operaciones de Pgvector."""
    
    def __init__(self, pgvector_wrapper: PgvectorWrapper):
        self.pgvector_db = pgvector_wrapper
    
    def ensure_course_table(self, course_name: str, vector_size: int) -> str:
        """
        Asegura que la tabla de Pgvector exista para el curso.
        Retorna el nombre de la tabla creada.
        """
        table_name = self.pgvector_db.get_table_name(course_name)
        logger.info(f"Asegurando tabla Pgvector '{table_name}' para curso '{course_name}'")
        
        if not self.pgvector_db.ensure_table(course_name, vector_size):
            raise Exception(f"Falló al crear la tabla Pgvector '{table_name}'")
        
        logger.info(f"Tabla Pgvector '{table_name}' lista")
        return table_name
    
    def delete_file_chunks(self, course_name: str, document_id: str) -> bool:
        """Elimina chunks de un archivo específico."""
        return self.pgvector_db.delete_file_chunks(course_name, document_id)
    
    def delete_file_from_tracker(self, course_id: int, file_identifier: str) -> bool:
        """Elimina registro del tracker de archivos."""
        return self.pgvector_db.delete_file_from_tracker(course_id, file_identifier)
    
    def is_file_new_or_modified(self, course_id: int, filename: str, timemodified: int) -> bool:
        """Verifica si un archivo es nuevo o fue modificado."""
        return self.pgvector_db.is_file_new_or_modified(course_id, filename, timemodified)
    
    def get_processed_files_timestamps(self, course_id: int):
        """Obtiene timestamps de archivos procesados."""
        return self.pgvector_db.get_processed_files_timestamps(course_id)
