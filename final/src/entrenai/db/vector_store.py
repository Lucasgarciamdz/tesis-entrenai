"""Store de vectores simplificado con pgvector."""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
import asyncpg
from pgvector.asyncpg import register_vector
from ..config import Config


class VectorStore:
    """Store de vectores simplificado usando pgvector."""
    
    def __init__(self, config: Config):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Conecta a la base de datos."""
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.config.database.url)
            
            # Registrar el tipo vector
            async with self.pool.acquire() as conn:
                await register_vector(conn)
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    async def disconnect(self):
        """Desconecta de la base de datos."""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def create_collection(self, name: str, dimensions: int = 1536) -> bool:
        """Crea una colección (tabla) para almacenar vectores."""
        if not self.pool:
            await self.connect()
        
        query = f"""
        CREATE TABLE IF NOT EXISTS {name} (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector({dimensions}),
            metadata JSONB DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query)
                
                # Crear índice HNSW para búsquedas eficientes
                index_query = f"""
                CREATE INDEX IF NOT EXISTS {name}_embedding_idx 
                ON {name} USING hnsw (embedding vector_cosine_ops)
                """
                await conn.execute(index_query)
                
                return True
        except Exception as e:
            print(f"Error creando colección {name}: {e}")
            return False
    
    async def add_documents(
        self,
        collection: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> List[int]:
        """Añade documentos con sus embeddings a una colección."""
        if not self.pool:
            await self.connect()
        
        if not metadata:
            metadata = [{}] * len(documents)
        
        query = f"""
        INSERT INTO {collection} (content, embedding, metadata)
        VALUES ($1, $2, $3)
        RETURNING id
        """
        
        ids = []
        async with self.pool.acquire() as conn:
            for doc, emb, meta in zip(documents, embeddings, metadata):
                result = await conn.fetchrow(query, doc, emb, meta)
                ids.append(result['id'])
        
        return ids
    
    async def similarity_search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Busca documentos similares por embedding."""
        if not self.pool:
            await self.connect()
        
        query = f"""
        SELECT id, content, metadata, 
               1 - (embedding <=> $1) as similarity
        FROM {collection}
        WHERE 1 - (embedding <=> $1) > $2
        ORDER BY embedding <=> $1
        LIMIT $3
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, query_embedding, threshold, limit)
            
            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "similarity": float(row["similarity"])
                }
                for row in rows
            ]
    
    async def delete_collection(self, name: str) -> bool:
        """Elimina una colección."""
        if not self.pool:
            await self.connect()
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {name}")
                return True
        except Exception as e:
            print(f"Error eliminando colección {name}: {e}")
            return False
    
    async def collection_exists(self, name: str) -> bool:
        """Verifica si una colección existe."""
        if not self.pool:
            await self.connect()
        
        query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = $1
        )
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, name)
            return result
    
    async def get_collection_stats(self, name: str) -> Dict[str, Any]:
        """Obtiene estadísticas de una colección."""
        if not self.pool:
            await self.connect()
        
        query = f"""
        SELECT 
            COUNT(*) as total_documents,
            AVG(LENGTH(content)) as avg_content_length
        FROM {name}
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return {
                "total_documents": row["total_documents"],
                "avg_content_length": float(row["avg_content_length"]) if row["avg_content_length"] else 0
            }
