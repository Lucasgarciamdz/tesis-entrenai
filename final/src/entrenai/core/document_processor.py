"""Procesador simplificado de documentos."""

import re
from typing import List, Dict, Any
from pathlib import Path
from ..config import Config
from ..ai.providers import get_ai_provider
from ..db.vector_store import VectorStore


class DocumentProcessor:
    """Procesador simplificado de documentos."""
    
    def __init__(self, config: Config):
        self.config = config
        self.ai_provider = get_ai_provider(config.ai)
        self.vector_store = VectorStore(config)
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Divide un texto en chunks con superposición."""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Intentar cortar en un punto natural (punto, salto de línea)
            if end < len(text):
                # Buscar el último punto o salto de línea en el chunk
                last_period = text.rfind('.', start, end)
                last_newline = text.rfind('\n', start, end)
                
                natural_break = max(last_period, last_newline)
                if natural_break > start + chunk_size // 2:
                    end = natural_break + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
        
        return chunks
    
    def extract_text_from_file(self, file_path: Path) -> str:
        """Extrae texto de un archivo."""
        try:
            if file_path.suffix.lower() == '.txt':
                return file_path.read_text(encoding='utf-8')
            elif file_path.suffix.lower() == '.md':
                content = file_path.read_text(encoding='utf-8')
                # Limpiar markdown básico
                content = re.sub(r'#+\s+', '', content)  # Headers
                content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # Bold
                content = re.sub(r'\*(.*?)\*', r'\1', content)  # Italic
                return content
            else:
                # Para otros tipos de archivo, devolver nombre del archivo
                return f"Archivo: {file_path.name}"
        except Exception as e:
            return f"Error leyendo archivo {file_path.name}: {str(e)}"
    
    async def process_and_store_documents(
        self,
        course_id: int,
        file_paths: List[Path],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Procesa archivos y los almacena en el vector store."""
        
        if not metadata:
            metadata = {}
        
        vector_table = f"curso_{course_id}_vectores"
        
        # Verificar que la tabla existe
        if not await self.vector_store.collection_exists(vector_table):
            await self.vector_store.create_collection(vector_table)
        
        all_chunks = []
        all_metadata = []
        
        # Procesar cada archivo
        for file_path in file_paths:
            try:
                # Extraer texto
                text = self.extract_text_from_file(file_path)
                
                # Dividir en chunks
                chunks = self.chunk_text(text)
                
                # Añadir chunks y metadata
                for i, chunk in enumerate(chunks):
                    all_chunks.append(chunk)
                    chunk_metadata = {
                        **metadata,
                        "source_file": str(file_path.name),
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    }
                    all_metadata.append(chunk_metadata)
                    
            except Exception as e:
                print(f"Error procesando archivo {file_path}: {e}")
                continue
        
        if not all_chunks:
            return False
        
        try:
            # Generar embeddings
            embeddings = await self.ai_provider.generate_embeddings(all_chunks)
            
            # Almacenar en vector store
            await self.vector_store.add_documents(
                vector_table,
                all_chunks,
                embeddings,
                all_metadata
            )
            
            return True
            
        except Exception as e:
            print(f"Error almacenando documentos: {e}")
            return False
    
    async def process_text_content(
        self,
        course_id: int,
        content: str,
        source_name: str = "texto",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Procesa contenido de texto directamente."""
        
        if not metadata:
            metadata = {}
        
        vector_table = f"curso_{course_id}_vectores"
        
        # Verificar que la tabla existe
        if not await self.vector_store.collection_exists(vector_table):
            await self.vector_store.create_collection(vector_table)
        
        try:
            # Dividir en chunks
            chunks = self.chunk_text(content)
            
            # Preparar metadata
            all_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    **metadata,
                    "source": source_name,
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
                all_metadata.append(chunk_metadata)
            
            # Generar embeddings
            embeddings = await self.ai_provider.generate_embeddings(chunks)
            
            # Almacenar en vector store
            await self.vector_store.add_documents(
                vector_table,
                chunks,
                embeddings,
                all_metadata
            )
            
            return True
            
        except Exception as e:
            print(f"Error procesando contenido de texto: {e}")
            return False
