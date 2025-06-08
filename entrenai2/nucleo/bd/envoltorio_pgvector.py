import re
import time
import json
from typing import List, Dict, Any

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor, execute_values

from entrenai2.api.modelos import FragmentoDocumento
from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador

registrador = obtener_registrador(__name__)


class ErrorEnvoltorioPgvector(Exception):
    """Excepción personalizada para errores del EnvoltorioPgvector."""
    pass


class EnvoltorioPgvector:
    """Envoltorio para interactuar con PostgreSQL y la extensión pgvector."""

    _NOMBRE_TABLA_SEGUIMIENTO = "seguimiento_archivos"

    def __init__(self):
        self._conexion = None
        self._cursor = None

    def _conectar(self):
        """Establece la conexión a la base de datos si no está activa."""
        if self._conexion and not self._conexion.closed:
            return
        try:
            db_config = config.db
            if not all([db_config.host, db_config.puerto, db_config.usuario, db_config.contrasena, db_config.nombre_bd]):
                raise ErrorEnvoltorioPgvector("Faltan detalles de conexión a la base de datos en la configuración.")

            self._conexion = psycopg2.connect(
                host=db_config.host, port=db_config.puerto, user=db_config.usuario,
                password=db_config.contrasena, dbname=db_config.nombre_bd
            )
            self._cursor = self._conexion.cursor(cursor_factory=RealDictCursor)
            register_vector(self._conexion)
            self._cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self._conexion.commit()
            registrador.info(f"Conectado a la base de datos en {db_config.host}:{db_config.puerto}")
        except psycopg2.Error as e:
            registrador.error(f"No se pudo conectar a la base de datos: {e}")
            self._conexion = self._cursor = None
            raise ErrorEnvoltorioPgvector(f"Fallo en la conexión a la base de datos: {e}") from e

    @property
    def cursor(self) -> RealDictCursor:
        """Propiedad que asegura una conexión y un cursor activos."""
        self._conectar()
        if not self._cursor:
            raise ErrorEnvoltorioPgvector("El cursor de la base de datos no está disponible.")
        return self._cursor
    
    def _commit(self):
        """Realiza un commit si la conexión está activa."""
        if self._conexion:
            self._conexion.commit()

    def obtener_nombre_tabla(self, nombre_curso: str) -> str:
        """Genera un nombre de tabla normalizado para un curso."""
        nombre_normalizado = re.sub(r'\s+', '_', nombre_curso.lower())
        nombre_normalizado = re.sub(r'[^a-z0-9_]', '', nombre_normalizado)[:50]
        if not nombre_normalizado:
            raise ValueError("El nombre del curso resultó en un nombre de tabla inválido.")
        return f"{config.db.prefijo_coleccion}{nombre_normalizado}"

    def asegurar_tabla(self, nombre_curso: str, tamano_vector: int):
        """Asegura que exista una tabla para el curso con la dimensión de vector correcta."""
        nombre_tabla = self.obtener_nombre_tabla(nombre_curso)
        self.cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);", (nombre_tabla,))
        resultado = self.cursor.fetchone()
        if resultado and resultado["exists"]:
            return

        self.cursor.execute(f"CREATE TABLE {nombre_tabla} (id TEXT PRIMARY KEY, id_curso INTEGER, id_documento TEXT, texto TEXT, metadata JSONB, embedding vector({tamano_vector}));")
        if tamano_vector <= 2000:
            self.cursor.execute(f"CREATE INDEX ON {nombre_tabla} USING hnsw (embedding vector_cosine_ops);")
        else:
            self.cursor.execute(f"CREATE INDEX ON {nombre_tabla} USING hnsw ((embedding::halfvec({tamano_vector})) halfvec_cosine_ops);")
        self._commit()

    def insertar_o_actualizar_fragmentos(self, nombre_curso: str, fragmentos: List[FragmentoDocumento]):
        """Inserta o actualiza (upsert) fragmentos de documentos en la tabla del curso."""
        if not fragmentos: return
        
        nombre_tabla = self.obtener_nombre_tabla(nombre_curso)
        dimension_vector = len(fragmentos[0].embedding) if fragmentos[0].embedding else config.db.tamano_vector_defecto
        self.asegurar_tabla(nombre_curso, dimension_vector)

        datos = [(f.id, f.id_curso, f.id_documento, f.texto, json.dumps(f.metadata), f.embedding) for f in fragmentos if f.embedding]
        if not datos: return

        sql = f"INSERT INTO {nombre_tabla} (id, id_curso, id_documento, texto, metadata, embedding) VALUES %s ON CONFLICT (id) DO UPDATE SET texto = EXCLUDED.texto, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding;"
        execute_values(self.cursor, sql, datos)
        self._commit()

    def buscar_fragmentos(self, nombre_curso: str, embedding_consulta: List[float], limite: int = 5) -> List[Dict[str, Any]]:
        """Busca fragmentos relevantes por similitud de coseno."""
        nombre_tabla = self.obtener_nombre_tabla(nombre_curso)
        sql = f"SELECT id, texto, metadata, (1 - (embedding <=> %s)) AS score FROM {nombre_tabla} ORDER BY embedding <=> %s LIMIT %s;"
        self.cursor.execute(sql, (embedding_consulta, embedding_consulta, limite))
        resultados = self.cursor.fetchall()
        return [dict(row) for row in resultados] if resultados else []

    def eliminar_fragmentos_archivo(self, nombre_curso: str, id_documento: str):
        """Elimina todos los fragmentos asociados a un documento específico."""
        nombre_tabla = self.obtener_nombre_tabla(nombre_curso)
        self.cursor.execute(f"DELETE FROM {nombre_tabla} WHERE id_documento = %s;", (id_documento,))
        self._commit()

    def asegurar_tabla_seguimiento_archivos(self):
        """Asegura que la tabla de seguimiento de archivos exista."""
        self.cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);", (self._NOMBRE_TABLA_SEGUIMIENTO,))
        resultado = self.cursor.fetchone()
        if resultado and resultado["exists"]: return
        
        self.cursor.execute(f"CREATE TABLE {self._NOMBRE_TABLA_SEGUIMIENTO} (id_curso INTEGER NOT NULL, identificador_archivo TEXT NOT NULL, moodle_timemodified BIGINT NOT NULL, processed_at BIGINT NOT NULL, PRIMARY KEY (id_curso, identificador_archivo));")
        self._commit()

    def obtener_marcas_tiempo_archivos_procesados(self, id_curso: int) -> Dict[str, int]:
        """Obtiene un mapa de archivos procesados y sus marcas de tiempo de modificación."""
        self.cursor.execute(f"SELECT identificador_archivo, moodle_timemodified FROM {self._NOMBRE_TABLA_SEGUIMIENTO} WHERE id_curso = %s;", (id_curso,))
        resultados = self.cursor.fetchall()
        return {row["identificador_archivo"]: row["moodle_timemodified"] for row in resultados} if resultados else {}

    def marcar_archivo_como_procesado(self, id_curso: int, identificador_archivo: str, moodle_timemodified: int):
        """Registra un archivo como procesado en la tabla de seguimiento."""
        sql = f"INSERT INTO {self._NOMBRE_TABLA_SEGUIMIENTO} (id_curso, identificador_archivo, moodle_timemodified, processed_at) VALUES (%s, %s, %s, %s) ON CONFLICT (id_curso, identificador_archivo) DO UPDATE SET moodle_timemodified = EXCLUDED.moodle_timemodified, processed_at = EXCLUDED.processed_at;"
        self.cursor.execute(sql, (id_curso, identificador_archivo, moodle_timemodified, int(time.time())))
        self._commit()

    def eliminar_archivo_de_seguimiento(self, id_curso: int, identificador_archivo: str):
        """Elimina un archivo de la tabla de seguimiento."""
        self.cursor.execute(f"DELETE FROM {self._NOMBRE_TABLA_SEGUIMIENTO} WHERE id_curso = %s AND identificador_archivo = %s;", (id_curso, identificador_archivo))
        self._commit()

    def cerrar_conexion(self):
        """Cierra la conexión a la base de datos."""
        if self._cursor: self._cursor.close()
        if self._conexion: self._conexion.close()
        self._conexion = self._cursor = None
        registrador.info("Conexión a la base de datos cerrada.")

    def __del__(self):
        self.cerrar_conexion()
