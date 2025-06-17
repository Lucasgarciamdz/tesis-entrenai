"""Cliente simplificado para el almacén de vectores (PostgreSQL + pgvector)."""

from typing import List, Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from loguru import logger

from ..config.settings import Settings, get_settings


class VectorStoreError(Exception):
    """Error del almacén de vectores."""
    pass


class VectorStoreClient:
    """Cliente simplificado para PostgreSQL con pgvector."""
    
    def __init__(self, settings: Settings):
        self.connection_string = settings.database.connection_string
        self.embedding_dimensions = settings.ai.embedding_dimensions
        self.connection = None
        logger.info("VectorStoreClient inicializado")
    
    def _get_connection(self):
        """Obtiene una conexión a la base de datos."""
        if not self.connection or self.connection.closed:
            try:
                self.connection = psycopg2.connect(
                    self.connection_string,
                    cursor_factory=RealDictCursor
                )
                self.connection.autocommit = True
            except Exception as e:
                raise VectorStoreError(f"Error conectando a la base de datos: {e}")
        return self.connection
    
    def ensure_extension(self) -> bool:
        """Asegura que la extensión pgvector esté instalada."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            return True
        except Exception as e:
            logger.error(f"Error instalando extensión pgvector: {e}")
            return False
    
    def create_collection(self, table_name: str) -> bool:
        """Crea una tabla/colección para almacenar vectores."""
        try:
            # Asegurar que pgvector esté instalado
            if not self.ensure_extension():
                return False
            
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Crear tabla con campos básicos y vector
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    filename VARCHAR(255),
                    file_type VARCHAR(50),
                    chunk_index INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{{}}',
                    embedding vector({self.embedding_dimensions}),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
                cursor.execute(create_table_sql)
                
                # Crear índice para búsqueda de similitud
                index_sql = f"""
                CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx 
                ON {table_name} 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                """
                cursor.execute(index_sql)
                
            logger.info(f"Tabla {table_name} creada exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error creando tabla {table_name}: {e}")
            return False
    
    def collection_exists(self, table_name: str) -> bool:
        """Verifica si una tabla/colección existe."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, (table_name,))
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Error verificando existencia de tabla {table_name}: {e}")
            return False
    
    def insert_documents(self, table_name: str, documents: List[Dict[str, Any]]) -> bool:
        """Inserta documentos con sus embeddings."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                insert_sql = f"""
                INSERT INTO {table_name} (content, filename, file_type, chunk_index, metadata, embedding)
                VALUES (%(content)s, %(filename)s, %(file_type)s, %(chunk_index)s, %(metadata)s, %(embedding)s)
                """
                
                # Preparar datos para inserción
                insert_data = []
                for doc in documents:
                    insert_data.append({
                        'content': doc['content'],
                        'filename': doc.get('filename', ''),
                        'file_type': doc.get('file_type', ''),
                        'chunk_index': doc.get('chunk_index', 0),
                        'metadata': doc.get('metadata', {}),
                        'embedding': doc['embedding']  # Se espera que sea una lista/array
                    })
                
                cursor.executemany(insert_sql, insert_data)
                
            logger.info(f"Insertados {len(documents)} documentos en {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error insertando documentos en {table_name}: {e}")
            return False
    
    def search_similar(self, table_name: str, query_embedding: List[float], limit: int = 5, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Busca documentos similares usando similitud coseno."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                search_sql = f"""
                SELECT 
                    id, content, filename, file_type, chunk_index, metadata,
                    1 - (embedding <=> %s) as similarity
                FROM {table_name}
                WHERE 1 - (embedding <=> %s) > %s
                ORDER BY embedding <=> %s
                LIMIT %s;
                """
                
                cursor.execute(search_sql, (query_embedding, query_embedding, threshold, query_embedding, limit))
                results = cursor.fetchall()
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Error buscando en {table_name}: {e}")
            return []
    
    def get_collection_stats(self, table_name: str) -> Dict[str, Any]:
        """Obtiene estadísticas de una colección."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as document_count,
                        COUNT(DISTINCT filename) as unique_files,
                        AVG(LENGTH(content)) as avg_content_length
                    FROM {table_name};
                """)
                result = cursor.fetchone()
                
                if result:
                    return dict(result)
                return {"document_count": 0, "unique_files": 0, "avg_content_length": 0}
                
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de {table_name}: {e}")
            return {"document_count": 0, "unique_files": 0, "avg_content_length": 0}
    
    def delete_collection(self, table_name: str) -> bool:
        """Elimina una tabla/colección completamente."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
            
            logger.info(f"Tabla {table_name} eliminada exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando tabla {table_name}: {e}")
            return False
    
    def delete_documents_by_filename(self, table_name: str, filename: str) -> bool:
        """Elimina documentos por nombre de archivo."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table_name} WHERE filename = %s;", (filename,))
                affected_rows = cursor.rowcount
            
            logger.info(f"Eliminados {affected_rows} documentos del archivo {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando documentos de {filename}: {e}")
            return False
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        if self.connection and not self.connection.closed:
            self.connection.close()


def get_vector_store_client(settings: Settings = None) -> VectorStoreClient:
    """Dependency para obtener el cliente del almacén de vectores."""
    if settings is None:
        settings = get_settings()
    return VectorStoreClient(settings)
