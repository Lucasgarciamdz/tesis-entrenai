import re
import time
from typing import List, Dict, Any, Optional
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor, execute_values
from loguru import logger


class PgvectorWrapperError(Exception):
    """Excepción para errores del wrapper de Pgvector."""
    pass


class DocumentChunk:
    """Modelo básico para chunks de documentos."""
    def __init__(self, content: str, embedding: List[float], metadata: Dict[str, Any] = None):
        self.content = content
        self.embedding = embedding
        self.metadata = metadata or {}


class PgvectorWrapper:
    """Wrapper simplificado para PostgreSQL con pgvector."""
    
    def __init__(self, host: str, port: int, user: str, password: str, db_name: str):
        self.conn = None
        self.cursor = None
        
        try:
            self.conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=db_name,
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            register_vector(self.conn)
            
            # Crear extensión si no existe
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conn.commit()
            
            logger.info(f"PgvectorWrapper conectado a {host}:{port}/{db_name}")
            
        except psycopg2.Error as e:
            logger.error(f"Error conectando a PostgreSQL: {e}")
            raise PgvectorWrapperError(f"Error de conexión: {e}")
    
    def _normalize_table_name(self, name: str) -> str:
        """Normaliza un nombre para usarlo como tabla PostgreSQL."""
        if not name:
            raise ValueError("El nombre no puede estar vacío")
        
        name_processed = re.sub(r'\s+', '_', name.lower())
        name_processed = re.sub(r'[^a-z0-9_]', '', name_processed)
        name_processed = name_processed[:50]  # Limitar longitud
        
        if not name_processed:
            raise ValueError(f"El nombre '{name}' resultó en un nombre de tabla vacío")
        
        return name_processed
    
    def ensure_table(self, table_name: str, vector_dimension: int = 1536) -> bool:
        """Asegura que exista la tabla de vectores."""
        normalized_name = self._normalize_table_name(table_name)
        
        try:
            create_sql = f"""
            CREATE TABLE IF NOT EXISTS {normalized_name} (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({vector_dimension}),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            
            self.cursor.execute(create_sql)
            
            # Crear índice para búsquedas de vectores
            index_sql = f"""
            CREATE INDEX IF NOT EXISTS {normalized_name}_embedding_idx 
            ON {normalized_name} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """
            
            self.cursor.execute(index_sql)
            self.conn.commit()
            
            logger.info(f"Tabla {normalized_name} creada/verificada exitosamente")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Error creando tabla {normalized_name}: {e}")
            self.conn.rollback()
            return False
    
    def upsert_chunks(self, table_name: str, chunks: List[DocumentChunk]) -> bool:
        """Inserta o actualiza chunks en la tabla."""
        normalized_name = self._normalize_table_name(table_name)
        
        if not chunks:
            logger.warning("No hay chunks para insertar")
            return True
        
        try:
            # Preparar datos para inserción
            values = []
            for chunk in chunks:
                values.append((
                    chunk.metadata.get('filename', 'unknown'),
                    chunk.content,
                    chunk.embedding,
                    chunk.metadata
                ))
            
            insert_sql = f"""
            INSERT INTO {normalized_name} (filename, content, embedding, metadata)
            VALUES %s
            ON CONFLICT DO NOTHING
            """
            
            execute_values(
                self.cursor,
                insert_sql,
                values,
                template=None,
                page_size=100
            )
            
            self.conn.commit()
            logger.info(f"Insertados {len(chunks)} chunks en {normalized_name}")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Error insertando chunks en {normalized_name}: {e}")
            self.conn.rollback()
            return False
    
    def search_chunks(self, table_name: str, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Busca chunks similares usando la consulta de embedding."""
        normalized_name = self._normalize_table_name(table_name)
        
        try:
            search_sql = f"""
            SELECT filename, content, metadata, 
                   embedding <=> %s as distance
            FROM {normalized_name}
            ORDER BY embedding <=> %s
            LIMIT %s
            """
            
            self.cursor.execute(search_sql, (query_embedding, query_embedding, limit))
            results = self.cursor.fetchall()
            
            # Convertir a lista de diccionarios
            return [dict(row) for row in results]
            
        except psycopg2.Error as e:
            logger.error(f"Error buscando en {normalized_name}: {e}")
            return []
    
    def is_file_new_or_modified(self, filename: str, file_size: int, file_timestamp: int) -> bool:
        """Verifica si un archivo es nuevo o ha sido modificado."""
        try:
            # Crear tabla de tracking si no existe
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_tracker (
                    filename TEXT PRIMARY KEY,
                    file_size BIGINT,
                    file_timestamp BIGINT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Verificar si el archivo existe y si ha cambiado
            self.cursor.execute("""
                SELECT file_size, file_timestamp 
                FROM file_tracker 
                WHERE filename = %s
            """, (filename,))
            
            result = self.cursor.fetchone()
            
            if not result:
                return True  # Archivo nuevo
            
            # Verificar si cambió el tamaño o timestamp
            stored_size, stored_timestamp = result
            return file_size != stored_size or file_timestamp != stored_timestamp
            
        except psycopg2.Error as e:
            logger.error(f"Error verificando archivo {filename}: {e}")
            return True  # En caso de error, asumir que es nuevo
    
    def mark_file_as_processed(self, filename: str, file_size: int, file_timestamp: int) -> bool:
        """Marca un archivo como procesado."""
        try:
            upsert_sql = """
            INSERT INTO file_tracker (filename, file_size, file_timestamp)
            VALUES (%s, %s, %s)
            ON CONFLICT (filename) DO UPDATE SET
                file_size = EXCLUDED.file_size,
                file_timestamp = EXCLUDED.file_timestamp,
                processed_at = CURRENT_TIMESTAMP
            """
            
            self.cursor.execute(upsert_sql, (filename, file_size, file_timestamp))
            self.conn.commit()
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Error marcando archivo {filename} como procesado: {e}")
            self.conn.rollback()
            return False
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Conexión a PgvectorWrapper cerrada")


def get_pgvector_client() -> PgvectorWrapper:
    """Función dependency para FastAPI."""
    from entrenai.config.settings import settings
    return PgvectorWrapper(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        db_name=settings.postgres_db
    )
