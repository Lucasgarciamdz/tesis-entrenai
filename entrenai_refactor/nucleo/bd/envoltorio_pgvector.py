import re
import time
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor, execute_values
from typing import List, Dict, Any, Optional
import json # Para convertir metadatos a JSON string

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.api import modelos as modelos_api

registrador = obtener_registrador(__name__)

class ErrorBaseDeDatosVectorial(Exception):
    """Excepción personalizada para errores del EnvoltorioBaseDeDatosVectorial."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorBaseDeDatosVectorial creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()


class EnvoltorioPgVector:
    """
    Envoltorio para interactuar con PostgreSQL y la extensión pgvector.
    Gestiona conexiones, creación de tablas, inserción y búsqueda de embeddings.
    """

    _NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS = "seguimiento_archivos_procesados"

    def __init__(self):
        self.config_db = configuracion_global.db
        self._conexion_db: Optional[psycopg2.extensions.connection] = None
        self._cursor_db: Optional[RealDictCursor] = None
        registrador.info("EnvoltorioPgVector inicializado. La conexión a la base de datos se establecerá de forma perezosa.")

    def _conectar_a_db(self):
        """
        Establece o verifica una conexión activa a la base de datos PostgreSQL.
        Si la conexión o el cursor están cerrados o no existen, intenta (re)establecerlos.
        """
        if self._conexion_db and not self._conexion_db.closed:
            if self._cursor_db and not self._cursor_db.closed:
                registrador.debug("Conexión y cursor a BD ya activos.")
                return # Ya conectado y cursor listo

            # Conexión activa, pero cursor cerrado o no inicializado
            try:
                self._cursor_db = self._conexion_db.cursor(cursor_factory=RealDictCursor)
                registrador.info("Cursor recreado para conexión a BD existente.")
                return
            except psycopg2.Error as e_cursor:
                registrador.warning(f"No se pudo recrear el cursor ({e_cursor}). Se intentará reconexión completa a la BD.")
                self._cerrar_conexion_actual() # Forzar cierre para reconectar

        registrador.info(f"Intentando conectar a PostgreSQL en {self.config_db.host_db}:{self.config_db.puerto_db}, BD: {self.config_db.nombre_base_datos}") # CAMBIADO

        if not all([self.config_db.host_db, self.config_db.puerto_db, self.config_db.usuario_db, self.config_db.contrasena_db, self.config_db.nombre_base_datos]): # CAMBIADO
            registrador.error("Faltan detalles de configuración para la conexión a PgVector (host, puerto, usuario, etc.).")
            raise ErrorBaseDeDatosVectorial("Detalles de conexión a PgVector incompletos en la configuración.")

        try:
            self._conexion_db = psycopg2.connect(
                host=self.config_db.host_db, # CAMBIADO
                port=self.config_db.puerto_db, # CAMBIADO
                user=self.config_db.usuario_db, # CAMBIADO
                password=self.config_db.contrasena_db, # CAMBIADO
                dbname=self.config_db.nombre_base_datos, # CAMBIADO
            )
            self._conexion_db.autocommit = False # Controlar transacciones explícitamente
            self._cursor_db = self._conexion_db.cursor(cursor_factory=RealDictCursor)

            register_vector(self._conexion_db) # Registrar el adaptador para tipos 'vector'
            self._cursor_db.execute("CREATE EXTENSION IF NOT EXISTS vector;") # Asegurar extensión pgvector
            self._confirmar_transaccion() # Commit para CREATE EXTENSION

            registrador.info(f"Conexión a PgVector establecida: {self.config_db.host_db}:{self.config_db.puerto_db}/{self.config_db.nombre_base_datos}") # CAMBIADO
            self._asegurar_tabla_seguimiento_archivos() # Asegurar que la tabla de seguimiento exista
        except psycopg2.OperationalError as e_op:
            registrador.error(f"Error operacional al conectar a PostgreSQL/pgvector: {e_op}")
            self._cerrar_conexion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error operacional al conectar a la base de datos: {e_op}", e_op)
        except psycopg2.Error as e_psycopg: # Otros errores de psycopg2
            registrador.error(f"Error de Psycopg2 al conectar a PostgreSQL/pgvector: {e_psycopg}")
            self._cerrar_conexion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error de base de datos al conectar: {e_psycopg}", e_psycopg)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado durante la conexión a PgVector: {e_inesperado}")
            self._cerrar_conexion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado durante la conexión a la base de datos: {e_inesperado}", e_inesperado)

    @property
    def cursor(self) -> RealDictCursor:
        """
        Propiedad para acceder al cursor de la base de datos.
        Asegura que la conexión esté activa y el cursor disponible.
        """
        self._conectar_a_db() # Asegura que _conexion_db y _cursor_db estén inicializados
        if not self._cursor_db or self._cursor_db.closed:
             # Esto no debería ocurrir si _conectar_a_db funciona correctamente
             registrador.critical("El cursor de la BD no está disponible después de _conectar_a_db. Esto indica un problema severo.")
             raise ErrorBaseDeDatosVectorial("Cursor de base de datos no disponible después de múltiples intentos.")
        return self._cursor_db

    def _confirmar_transaccion(self):
        """Confirma la transacción actual en la base de datos."""
        if self._conexion_db and not self._conexion_db.closed:
            try:
                self._conexion_db.commit()
                registrador.debug("Transacción confirmada (commit) en la base de datos.")
            except psycopg2.Error as e_commit:
                registrador.error(f"Error al intentar confirmar transacción (commit): {e_commit}")
                raise ErrorBaseDeDatosVectorial("Error al confirmar transacción en la BD.", e_commit)
        else:
            registrador.warning("No hay conexión activa a la BD para confirmar transacción.")
            # Considerar si esto debería ser una excepción, ya que es un estado anómalo.

    def _revertir_transaccion(self):
        """Revierte la transacción actual en la base de datos."""
        if self._conexion_db and not self._conexion_db.closed:
            try:
                self._conexion_db.rollback()
                registrador.info("Transacción revertida (rollback) en la base de datos.")
            except psycopg2.Error as e_rollback:
                registrador.error(f"Error al intentar revertir transacción (rollback): {e_rollback}")
                # No lanzar excepción aquí usualmente, ya que rollback se usa en manejo de errores.
        else:
            registrador.warning("No hay conexión activa a la BD para revertir transacción.")


    @staticmethod
    def _normalizar_nombre_para_identificador_sql(nombre_original: str) -> str:
        """Normaliza un nombre para ser usado como identificador SQL (ej. nombre de tabla)."""
        if not nombre_original:
            registrador.error("Se intentó normalizar un nombre vacío para identificador SQL.")
            raise ValueError("El nombre original no puede estar vacío para generar un identificador SQL.")

        nombre_en_minusculas = nombre_original.lower()
        # Reemplazar espacios y caracteres no alfanuméricos (excepto '_') con '_'
        nombre_procesado = re.sub(r"\s+", "_", nombre_en_minusculas)
        nombre_procesado = re.sub(r"[^a-z0-9_]", "", nombre_procesado)

        # Truncar para evitar nombres excesivamente largos (PostgreSQL tiene un límite, ej. 63 bytes)
        nombre_procesado = nombre_procesado[:50]

        if not nombre_procesado: # Si después de normalizar queda vacío (ej. nombre original era "!!!")
            registrador.error(f"Nombre original '{nombre_original}' resultó en identificador SQL normalizado vacío.")
            # Podría generarse un UUID o hash como fallback si se permite, o lanzar error.
            raise ValueError(f"Nombre original '{nombre_original}' resultó en identificador SQL normalizado vacío.")

        # Asegurar que no empiece con un número (aunque CREATE TABLE lo permitiría si va entre comillas)
        if nombre_procesado[0].isdigit():
            nombre_procesado = "_" + nombre_procesado
            nombre_procesado = nombre_procesado[:50] # Re-truncar si se añadió prefijo

        return nombre_procesado

    def obtener_nombre_tabla_para_curso(self, identificador_curso: Any) -> str:
        """Genera un nombre de tabla seguro y normalizado para un curso."""
        nombre_base_curso = str(identificador_curso) # Convertir a string por si acaso
        nombre_normalizado_curso = self._normalizar_nombre_para_identificador_sql(nombre_base_curso)

        prefijo_tabla_limpio = self.config_db.prefijo_tabla_cursos_vectorial.replace('"', '') # CAMBIADO: prefijo_coleccion -> prefijo_tabla_cursos_vectorial
        nombre_tabla_final = f"{prefijo_tabla_limpio}{nombre_normalizado_curso}"
        registrador.debug(f"Nombre de tabla generado para curso '{identificador_curso}': '{nombre_tabla_final}'")
        return nombre_tabla_final

    def asegurar_existencia_tabla_curso(self, identificador_curso: Any, dimension_vector: int) -> bool:
        """Asegura que la tabla para un curso específico exista, creándola si es necesario."""
        self._conectar_a_db()
        nombre_tabla_curso = self.obtener_nombre_tabla_para_curso(identificador_curso)

        try:
            # Verificar si la tabla ya existe (usar %s para el nombre de tabla previene inyección si se escapa correctamente)
            # Sin embargo, los nombres de tabla no pueden ser placeholders directos en SQL. Se debe construir la query.
            # Es crucial que `nombre_tabla_curso` sea seguro (lo es por `_normalizar_nombre_para_identificador_sql`).
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_curso}');")
            resultado_existencia = self.cursor.fetchone()

            if resultado_existencia and resultado_existencia["exists"]:
                registrador.info(f"Tabla '{nombre_tabla_curso}' ya existe. No se requiere creación.")
                return True

            registrador.info(f"Tabla '{nombre_tabla_curso}' no existe. Creando tabla...")
            sql_crear_tabla = f"""
            CREATE TABLE IF NOT EXISTS "{nombre_tabla_curso}" (
                id_fragmento TEXT PRIMARY KEY,
                id_curso TEXT,
                id_documento TEXT,
                texto TEXT,
                metadatos JSONB,
                embedding vector({dimension_vector})
            );
            """
            self.cursor.execute(sql_crear_tabla)
            registrador.info(f"Tabla '{nombre_tabla_curso}' creada con dimensión de vector {dimension_vector}.")

            # Crear índice HNSW para búsquedas eficientes.
            # Para vectores de alta dimensionalidad (>2000), se recomienda usar halfvec con HNSW.
            # Esta lógica puede necesitar ajustarse según la versión de pgvector y las necesidades.
            if dimension_vector > 2000 and False: # Deshabilitado temporalmente por simplicidad, halfvec requiere compilación especial
                sql_crear_indice = f"CREATE INDEX IF NOT EXISTS idx_hnsw_{nombre_tabla_curso} ON \"{nombre_tabla_curso}\" USING hnsw ((embedding::halfvec({dimension_vector})) halfvec_cosine_ops);"
                registrador.info(f"Creando índice HNSW con halfvec para tabla '{nombre_tabla_curso}'.")
            else:
                sql_crear_indice = f"CREATE INDEX IF NOT EXISTS idx_hnsw_{nombre_tabla_curso} ON \"{nombre_tabla_curso}\" USING hnsw (embedding vector_l2_ops);" # O vector_cosine_ops, vector_ip_ops
                registrador.info(f"Creando índice HNSW estándar para tabla '{nombre_tabla_curso}'.")

            self.cursor.execute(sql_crear_indice)
            self._confirmar_transaccion()
            registrador.info(f"Índice HNSW creado para tabla '{nombre_tabla_curso}'.")
            return True

        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al asegurar tabla '{nombre_tabla_curso}': {e_db}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error al asegurar tabla del curso '{nombre_tabla_curso}'.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al asegurar tabla '{nombre_tabla_curso}': {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al asegurar tabla del curso '{nombre_tabla_curso}'.", e_inesperado)


    def insertar_o_actualizar_fragmentos(self, identificador_curso: Any, fragmentos_documento: List[modelos_api.FragmentoDocumento]) -> bool:
        """Inserta o actualiza una lista de fragmentos de documento en la tabla del curso."""
        self._conectar_a_db()
        if not fragmentos_documento:
            registrador.info("No hay fragmentos para insertar o actualizar.")
            return True

        nombre_tabla_curso = self.obtener_nombre_tabla_para_curso(identificador_curso)

        # Determinar la dimensión del vector del primer fragmento válido
        dimension_vector_actual = self.config_db.dimension_embedding_defecto # CAMBIADO: tamano_vector_defecto -> dimension_embedding_defecto
        for frag in fragmentos_documento:
            if frag.embedding:
                dimension_vector_actual = len(frag.embedding)
                break

        if not self.asegurar_existencia_tabla_curso(identificador_curso, dimension_vector_actual):
            registrador.error(f"Falló la creación/aseguramiento de la tabla '{nombre_tabla_curso}' para la inserción de fragmentos.")
            return False

        datos_para_upsert = []
        for fragmento in fragmentos_documento:
            if fragmento.embedding is None:
                registrador.warning(f"Fragmento ID '{fragmento.id_fragmento}' (curso: {fragmento.id_curso}, doc: {fragmento.id_documento}) no tiene embedding. Se omitirá.")
                continue
            # Convertir metadatos a string JSON si es un dict, sino se asume que ya es un string JSON o None
            metadatos_serializados = json.dumps(fragmento.metadatos) if isinstance(fragmento.metadatos, dict) else fragmento.metadatos
            datos_para_upsert.append(
                (fragmento.id_fragmento, str(fragmento.id_curso), fragmento.id_documento, fragmento.texto, metadatos_serializados, fragmento.embedding)
            )

        if not datos_para_upsert:
            registrador.info(f"No hay fragmentos válidos con embeddings para insertar/actualizar en '{nombre_tabla_curso}'.")
            return True

        registrador.info(f"Insertando/actualizando {len(datos_para_upsert)} fragmentos en tabla '{nombre_tabla_curso}'.")
        try:
            # SQL para inserción masiva con manejo de conflictos (UPSERT)
            sql_plantilla_upsert = f"""
            INSERT INTO "{nombre_tabla_curso}" (id_fragmento, id_curso, id_documento, texto, metadatos, embedding)
            VALUES %s
            ON CONFLICT (id_fragmento) DO UPDATE SET
                id_curso = EXCLUDED.id_curso,
                id_documento = EXCLUDED.id_documento,
                texto = EXCLUDED.texto,
                metadatos = EXCLUDED.metadatos,
                embedding = EXCLUDED.embedding;
            """
            execute_values(self.cursor, sql_plantilla_upsert, datos_para_upsert, page_size=100) # page_size para grandes inserciones
            self._confirmar_transaccion()
            registrador.info(f"Se insertaron/actualizaron {len(datos_para_upsert)} fragmentos exitosamente en tabla '{nombre_tabla_curso}'.")
            return True
        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al insertar/actualizar fragmentos en tabla '{nombre_tabla_curso}': {e_db}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error al insertar/actualizar fragmentos en '{nombre_tabla_curso}'.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al insertar/actualizar fragmentos en tabla '{nombre_tabla_curso}': {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al procesar fragmentos para '{nombre_tabla_curso}'.", e_inesperado)

    def buscar_fragmentos_similares_por_embedding(
        self, identificador_curso: Any, embedding_consulta: List[float], limite_resultados: int = 5, factor_ef_search: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Busca fragmentos similares a un embedding de consulta en la tabla del curso."""
        self._conectar_a_db()
        nombre_tabla_curso = self.obtener_nombre_tabla_para_curso(identificador_curso)
        registrador.info(f"Buscando {limite_resultados} fragmentos similares en tabla '{nombre_tabla_curso}'.")

        try:
            # Opcionalmente, ajustar el parámetro `hnsw.ef_search` para la sesión actual.
            # Un valor más alto puede mejorar la precisión (recall) a costa de la velocidad.
            if factor_ef_search is not None:
                self.cursor.execute("SET LOCAL hnsw.ef_search = %s;", (factor_ef_search,))
                registrador.debug(f"Parámetro hnsw.ef_search ajustado a {factor_ef_search} para esta consulta.")

            dimension_vector_consulta = len(embedding_consulta)
            # Usar el operador '<=>' para distancia L2, '<#>' para producto interno, o '<->' para coseno (1 - similitud coseno)
            # Para similitud de coseno directa (mayor es mejor), se usa `1 - (embedding <=> vector)`
            sql_busqueda_similitud = f"""
            SELECT id_fragmento, id_curso, id_documento, texto, metadatos, (1 - (embedding <=> %s::vector({dimension_vector_consulta}))) AS similitud
            FROM "{nombre_tabla_curso}"
            ORDER BY embedding <=> %s::vector({dimension_vector_consulta})
            LIMIT %s;
            """
            # El orden es por distancia (menor es mejor), por eso se usa directamente el operador de distancia.
            # La similitud se calcula después para mostrarla.

            self.cursor.execute(sql_busqueda_similitud, (embedding_consulta, embedding_consulta, limite_resultados))
            filas_resultado = self.cursor.fetchall()

            resultados_formateados = []
            for fila in filas_resultado:
                metadatos_dict = {}
                if fila.get("metadatos"):
                    if isinstance(fila["metadatos"], str): # Si se almacenó como string JSON
                        try:
                            metadatos_dict = json.loads(fila["metadatos"])
                        except json.JSONDecodeError:
                            registrador.warning(f"No se pudo decodificar metadatos JSON para fragmento {fila['id_fragmento']}: {fila['metadatos']}")
                    elif isinstance(fila["metadatos"], dict): # Si ya es un dict (JSONB)
                        metadatos_dict = fila["metadatos"]

                resultados_formateados.append({
                    "id_fragmento": fila["id_fragmento"],
                    "similitud": fila["similitud"], # Asumiendo que 0 es idéntico y 1 es muy diferente (distancia)
                    "payload": { # Datos adicionales del fragmento
                        "id_curso": fila.get("id_curso"),
                        "id_documento": fila.get("id_documento"),
                        "texto": fila.get("texto"),
                        **metadatos_dict, # Desempaquetar metadatos en el payload
                    }
                })
            registrador.info(f"Búsqueda en tabla '{nombre_tabla_curso}' encontró {len(resultados_formateados)} resultados.")
            return resultados_formateados

        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al buscar en tabla '{nombre_tabla_curso}': {e_db}")
            # No revertir aquí, ya que es una consulta SELECT.
            raise ErrorBaseDeDatosVectorial(f"Error al buscar similitudes en '{nombre_tabla_curso}'.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al buscar en tabla '{nombre_tabla_curso}': {e_inesperado}")
            raise ErrorBaseDeDatosVectorial(f"Error inesperado durante búsqueda en '{nombre_tabla_curso}'.", e_inesperado)


    def eliminar_fragmentos_por_id_documento(self, identificador_curso: Any, id_documento_a_eliminar: str) -> bool:
        """Elimina todos los fragmentos asociados a un ID de documento específico de la tabla del curso."""
        self._conectar_a_db()
        nombre_tabla_curso = self.obtener_nombre_tabla_para_curso(identificador_curso)
        registrador.info(f"Intentando eliminar fragmentos para ID de documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso}'.")

        try:
            # Verificar primero si la tabla existe para evitar errores si no existe
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_curso}');")
            if not (resultado_existencia := self.cursor.fetchone()) or not resultado_existencia["exists"]:
                registrador.warning(f"Tabla '{nombre_tabla_curso}' no existe. No se pueden eliminar fragmentos para documento ID '{id_documento_a_eliminar}'. Se considera operación exitosa (nada que eliminar).")
                return True

            sql_eliminar_fragmentos = f'DELETE FROM "{nombre_tabla_curso}" WHERE id_documento = %s;'
            self.cursor.execute(sql_eliminar_fragmentos, (id_documento_a_eliminar,))
            filas_afectadas = self.cursor.rowcount # Número de filas eliminadas
            self._confirmar_transaccion()

            registrador.info(f"Se eliminaron {filas_afectadas} fragmentos para el ID de documento '{id_documento_a_eliminar}' de la tabla '{nombre_tabla_curso}'.")
            return True
        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al eliminar fragmentos para ID de documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso}': {e_db}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error al eliminar fragmentos del documento '{id_documento_a_eliminar}'.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al eliminar fragmentos del documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso}': {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al eliminar fragmentos del documento '{id_documento_a_eliminar}'.", e_inesperado)

    # --- Métodos para seguimiento de archivos procesados ---

    def _asegurar_tabla_seguimiento_archivos(self):
        """Asegura que la tabla para el seguimiento de archivos procesados exista."""
        # Esta función es llamada internamente por _conectar_a_db, por lo que la conexión ya debería estar activa.
        if not self._conexion_db or not self._cursor_db or self._conexion_db.closed or self._cursor_db.closed:
             registrador.critical("No hay conexión a BD para asegurar tabla de seguimiento. Esto no debería pasar si _conectar_a_db fue llamado.")
             raise ErrorBaseDeDatosVectorial("Conexión no disponible para asegurar tabla de seguimiento de archivos.")

        nombre_tabla_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS
        registrador.debug(f"Asegurando existencia de tabla de seguimiento de archivos: '{nombre_tabla_seguimiento}'.")
        try:
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_seguimiento}');")
            if (resultado_existencia := self.cursor.fetchone()) and resultado_existencia["exists"]:
                registrador.debug(f"Tabla de seguimiento '{nombre_tabla_seguimiento}' ya existe.")
                return

            registrador.info(f"Tabla de seguimiento '{nombre_tabla_seguimiento}' no existe. Creando tabla...")
            sql_crear_tabla_seguimiento = f"""
            CREATE TABLE IF NOT EXISTS "{nombre_tabla_seguimiento}" (
                id_curso INTEGER NOT NULL,
                identificador_archivo TEXT NOT NULL,
                tiempo_modificacion_moodle BIGINT NOT NULL,
                procesado_en BIGINT NOT NULL, -- Timestamp Unix de cuándo fue procesado
                PRIMARY KEY (id_curso, identificador_archivo)
            );
            """
            # `identificador_archivo` podría ser un `instanceid` de Moodle, o un path único si es de otra fuente.
            self.cursor.execute(sql_crear_tabla_seguimiento)
            self._confirmar_transaccion() # Importante hacer commit después de CREATE TABLE
            registrador.info(f"Tabla de seguimiento de archivos '{nombre_tabla_seguimiento}' creada exitosamente.")
        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al asegurar la tabla de seguimiento '{nombre_tabla_seguimiento}': {e_db}")
            self._revertir_transaccion() # Revertir si la creación falla
            raise ErrorBaseDeDatosVectorial(f"Error al asegurar tabla de seguimiento de archivos.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al asegurar la tabla de seguimiento '{nombre_tabla_seguimiento}': {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al asegurar tabla de seguimiento.", e_inesperado)


    def obtener_marcas_de_tiempo_archivos_procesados_curso(self, id_curso: int) -> Dict[str, int]:
        """Obtiene un diccionario de {identificador_archivo: tiempo_modificacion_moodle} para un curso."""
        self._conectar_a_db()
        nombre_tabla_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS
        registrador.debug(f"Obteniendo marcas de tiempo de archivos procesados para curso ID {id_curso} desde '{nombre_tabla_seguimiento}'.")
        try:
            sql_consulta_marcas = f'SELECT identificador_archivo, tiempo_modificacion_moodle FROM "{nombre_tabla_seguimiento}" WHERE id_curso = %s;'
            self.cursor.execute(sql_consulta_marcas, (id_curso,))
            archivos_procesados = {fila["identificador_archivo"]: fila["tiempo_modificacion_moodle"] for fila in self.cursor.fetchall()}
            registrador.info(f"Se encontraron {len(archivos_procesados)} registros de archivos procesados para el curso ID {id_curso}.")
            return archivos_procesados
        except psycopg2.Error as e_db:
            registrador.error(f"Error de base de datos al obtener marcas de tiempo para curso ID '{id_curso}': {e_db}")
            raise ErrorBaseDeDatosVectorial(f"Error al obtener marcas de tiempo para curso {id_curso}.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al obtener marcas de tiempo para curso ID '{id_curso}': {e_inesperado}")
            raise ErrorBaseDeDatosVectorial(f"Error inesperado obteniendo marcas de tiempo para curso {id_curso}.", e_inesperado)

    def verificar_si_archivo_es_nuevo_o_modificado(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_actual_moodle: int) -> bool:
        """Comprueba si un archivo es nuevo o ha sido modificado desde su último procesamiento."""
        self._conectar_a_db()
        nombre_tabla_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS
        registrador.debug(f"Verificando estado del archivo '{identificador_archivo}' (curso ID {id_curso}) con timestamp Moodle {tiempo_modificacion_actual_moodle}.")
        try:
            sql_consulta_archivo = f'SELECT tiempo_modificacion_moodle FROM "{nombre_tabla_seguimiento}" WHERE id_curso = %s AND identificador_archivo = %s;'
            self.cursor.execute(sql_consulta_archivo, (id_curso, identificador_archivo))
            resultado_archivo = self.cursor.fetchone()

            if resultado_archivo is None:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) no encontrado en seguimiento. Se considera nuevo.")
                return True # Archivo no encontrado en la tabla de seguimiento, es nuevo.

            tiempo_modificacion_registrado = resultado_archivo["tiempo_modificacion_moodle"]
            if tiempo_modificacion_actual_moodle > tiempo_modificacion_registrado:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) ha sido modificado (Moodle: {tiempo_modificacion_actual_moodle} > DB: {tiempo_modificacion_registrado}).")
                return True # Archivo modificado.
            else:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) no ha cambiado (Moodle: {tiempo_modificacion_actual_moodle} <= DB: {tiempo_modificacion_registrado}).")
                return False # Archivo no modificado.

        except psycopg2.Error as e_db:
            registrador.error(f"Error de BD al verificar estado de archivo '{identificador_archivo}' (curso {id_curso}): {e_db}")
            # En caso de error, es más seguro asumir que necesita reprocesamiento.
            return True
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al verificar estado de archivo '{identificador_archivo}' (curso {id_curso}): {e_inesperado}")
            return True


    def marcar_archivo_como_procesado_en_seguimiento(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_moodle: int) -> bool:
        """Registra o actualiza un archivo en la tabla de seguimiento, marcándolo como procesado."""
        self._conectar_a_db()
        timestamp_procesamiento_actual = int(time.time())
        nombre_tabla_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS
        registrador.info(f"Marcando archivo '{identificador_archivo}' (curso ID {id_curso}, ts Moodle: {tiempo_modificacion_moodle}) como procesado en '{nombre_tabla_seguimiento}'.")

        try:
            sql_upsert_seguimiento = f"""
            INSERT INTO "{nombre_tabla_seguimiento}" (id_curso, identificador_archivo, tiempo_modificacion_moodle, procesado_en)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_curso, identificador_archivo) DO UPDATE SET
                tiempo_modificacion_moodle = EXCLUDED.tiempo_modificacion_moodle,
                procesado_en = EXCLUDED.procesado_en;
            """
            self.cursor.execute(sql_upsert_seguimiento, (id_curso, identificador_archivo, tiempo_modificacion_moodle, timestamp_procesamiento_actual))
            self._confirmar_transaccion()
            registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) marcado como procesado exitosamente.")
            return True
        except psycopg2.Error as e_db:
            registrador.error(f"Error de BD al marcar archivo '{identificador_archivo}' (curso {id_curso}) como procesado: {e_db}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error al marcar archivo '{identificador_archivo}' como procesado.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al marcar archivo '{identificador_archivo}' (curso {id_curso}) como procesado: {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado marcando archivo '{identificador_archivo}' como procesado.", e_inesperado)

    def eliminar_registro_de_archivo_en_seguimiento(self, id_curso: int, identificador_archivo: str) -> bool:
        """Elimina un archivo de la tabla de seguimiento (ej. si el archivo fue eliminado en Moodle)."""
        self._conectar_a_db()
        nombre_tabla_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS
        registrador.info(f"Eliminando seguimiento para archivo '{identificador_archivo}' (curso ID {id_curso}) de tabla '{nombre_tabla_seguimiento}'.")

        try:
            sql_eliminar_seguimiento = f'DELETE FROM "{nombre_tabla_seguimiento}" WHERE id_curso = %s AND identificador_archivo = %s;'
            self.cursor.execute(sql_eliminar_seguimiento, (id_curso, identificador_archivo))
            filas_afectadas = self.cursor.rowcount
            self._confirmar_transaccion()

            if filas_afectadas > 0:
                registrador.info(f"Registro de seguimiento para archivo '{identificador_archivo}' (curso {id_curso}) eliminado. Filas afectadas: {filas_afectadas}.")
            else:
                registrador.info(f"No se encontró registro de seguimiento para eliminar para archivo '{identificador_archivo}' (curso {id_curso}).")
            return True
        except psycopg2.Error as e_db:
            registrador.error(f"Error de BD al eliminar seguimiento para archivo '{identificador_archivo}' (curso {id_curso}): {e_db}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error al eliminar registro de seguimiento del archivo '{identificador_archivo}'.", e_db)
        except Exception as e_inesperado:
            registrador.exception(f"Error inesperado al eliminar seguimiento para archivo '{identificador_archivo}' (curso {id_curso}): {e_inesperado}")
            self._revertir_transaccion()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado eliminando registro de seguimiento del archivo '{identificador_archivo}'.", e_inesperado)

    def _cerrar_conexion_actual(self):
        """Cierra el cursor y la conexión a la base de datos si están abiertos."""
        if self._cursor_db and not self._cursor_db.closed:
            self._cursor_db.close()
            registrador.debug("Cursor de BD cerrado.")
        self._cursor_db = None # Asegurar que se limpie
        if self._conexion_db and not self._conexion_db.closed:
            self._conexion_db.close()
            registrador.debug("Conexión a BD cerrada.")
        self._conexion_db = None # Asegurar que se limpie

    def cerrar_conexion_a_db(self):
        """Método público para cerrar la conexión a la base de datos."""
        registrador.info("Solicitud para cerrar conexión a la base de datos.")
        self._cerrar_conexion_actual()

    def __del__(self):
        """Destructor para asegurar el cierre de la conexión al eliminar el objeto."""
        registrador.debug("Destructor de EnvoltorioPgVector llamado. Cerrando conexión a BD.")
        self._cerrar_conexion_actual()

[end of entrenai_refactor/nucleo/bd/envoltorio_pgvector_refactorizado.py]
