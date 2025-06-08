import logging
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional
from entrenai_refactor.config.configuracion import config

class ErrorBaseVectorial(Exception):
    pass

class BaseVectorial:
    def __init__(self):
        self.logger = logging.getLogger("base_vectorial")
        self.conexion = None
        self.cursor = None
        self._conectar()

    def _conectar(self):
        try:
            self.conexion = psycopg2.connect(config.pgvector_url)
            self.cursor = self.conexion.cursor(cursor_factory=RealDictCursor)
            register_vector(self.conexion)
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conexion.commit()
            self.logger.info(f"BaseVectorial conectada a {config.pgvector_url}")
        except Exception as e:
            self.logger.error(f"Error al conectar a la base de datos vectorial: {e}")
            self.conexion = None
            self.cursor = None
            raise ErrorBaseVectorial(str(e))

    def obtener_archivos_procesados(self, id_curso: int) -> Dict[str, int]:
        self._conectar()
        if not self.conexion or not self.cursor:
            self.logger.error("No hay conexión a la base de datos.")
            return {}
        try:
            self.cursor.execute("SELECT file_identifier, moodle_timemodified FROM file_tracker WHERE course_id = %s;", (id_curso,))
            resultados = self.cursor.fetchall()
            return {row["file_identifier"]: row["moodle_timemodified"] for row in resultados}
        except Exception as e:
            self.logger.error(f"Error al obtener archivos procesados: {e}")
            return {}

    def conectar(self):
        self.logger.info("Conectando a la base de datos vectorial (pgvector)")
        return True 