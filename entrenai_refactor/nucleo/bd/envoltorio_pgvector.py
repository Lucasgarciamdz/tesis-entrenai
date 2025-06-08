import re
import time
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor, execute_values
from typing import List, Dict, Any, Optional
import logging # Usar logging directamente o el registrador configurado
import json # Para convertir metadatos a JSON string

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador # Para consistencia
from entrenai_refactor.api import modelos as modelos_api

registrador = obtener_registrador(__name__) # O logging.getLogger(__name__)

class ErrorEnvoltorioPgVector(Exception):
    """Excepción personalizada para errores del EnvoltorioPgVector."""
    pass

class EnvoltorioPgVector:
    """Envoltorio para interactuar con PostgreSQL y la extensión pgvector."""

    _NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS = "seguimiento_archivos_procesados"

    def __init__(self):
        self.config_db = configuracion_global.db
        self._conexion = None
        self._cursor = None
        # La conexión se establecerá de forma perezosa.
        registrador.info("EnvoltorioPgVector inicializado. La conexión se establecerá perezosamente.")

    def _conectar(self):
        """Establece una conexión a la base de datos si no existe una activa."""
        if self._conexion and not self._conexion.closed:
            # Verificar si el cursor también está activo
            if self._cursor and not self._cursor.closed:
                return
            # Si el cursor está cerrado pero la conexión no, recrear cursor
            if not self._cursor or self._cursor.closed:
                try:
                    self._cursor = self._conexion.cursor(cursor_factory=RealDictCursor)
                    registrador.debug("Cursor recreado para conexión existente.")
                    return
                except psycopg2.Error as e:
                    registrador.warning(f"No se pudo recrear el cursor, se intentará reconectar: {e}")
                    # Forzar reconexión completa
                    if self._conexion: self._conexion.close() # Cerrar conexión existente
                    self._conexion = None
                    self._cursor = None


        registrador.debug(f"Intentando conectar a PostgreSQL en {self.config_db.host}:{self.config_db.puerto} DB: {self.config_db.nombre_bd}")
        if not all([self.config_db.host, self.config_db.puerto, self.config_db.usuario, self.config_db.contrasena, self.config_db.nombre_bd]):
            registrador.error("Detalles de conexión a PgVector faltan en la configuración.")
            raise ErrorEnvoltorioPgVector("Detalles de conexión a PgVector faltantes.")
        try:
            self._conexion = psycopg2.connect(
                host=self.config_db.host,
                port=self.config_db.puerto,
                user=self.config_db.usuario,
                password=self.config_db.contrasena,
                dbname=self.config_db.nombre_bd,
            )
            self._cursor = self._conexion.cursor(cursor_factory=RealDictCursor)
            register_vector(self._conexion)
            self._cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self._conexion.commit() # Confirmar CREATE EXTENSION
            registrador.info(f"Conectado a PgVector: {self.config_db.host}:{self.config_db.puerto}/{self.config_db.nombre_bd}")
            self.asegurar_tabla_seguimiento_archivos()
        except psycopg2.Error as e:
            registrador.error(f"Falló la conexión a PostgreSQL/pgvector en {self.config_db.host}:{self.config_db.puerto}: {e}")
            self._conexion = None
            self._cursor = None
            raise ErrorEnvoltorioPgVector(f"Falló la conexión a la base de datos: {e}")
        except Exception as e:
            registrador.error(f"Error inesperado durante conexión a PgVector: {e}")
            self._conexion = None
            self._cursor = None
            raise ErrorEnvoltorioPgVector(f"Error inesperado en conexión: {e}")

    @property
    def cursor(self) -> RealDictCursor:
        """Proporciona un cursor, asegurando que la conexión esté activa."""
        self._conectar() # Esto asegura que _conexion y _cursor estén inicializados si es posible
        if not self._cursor or self._cursor.closed:
             registrador.warning("Cursor cerrado o no disponible. Intentando reconectar/recrear cursor.")
             # Forzar reconexión completa si el cursor está mal, ya que _conectar() al inicio de esta propiedad
             # ya debería haberlo manejado si la conexión estaba bien pero el cursor mal.
             if self._conexion: self._conexion.close()
             self._conexion = None
             self._cursor = None
             self._conectar() # Reintentar conexión completa

        if self._cursor is None or self._cursor.closed:
            raise ErrorEnvoltorioPgVector("Cursor de base de datos no está disponible después de reintentos.")
        return self._cursor


    def _confirmar_cambios(self):
        if self._conexion and not self._conexion.closed:
            self._conexion.commit()
            registrador.debug("Cambios confirmados en la base de datos.")
        else:
            registrador.warning("No hay conexión activa para confirmar cambios.")
            raise ErrorEnvoltorioPgVector("No hay conexión activa para confirmar.")


    def _revertir_cambios(self):
        if self._conexion and not self._conexion.closed:
            self._conexion.rollback()
            registrador.debug("Cambios revertidos en la base de datos.")
        else:
            registrador.warning("No hay conexión activa para revertir cambios.")

    @staticmethod
    def _normalizar_nombre_para_tabla(nombre: str) -> str:
        if not nombre:
            registrador.error("Se intentó normalizar un nombre vacío para la tabla.")
            raise ValueError("El nombre del curso no puede estar vacío para generar nombre de tabla.")
        nombre_min = nombre.lower()
        nombre_proc = re.sub(r"\s+", "_", nombre_min)
        nombre_proc = re.sub(r"[^a-z0-9_]", "", nombre_proc)
        nombre_proc = nombre_proc[:50]
        if not nombre_proc:
            registrador.error(f"Nombre normalizado para '{nombre}' resultó en cadena vacía.")
            raise ValueError(f"Nombre de curso '{nombre}' resultó en nombre de tabla normalizado vacío.")
        return nombre_proc

    def obtener_nombre_tabla_curso(self, nombre_curso_o_id_curso: Any) -> str:
        nombre_base = str(nombre_curso_o_id_curso)
        nombre_normalizado = self._normalizar_nombre_para_tabla(nombre_base)
        # Quitar comillas dobles del prefijo si existen, ya que el nombre_tabla se entrecomillará después
        prefijo_limpio = self.config_db.prefijo_coleccion.replace('"', '')
        return f"{prefijo_limpio}{nombre_normalizado}"


    def asegurar_tabla_curso(self, nombre_curso_o_id_curso: Any, tamano_vector: int) -> bool:
        self._conectar()
        nombre_tabla = self.obtener_nombre_tabla_curso(nombre_curso_o_id_curso)
        try:
            # Usar comillas dobles para el nombre de la tabla por si contiene caracteres especiales o es palabra clave
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);", (nombre_tabla,))
            resultado = self.cursor.fetchone()
            if resultado and resultado["exists"]:
                registrador.info(f"Tabla '{nombre_tabla}' ya existe.")
                return True

            sql_crear_tabla = f"""
            CREATE TABLE "{nombre_tabla}" (
                id_fragmento TEXT PRIMARY KEY,
                id_curso TEXT,
                id_documento TEXT,
                texto TEXT,
                metadatos JSONB,
                embedding vector({tamano_vector})
            );
            """
            self.cursor.execute(sql_crear_tabla)

            if tamano_vector <= 2000:
                sql_crear_indice = f"CREATE INDEX ON \"{nombre_tabla}\" USING hnsw (embedding vector_cosine_ops);"
            else:
                sql_crear_indice = f"CREATE INDEX ON \"{nombre_tabla}\" USING hnsw ((embedding::halfvec({tamano_vector})) halfvec_cosine_ops);"

            self.cursor.execute(sql_crear_indice)
            self._confirmar_cambios()
            registrador.info(f"Tabla '{nombre_tabla}' creada con tamaño de vector {tamano_vector} e índice HNSW.")
            return True
        except Exception as e:
            registrador.error(f"Error asegurando tabla '{nombre_tabla}': {e}")
            self._revertir_cambios()
            return False

    def insertar_actualizar_fragmentos(self, nombre_curso_o_id_curso: Any, fragmentos: List[modelos_api.FragmentoDocumento]) -> bool:
        self._conectar()
        if not fragmentos:
            registrador.info("No hay fragmentos para insertar/actualizar.")
            return True

        nombre_tabla = self.obtener_nombre_tabla_curso(nombre_curso_o_id_curso)
        tamano_vector = self.config_db.tamano_vector_defecto
        for frag in fragmentos:
            if frag.embedding:
                tamano_vector = len(frag.embedding)
                break

        if not self.asegurar_tabla_curso(nombre_curso_o_id_curso, tamano_vector):
            registrador.error(f"Falló la creación/aseguramiento de tabla '{nombre_tabla}' para inserción de fragmentos.")
            return False

        datos_para_insertar = []
        for frag in fragmentos:
            if frag.embedding is None:
                registrador.warning(f"Fragmento ID '{frag.id_fragmento}' (curso: {frag.id_curso}, doc: {frag.id_documento}) no tiene embedding. Omitiendo.")
                continue
            metadatos_json = json.dumps(frag.metadatos) if isinstance(frag.metadatos, dict) else frag.metadatos
            datos_para_insertar.append(
                (frag.id_fragmento, str(frag.id_curso), frag.id_documento, frag.texto, metadatos_json, frag.embedding)
            )

        if not datos_para_insertar:
            registrador.info(f"No hay fragmentos válidos con embeddings para insertar en '{nombre_tabla}'.")
            return True

        try:
            sql_plantilla = f"""
            INSERT INTO "{nombre_tabla}" (id_fragmento, id_curso, id_documento, texto, metadatos, embedding)
            VALUES %s
            ON CONFLICT (id_fragmento) DO UPDATE SET
                id_curso = EXCLUDED.id_curso,
                id_documento = EXCLUDED.id_documento,
                texto = EXCLUDED.texto,
                metadatos = EXCLUDED.metadatos,
                embedding = EXCLUDED.embedding;
            """
            execute_values(self.cursor, sql_plantilla, datos_para_insertar)
            self._confirmar_cambios()
            registrador.info(f"Se insertaron/actualizaron {len(datos_para_insertar)} fragmentos en tabla '{nombre_tabla}'.")
            return True
        except Exception as e:
            registrador.error(f"Error insertando/actualizando fragmentos en tabla '{nombre_tabla}': {e}")
            self._revertir_cambios()
            return False

    def buscar_fragmentos_similares(
        self, nombre_curso_o_id_curso: Any, embedding_consulta: List[float], limite: int = 5, ef_search_valor: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        self._conectar()
        nombre_tabla = self.obtener_nombre_tabla_curso(nombre_curso_o_id_curso)
        try:
            if ef_search_valor is not None:
                self.cursor.execute("SET LOCAL hnsw.ef_search = %s;", (ef_search_valor,))

            tam_vector_consulta = len(embedding_consulta)
            sql_consulta = f"""
            SELECT id_fragmento, id_curso, id_documento, texto, metadatos, (1 - (embedding <=> %s::vector({tam_vector_consulta}))) AS similitud
            FROM "{nombre_tabla}"
            ORDER BY embedding <=> %s::vector({tam_vector_consulta})
            LIMIT %s;
            """

            self.cursor.execute(sql_consulta, (embedding_consulta, embedding_consulta, limite))
            resultados = self.cursor.fetchall()

            resultados_formateados = []
            for fila in resultados:
                metadatos = fila.get("metadatos")
                if isinstance(metadatos, str):
                    try:
                        metadatos = json.loads(metadatos)
                    except json.JSONDecodeError:
                        metadatos = {}
                elif not isinstance(metadatos, dict):
                     metadatos = {}

                resultados_formateados.append({
                    "id_fragmento": fila["id_fragmento"],
                    "similitud": fila["similitud"],
                    "payload": {
                        "id_curso": fila.get("id_curso"),
                        "id_documento": fila.get("id_documento"),
                        "texto": fila.get("texto"),
                        **metadatos,
                    }
                })
            registrador.info(f"Búsqueda en tabla '{nombre_tabla}' encontró {len(resultados_formateados)} resultados.")
            return resultados_formateados
        except Exception as e:
            registrador.error(f"Error buscando en tabla '{nombre_tabla}': {e}")
            return []

    def eliminar_fragmentos_por_id_documento(self, nombre_curso_o_id_curso: Any, id_documento: str) -> bool:
        self._conectar()
        nombre_tabla = self.obtener_nombre_tabla_curso(nombre_curso_o_id_curso)
        try:
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);", (nombre_tabla,))
            if not (resultado := self.cursor.fetchone()) or not resultado["exists"]:
                registrador.warning(f"Tabla '{nombre_tabla}' no existe. No se pueden eliminar fragmentos para doc ID '{id_documento}'.")
                return True

            sql_eliminar = f"DELETE FROM \"{nombre_tabla}\" WHERE id_documento = %s;"
            self.cursor.execute(sql_eliminar, (id_documento,))
            filas_eliminadas = self.cursor.rowcount
            self._confirmar_cambios()
            registrador.info(f"Eliminados {filas_eliminadas} fragmentos para doc ID '{id_documento}' de tabla '{nombre_tabla}'.")
            return True
        except Exception as e:
            registrador.error(f"Error eliminando fragmentos para doc ID '{id_documento}' de tabla '{nombre_tabla}': {e}")
            self._revertir_cambios()
            return False

    def asegurar_tabla_seguimiento_archivos(self):
        if not self._conexion or not self._cursor or self._conexion.closed or self._cursor.closed:
             registrador.error("No hay conexión a BD para asegurar tabla de seguimiento.")
             raise ErrorEnvoltorioPgVector("Conexión no disponible para asegurar tabla de seguimiento.")
        try:
            # Usar comillas dobles para el nombre de la tabla por si acaso
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}');")
            if (resultado := self.cursor.fetchone()) and resultado["exists"]:
                registrador.debug(f"Tabla '{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}' ya existe.")
                return

            sql_crear_tabla = f"""
            CREATE TABLE "{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}" (
                id_curso INTEGER NOT NULL,
                identificador_archivo TEXT NOT NULL,
                tiempo_modificacion_moodle BIGINT NOT NULL,
                procesado_en BIGINT NOT NULL,
                PRIMARY KEY (id_curso, identificador_archivo)
            );
            """
            self.cursor.execute(sql_crear_tabla)
            self._confirmar_cambios()
            registrador.info(f"Tabla '{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}' creada exitosamente.")
        except Exception as e:
            registrador.error(f"Error asegurando tabla '{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}': {e}")
            self._revertir_cambios()

    def obtener_marcas_tiempo_archivos_procesados(self, id_curso: int) -> Dict[str, int]:
        self._conectar()
        try:
            sql_consulta = f"SELECT identificador_archivo, tiempo_modificacion_moodle FROM \"{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}\" WHERE id_curso = %s;"
            self.cursor.execute(sql_consulta, (id_curso,))
            return {fila["identificador_archivo"]: fila["tiempo_modificacion_moodle"] for fila in self.cursor.fetchall()}
        except Exception as e:
            registrador.error(f"Error obteniendo marcas de tiempo para curso '{id_curso}': {e}")
            return {}

    def es_archivo_nuevo_o_modificado(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_moodle: int) -> bool:
        self._conectar()
        try:
            sql_consulta = f"SELECT tiempo_modificacion_moodle FROM \"{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}\" WHERE id_curso = %s AND identificador_archivo = %s;"
            self.cursor.execute(sql_consulta, (id_curso, identificador_archivo))
            resultado = self.cursor.fetchone()
            if resultado is None:
                return True
            return tiempo_modificacion_moodle > resultado["tiempo_modificacion_moodle"]
        except Exception as e:
            registrador.error(f"Error verificando estado de archivo '{identificador_archivo}' curso '{id_curso}': {e}")
            return True

    def marcar_archivo_como_procesado(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_moodle: int) -> bool:
        self._conectar()
        procesado_en_ts = int(time.time())
        try:
            sql_upsert = f"""
            INSERT INTO "{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}" (id_curso, identificador_archivo, tiempo_modificacion_moodle, procesado_en)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_curso, identificador_archivo) DO UPDATE SET
                tiempo_modificacion_moodle = EXCLUDED.tiempo_modificacion_moodle,
                procesado_en = EXCLUDED.procesado_en;
            """
            self.cursor.execute(sql_upsert, (id_curso, identificador_archivo, tiempo_modificacion_moodle, procesado_en_ts))
            self._confirmar_cambios()
            registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) marcado como procesado.")
            return True
        except Exception as e:
            registrador.error(f"Error marcando archivo '{identificador_archivo}' (curso {id_curso}) como procesado: {e}")
            self._revertir_cambios()
            return False

    def eliminar_archivo_de_seguimiento(self, id_curso: int, identificador_archivo: str) -> bool:
        self._conectar()
        try:
            sql_eliminar = f"DELETE FROM \"{self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS}\" WHERE id_curso = %s AND identificador_archivo = %s;"
            self.cursor.execute(sql_eliminar, (id_curso, identificador_archivo))
            filas_eliminadas = self.cursor.rowcount
            self._confirmar_cambios()
            registrador.info(f"Eliminado seguimiento para archivo '{identificador_archivo}' (curso {id_curso}). Filas afectadas: {filas_eliminadas}.")
            return True
        except Exception as e:
            registrador.error(f"Error eliminando seguimiento para archivo '{identificador_archivo}' (curso {id_curso}): {e}")
            self._revertir_cambios()
            return False

    def cerrar_conexion(self):
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conexion:
            self._conexion.close()
            self._conexion = None
        registrador.info("Conexión a PostgreSQL cerrada.")

    def __del__(self):
        self.cerrar_conexion()

[end of entrenai_refactor/nucleo/bd/envoltorio_pgvector.py]
