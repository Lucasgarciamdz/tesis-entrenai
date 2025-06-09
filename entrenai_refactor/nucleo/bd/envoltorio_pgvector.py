import re
import time
import psycopg2
from pgvector.psycopg2 import register_vector # Adaptador de pgvector para psycopg2
from psycopg2.extras import RealDictCursor, execute_values # Para cursores que devuelven dicts y inserción masiva
from typing import List, Dict, Any, Optional
import json # Para convertir metadatos (dict) a string JSON para la BD

from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.api import modelos as modelos_api # Modelos Pydantic para la API

registrador = obtener_registrador(__name__)

class ErrorBaseDeDatosVectorial(Exception):
    """Excepción personalizada para errores relacionados con el EnvoltorioPgVector."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None, tabla_implicada: Optional[str] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        self.tabla_implicada = tabla_implicada
        detalle_tabla = f", Tabla: {tabla_implicada}" if tabla_implicada else ""
        registrador.debug(f"Excepción ErrorBaseDeDatosVectorial creada: '{mensaje}'{detalle_tabla}, Original: {error_original}")

    def __str__(self):
        detalle_tabla = f" (Tabla implicada: {self.tabla_implicada})" if self.tabla_implicada else ""
        if self.error_original:
            return f"{super().__str__()}{detalle_tabla} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return f"{super().__str__()}{detalle_tabla}"


class EnvoltorioPgVector:
    """
    Envoltorio para interactuar con una base de datos PostgreSQL que utiliza la extensión pgvector.
    Gestiona las conexiones, la creación dinámica de tablas para cursos, la inserción/actualización (upsert)
    de fragmentos de documentos con sus embeddings, y la búsqueda de similitud vectorial.
    También maneja una tabla de seguimiento para archivos procesados.
    """

    _NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS = "seguimiento_archivos_procesados" # Nombre fijo para la tabla de seguimiento

    def __init__(self):
        self.config_db = configuracion_global.db # Configuración específica de la BD desde la config global
        self._conexion_activa_db: Optional[psycopg2.extensions.connection] = None # Conexión activa
        self._cursor_activo_db: Optional[RealDictCursor] = None # Cursor activo
        registrador.info("EnvoltorioPgVector inicializado. La conexión a la base de datos se establecerá de forma perezosa (al primer uso).")

    def _establecer_o_verificar_conexion_db(self):
        """
        Establece una nueva conexión a la base de datos PostgreSQL si no existe una activa,
        o verifica que la conexión y el cursor existentes estén abiertos.
        Si la conexión o el cursor están cerrados o no existen, intenta (re)establecerlos.
        """
        # Verificar si ya hay una conexión y cursor válidos
        if self._conexion_activa_db and not self._conexion_activa_db.closed:
            if self._cursor_activo_db and not self._cursor_activo_db.closed:
                registrador.debug("Conexión y cursor a la base de datos ya están activos y listos.")
                return # Conexión y cursor listos

            # Conexión activa, pero el cursor está cerrado o no inicializado
            try:
                self._cursor_activo_db = self._conexion_activa_db.cursor(cursor_factory=RealDictCursor)
                registrador.info("Cursor recreado para la conexión existente a la base de datos.")
                return
            except psycopg2.Error as e_crear_cursor:
                registrador.warning(f"No se pudo recrear el cursor para la conexión existente ({e_crear_cursor}). Se intentará una reconexión completa a la BD.")
                self._cerrar_conexion_db_interna() # Forzar cierre para una reconexión completa

        registrador.info(f"Intentando conectar a PostgreSQL en {self.config_db.host_db}:{self.config_db.puerto_db}, Base de Datos: {self.config_db.nombre_base_datos}")

        # Validar que todos los detalles de configuración necesarios estén presentes
        if not all([self.config_db.host_db, self.config_db.puerto_db, self.config_db.usuario_db, self.config_db.contrasena_db, self.config_db.nombre_base_datos]):
            registrador.error("Faltan detalles de configuración para la conexión a PgVector (host, puerto, usuario, contraseña, nombre_base_datos).")
            raise ErrorBaseDeDatosVectorial("Detalles de conexión a PgVector incompletos en la configuración de la aplicación.")

        try:
            self._conexion_activa_db = psycopg2.connect(
                host=self.config_db.host_db,
                port=self.config_db.puerto_db,
                user=self.config_db.usuario_db,
                password=self.config_db.contrasena_db,
                dbname=self.config_db.nombre_base_datos,
            )
            self._conexion_activa_db.autocommit = False # Deshabilitar autocommit para controlar transacciones explícitamente
            self._cursor_activo_db = self._conexion_activa_db.cursor(cursor_factory=RealDictCursor) # Usar RealDictCursor para obtener filas como diccionarios

            register_vector(self._conexion_activa_db) # Registrar el adaptador globalmente para el tipo 'vector' con psycopg2
            self._cursor_activo_db.execute("CREATE EXTENSION IF NOT EXISTS vector;") # Asegurar que la extensión pgvector esté habilitada
            self._confirmar_transaccion_actual() # Hacer commit para CREATE EXTENSION IF NOT EXISTS

            registrador.info(f"Conexión a PgVector establecida y extensión 'vector' asegurada para: {self.config_db.host_db}:{self.config_db.puerto_db}/{self.config_db.nombre_base_datos}")
            self._asegurar_existencia_tabla_seguimiento_archivos() # Asegurar que la tabla de seguimiento de archivos exista
        except psycopg2.OperationalError as e_operacional: # Errores como BD no disponible, credenciales incorrectas
            registrador.error(f"Error operacional al conectar a PostgreSQL/pgvector: {e_operacional}")
            self._cerrar_conexion_db_interna() # Limpiar recursos
            raise ErrorBaseDeDatosVectorial(f"Error operacional al conectar a la base de datos: {e_operacional}", e_operacional)
        except psycopg2.Error as e_psycopg_general: # Otros errores de psycopg2 (configuración, etc.)
            registrador.error(f"Error de Psycopg2 al conectar a PostgreSQL/pgvector: {e_psycopg_general}")
            self._cerrar_conexion_db_interna()
            raise ErrorBaseDeDatosVectorial(f"Error de base de datos al conectar: {e_psycopg_general}", e_psycopg_general)
        except Exception as e_inesperado_conexion: # Errores no previstos
            registrador.exception(f"Error inesperado durante la conexión a PgVector: {e_inesperado_conexion}")
            self._cerrar_conexion_db_interna()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado durante la conexión a la base de datos: {e_inesperado_conexion}", e_inesperado_conexion)

    @property
    def cursor(self) -> RealDictCursor:
        """
        Propiedad para acceder al cursor de la base de datos de forma segura.
        Asegura que la conexión esté activa y el cursor disponible antes de devolverlo.
        """
        self._establecer_o_verificar_conexion_db() # Asegura que _conexion_activa_db y _cursor_activo_db estén inicializados
        if not self._cursor_activo_db or self._cursor_activo_db.closed:
             # Esta situación no debería ocurrir si _establecer_o_verificar_conexion_db funciona correctamente.
             registrador.critical("El cursor de la BD no está disponible después de _establecer_o_verificar_conexion_db. Esto indica un problema severo en la lógica de conexión.")
             raise ErrorBaseDeDatosVectorial("Cursor de base de datos no disponible después de múltiples intentos de conexión/recreación.")
        return self._cursor_activo_db

    def _confirmar_transaccion_actual(self):
        """Confirma (commit) la transacción actual en la base de datos."""
        if self._conexion_activa_db and not self._conexion_activa_db.closed:
            try:
                self._conexion_activa_db.commit()
                registrador.debug("Transacción confirmada (commit) en la base de datos.")
            except psycopg2.Error as e_commit:
                registrador.error(f"Error al intentar confirmar transacción (commit) en la BD: {e_commit}")
                # Es importante relanzar para que el llamador sepa que el commit falló.
                raise ErrorBaseDeDatosVectorial("Error al confirmar la transacción en la base de datos.", e_commit)
        else:
            registrador.warning("No hay conexión activa a la BD para confirmar la transacción. La operación podría no haberse persistido.")
            # Considerar si esto debería ser una excepción, ya que indica un estado anómalo si se esperaba un commit.

    def _revertir_transaccion_actual(self):
        """Revierte (rollback) la transacción actual en la base de datos."""
        if self._conexion_activa_db and not self._conexion_activa_db.closed:
            try:
                self._conexion_activa_db.rollback()
                registrador.info("Transacción revertida (rollback) en la base de datos debido a un error previo.")
            except psycopg2.Error as e_rollback:
                # Un error durante el rollback es problemático. Se loguea, pero no se suele relanzar
                # porque el rollback ya es parte de un manejo de error.
                registrador.error(f"Error adicional al intentar revertir transacción (rollback) en la BD: {e_rollback}")
        else:
            registrador.warning("No hay conexión activa a la BD para revertir la transacción.")


    @staticmethod
    def _normalizar_nombre_para_identificador_sql(nombre_original: str) -> str:
        """
        Normaliza un nombre de cadena para ser usado de forma segura como identificador SQL
        (ej. nombre de tabla o índice). Aplica varias reglas para asegurar compatibilidad.
        """
        if not nombre_original: # Comprobar si la cadena original está vacía
            registrador.error("Se intentó normalizar un nombre vacío para identificador SQL.")
            raise ValueError("El nombre original no puede estar vacío para generar un identificador SQL.")

        nombre_en_minusculas = nombre_original.strip().lower() # Quitar espacios al inicio/fin y convertir a minúsculas
        # Reemplazar espacios y secuencias de caracteres no alfanuméricos (excepto '_') con un solo '_'
        nombre_procesado = re.sub(r"\s+", "_", nombre_en_minusculas)
        nombre_procesado = re.sub(r"[^a-z0-9_]+", "", nombre_procesado) # Eliminar cualquier caracter que no sea letra minúscula, número o guion bajo

        # Truncar para evitar nombres excesivamente largos (PostgreSQL tiene un límite, ej. 63 bytes/caracteres)
        # Dejar espacio para posibles prefijos o sufijos si se añaden después.
        nombre_procesado = nombre_procesado[:50]

        if not nombre_procesado: # Si después de normalizar queda vacío (ej. nombre original era "!!!")
            registrador.error(f"Nombre original '{nombre_original}' resultó en identificador SQL normalizado vacío tras limpieza.")
            raise ValueError(f"Nombre original '{nombre_original}' resultó en un identificador SQL normalizado vacío e inválido.")

        # Asegurar que no empiece con un número (aunque CREATE TABLE lo permitiría si va entre comillas, es buena práctica evitarlo)
        if nombre_procesado[0].isdigit():
            nombre_procesado = "_" + nombre_procesado # Añadir prefijo '_'
            nombre_procesado = nombre_procesado[:50] # Re-truncar si la adición del prefijo excedió el límite

        return nombre_procesado

    def obtener_nombre_tabla_curso_normalizado(self, identificador_curso: Any) -> str:
        """Genera un nombre de tabla seguro y normalizado para un curso específico."""
        nombre_base_curso = str(identificador_curso) # Asegurar que el identificador sea un string
        nombre_normalizado_curso = self._normalizar_nombre_para_identificador_sql(nombre_base_curso)

        # Limpiar el prefijo de la configuración por si acaso contiene caracteres no deseados (aunque no debería)
        prefijo_tabla_limpio = self.config_db.prefijo_tabla_cursos_vectorial.strip().replace('"', '')
        nombre_tabla_final = f"{prefijo_tabla_limpio}{nombre_normalizado_curso}"
        registrador.debug(f"Nombre de tabla SQL normalizado generado para curso '{identificador_curso}': '{nombre_tabla_final}'")
        return nombre_tabla_final

    def asegurar_existencia_tabla_curso(self, identificador_curso: Any, dimension_vector_embeddings: int) -> bool:
        """
        Asegura que la tabla para un curso específico exista en la BD. Si no existe, la crea
        junto con un índice HNSW para búsquedas de similitud eficientes.
        """
        self._establecer_o_verificar_conexion_db() # Asegurar conexión
        nombre_tabla_curso_seguro = self.obtener_nombre_tabla_curso_normalizado(identificador_curso)

        try:
            # Verificar si la tabla ya existe usando information_schema.
            # Es crucial que `nombre_tabla_curso_seguro` sea seguro (lo es por `_normalizar_nombre_para_identificador_sql`).
            # Los nombres de tabla no pueden ser placeholders directos en SQL, por eso se construye la query con f-string.
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_curso_seguro}');")
            resultado_existencia_tabla = self.cursor.fetchone()

            if resultado_existencia_tabla and resultado_existencia_tabla["exists"]:
                registrador.info(f"Tabla '{nombre_tabla_curso_seguro}' ya existe. No se requiere creación.")
                return True # La tabla ya existe

            registrador.info(f"Tabla '{nombre_tabla_curso_seguro}' no existe. Procediendo a crearla...")
            # Definición de la tabla con tipos de datos apropiados.
            # 'id_fragmento' es la clave primaria.
            # 'metadatos' se almacena como JSONB para flexibilidad y eficiencia en consultas.
            # 'embedding' es del tipo 'vector' con la dimensión especificada.
            sql_crear_tabla_curso = f"""
            CREATE TABLE IF NOT EXISTS "{nombre_tabla_curso_seguro}" (
                id_fragmento TEXT PRIMARY KEY,
                id_curso TEXT NOT NULL,
                id_documento TEXT NOT NULL,
                texto TEXT,
                metadatos JSONB,
                embedding vector({dimension_vector_embeddings})
            );
            """
            self.cursor.execute(sql_crear_tabla_curso)
            registrador.info(f"Tabla '{nombre_tabla_curso_seguro}' creada con dimensión de vector {dimension_vector_embeddings}.")

            # Crear un índice HNSW (Hierarchical Navigable Small World) para búsquedas de similitud eficientes.
            # El tipo de operador de distancia (vector_l2_ops, vector_cosine_ops, vector_ip_ops)
            # debe coincidir con cómo se calculará la similitud/distancia en las búsquedas.
            # L2 (Euclidiana) es común: `embedding <=> otro_embedding`.
            # Coseno: `1 - (embedding <=> otro_embedding)` para similitud, o `<=>` para distancia coseno.
            # Producto Interno (IP): `embedding <#> otro_embedding` (negativo para distancia).
            nombre_indice_hnsw = f"idx_hnsw_{nombre_tabla_curso_seguro}"
            sql_crear_indice_hnsw = f'CREATE INDEX IF NOT EXISTS "{nombre_indice_hnsw}" ON "{nombre_tabla_curso_seguro}" USING hnsw (embedding vector_l2_ops);'
            registrador.info(f"Creando índice HNSW (vector_l2_ops) llamado '{nombre_indice_hnsw}' para tabla '{nombre_tabla_curso_seguro}'.")
            self.cursor.execute(sql_crear_indice_hnsw)

            self._confirmar_transaccion_actual() # Commit para CREATE TABLE e CREATE INDEX
            registrador.info(f"Índice HNSW '{nombre_indice_hnsw}' creado exitosamente para tabla '{nombre_tabla_curso_seguro}'.")
            return True

        except psycopg2.Error as e_db_tabla:
            registrador.error(f"Error de base de datos al asegurar/crear tabla '{nombre_tabla_curso_seguro}': {e_db_tabla}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error al asegurar la tabla del curso '{nombre_tabla_curso_seguro}'.", e_db_tabla, tabla_implicada=nombre_tabla_curso_seguro)
        except Exception as e_inesperado_tabla:
            registrador.exception(f"Error inesperado al asegurar/crear tabla '{nombre_tabla_curso_seguro}': {e_inesperado_tabla}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al asegurar la tabla del curso '{nombre_tabla_curso_seguro}'.", e_inesperado_tabla, tabla_implicada=nombre_tabla_curso_seguro)


    def insertar_o_actualizar_fragmentos_documento(self, identificador_curso: Any, fragmentos_a_guardar: List[modelos_api.FragmentoDocumento]) -> bool:
        """
        Inserta o actualiza (upsert) una lista de fragmentos de documento en la tabla del curso correspondiente.
        Utiliza `execute_values` para una inserción masiva eficiente.
        """
        self._establecer_o_verificar_conexion_db()
        if not fragmentos_a_guardar:
            registrador.info("No hay fragmentos proporcionados para insertar o actualizar.")
            return True # Nada que hacer

        nombre_tabla_curso_seguro = self.obtener_nombre_tabla_curso_normalizado(identificador_curso)

        # Determinar la dimensión del vector del primer fragmento válido para asegurar la tabla.
        # Se asume que todos los fragmentos en una llamada tendrán la misma dimensión.
        dimension_vector_actual = self.config_db.dimension_embedding_defecto # Valor por defecto
        for frag_valido in fragmentos_a_guardar:
            if frag_valido.embedding:
                dimension_vector_actual = len(frag_valido.embedding)
                break

        if not self.asegurar_existencia_tabla_curso(identificador_curso, dimension_vector_actual):
            registrador.error(f"Falló la creación/aseguramiento de la tabla '{nombre_tabla_curso_seguro}' para la inserción/actualización de fragmentos.")
            return False # No se puede continuar si la tabla no está lista

        # Preparar datos para la inserción masiva (execute_values)
        datos_para_upsert_masivo = []
        for fragmento_actual in fragmentos_a_guardar:
            if fragmento_actual.embedding is None: # Omitir fragmentos sin embedding
                registrador.warning(f"Fragmento ID '{fragmento_actual.id_fragmento}' (curso: {fragmento_actual.id_curso}, doc: {fragmento_actual.id_documento}) no tiene embedding. Se omitirá.")
                continue
            # Convertir metadatos (dict) a string JSON si es necesario; psycopg2 puede manejar dicts para JSONB.
            metadatos_para_db = fragmento_actual.metadatos
            if isinstance(fragmento_actual.metadatos, dict):
                metadatos_para_db = json.dumps(fragmento_actual.metadatos) # Convertir a string JSON si es un dict

            datos_para_upsert_masivo.append(
                (fragmento_actual.id_fragmento, str(fragmento_actual.id_curso), fragmento_actual.id_documento, fragmento_actual.texto, metadatos_para_db, fragmento_actual.embedding)
            )

        if not datos_para_upsert_masivo:
            registrador.info(f"No hay fragmentos válidos con embeddings para insertar/actualizar en tabla '{nombre_tabla_curso_seguro}'.")
            return True

        registrador.info(f"Insertando/actualizando {len(datos_para_upsert_masivo)} fragmentos en tabla '{nombre_tabla_curso_seguro}'.")
        try:
            # SQL para inserción masiva con manejo de conflictos (UPSERT en id_fragmento).
            # EXCLUDED hace referencia a los valores que se intentarían insertar si hubiera conflicto.
            sql_plantilla_upsert_masivo = f"""
            INSERT INTO "{nombre_tabla_curso_seguro}" (id_fragmento, id_curso, id_documento, texto, metadatos, embedding)
            VALUES %s
            ON CONFLICT (id_fragmento) DO UPDATE SET
                id_curso = EXCLUDED.id_curso,
                id_documento = EXCLUDED.id_documento,
                texto = EXCLUDED.texto,
                metadatos = EXCLUDED.metadatos,
                embedding = EXCLUDED.embedding;
            """
            execute_values(self.cursor, sql_plantilla_upsert_masivo, datos_para_upsert_masivo, page_size=100) # page_size para optimizar grandes inserciones
            self._confirmar_transaccion_actual()
            registrador.info(f"Se insertaron/actualizaron {len(datos_para_upsert_masivo)} fragmentos exitosamente en tabla '{nombre_tabla_curso_seguro}'.")
            return True
        except psycopg2.Error as e_db_upsert:
            registrador.error(f"Error de base de datos al insertar/actualizar fragmentos en tabla '{nombre_tabla_curso_seguro}': {e_db_upsert}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error al insertar/actualizar fragmentos en '{nombre_tabla_curso_seguro}'.", e_db_upsert, tabla_implicada=nombre_tabla_curso_seguro)
        except Exception as e_inesperado_upsert:
            registrador.exception(f"Error inesperado al insertar/actualizar fragmentos en tabla '{nombre_tabla_curso_seguro}': {e_inesperado_upsert}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al procesar fragmentos para '{nombre_tabla_curso_seguro}'.", e_inesperado_upsert, tabla_implicada=nombre_tabla_curso_seguro)

    def buscar_fragmentos_similares_por_embedding(
        self, identificador_curso: Any, embedding_de_consulta: List[float], limite_resultados: int = 5, factor_ef_search_hnsw: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca fragmentos de texto similares a un embedding de consulta dado, dentro de la tabla del curso.
        Utiliza el operador de distancia L2 (<=>) de pgvector. La "similitud" devuelta es `1 - distancia_L2`.
        """
        self._establecer_o_verificar_conexion_db()
        nombre_tabla_curso_seguro = self.obtener_nombre_tabla_curso_normalizado(identificador_curso)
        registrador.info(f"Buscando {limite_resultados} fragmentos similares en tabla '{nombre_tabla_curso_seguro}' usando distancia L2.")

        try:
            # Opcionalmente, ajustar el parámetro `hnsw.ef_search` para la sesión actual para el índice HNSW.
            # Un valor más alto puede mejorar la precisión (recall) a costa de la velocidad de búsqueda.
            if factor_ef_search_hnsw is not None and factor_ef_search_hnsw > 0:
                self.cursor.execute("SET LOCAL hnsw.ef_search = %s;", (factor_ef_search_hnsw,))
                registrador.debug(f"Parámetro hnsw.ef_search ajustado a {factor_ef_search_hnsw} para esta consulta en tabla '{nombre_tabla_curso_seguro}'.")

            dimension_vector_consulta_actual = len(embedding_de_consulta)
            # Operador '<=>' calcula la distancia L2 (Euclidiana). Menor distancia = más similar.
            # Para obtener una métrica de "similitud" donde mayor es mejor, se puede usar `1 - distancia`.
            # Esto no es similitud coseno, sino una transformación de la distancia L2.
            sql_busqueda_similitud_l2 = f"""
            SELECT id_fragmento, id_curso, id_documento, texto, metadatos, (embedding <=> %s::vector({dimension_vector_consulta_actual})) AS distancia_l2
            FROM "{nombre_tabla_curso_seguro}"
            ORDER BY distancia_l2 ASC
            LIMIT %s;
            """
            # El orden es por distancia_l2 ASC (menor distancia primero).

            self.cursor.execute(sql_busqueda_similitud_l2, (embedding_de_consulta, limite_resultados))
            filas_resultado_consulta = self.cursor.fetchall() # Lista de RealDictRow

            resultados_formateados_finales = []
            for fila_db in filas_resultado_consulta:
                distancia_l2_calculada = fila_db["distancia_l2"]
                # Similitud transformada: 1.0 para distancia 0, disminuye a medida que aumenta la distancia.
                # Puede ser negativa si la distancia L2 es > 1.
                similitud_transformada = 1.0 - distancia_l2_calculada

                metadatos_dict_final = {}
                if fila_db.get("metadatos"): # Metadatos pueden ser None
                    if isinstance(fila_db["metadatos"], str): # Si se almacenó como string JSON
                        try:
                            metadatos_dict_final = json.loads(fila_db["metadatos"])
                        except json.JSONDecodeError:
                            registrador.warning(f"No se pudo decodificar metadatos JSON para fragmento {fila_db['id_fragmento']} en tabla '{nombre_tabla_curso_seguro}': {fila_db['metadatos']}")
                    elif isinstance(fila_db["metadatos"], dict): # Si ya es un dict (JSONB)
                        metadatos_dict_final = fila_db["metadatos"]

                # Construir el payload con la información relevante
                payload_fragmento = {
                    "id_curso": fila_db.get("id_curso"),
                    "id_documento": fila_db.get("id_documento"),
                    "texto": fila_db.get("texto"),
                    **metadatos_dict_final, # Desempaquetar metadatos limpios en el payload
                }

                resultados_formateados_finales.append({
                    "id_fragmento": fila_db["id_fragmento"],
                    "similitud": similitud_transformada, # Similitud (1 - distancia L2)
                    "distancia": distancia_l2_calculada, # Distancia L2 original
                    "payload": payload_fragmento
                })
            registrador.info(f"Búsqueda de similitud en tabla '{nombre_tabla_curso_seguro}' encontró {len(resultados_formateados_finales)} resultados.")
            return resultados_formateados_finales

        except psycopg2.Error as e_db_busqueda:
            registrador.error(f"Error de base de datos al buscar similitudes en tabla '{nombre_tabla_curso_seguro}': {e_db_busqueda}")
            # No se revierte la transacción aquí, ya que es una consulta SELECT y no modifica datos.
            raise ErrorBaseDeDatosVectorial(f"Error al buscar similitudes en '{nombre_tabla_curso_seguro}'.", e_db_busqueda, tabla_implicada=nombre_tabla_curso_seguro)
        except Exception as e_inesperado_busqueda:
            registrador.exception(f"Error inesperado al buscar similitudes en tabla '{nombre_tabla_curso_seguro}': {e_inesperado_busqueda}")
            raise ErrorBaseDeDatosVectorial(f"Error inesperado durante búsqueda de similitud en '{nombre_tabla_curso_seguro}'.", e_inesperado_busqueda, tabla_implicada=nombre_tabla_curso_seguro)


    def eliminar_fragmentos_por_id_documento(self, identificador_curso: Any, id_documento_a_eliminar: str) -> bool:
        """Elimina todos los fragmentos asociados a un ID de documento específico de la tabla del curso."""
        self._establecer_o_verificar_conexion_db()
        nombre_tabla_curso_seguro = self.obtener_nombre_tabla_curso_normalizado(identificador_curso)
        registrador.info(f"Intentando eliminar fragmentos para ID de documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso_seguro}'.")

        try:
            # Verificar primero si la tabla existe para evitar errores si no existe
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_curso_seguro}');")
            if not (resultado_existencia_tabla := self.cursor.fetchone()) or not resultado_existencia_tabla["exists"]:
                registrador.warning(f"Tabla '{nombre_tabla_curso_seguro}' no existe. No se pueden eliminar fragmentos para documento ID '{id_documento_a_eliminar}'. Se considera operación exitosa (nada que eliminar).")
                return True # Si la tabla no existe, no hay nada que eliminar.

            sql_eliminar_fragmentos_por_doc = f'DELETE FROM "{nombre_tabla_curso_seguro}" WHERE id_documento = %s;'
            self.cursor.execute(sql_eliminar_fragmentos_por_doc, (id_documento_a_eliminar,))
            filas_afectadas_por_delete = self.cursor.rowcount # Número de filas eliminadas
            self._confirmar_transaccion_actual()

            registrador.info(f"Se eliminaron {filas_afectadas_por_delete} fragmentos para el ID de documento '{id_documento_a_eliminar}' de la tabla '{nombre_tabla_curso_seguro}'.")
            return True
        except psycopg2.Error as e_db_delete:
            registrador.error(f"Error de base de datos al eliminar fragmentos para ID de documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso_seguro}': {e_db_delete}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error al eliminar fragmentos del documento '{id_documento_a_eliminar}'.", e_db_delete, tabla_implicada=nombre_tabla_curso_seguro)
        except Exception as e_inesperado_delete:
            registrador.exception(f"Error inesperado al eliminar fragmentos del documento '{id_documento_a_eliminar}' de tabla '{nombre_tabla_curso_seguro}': {e_inesperado_delete}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al eliminar fragmentos del documento '{id_documento_a_eliminar}'.", e_inesperado_delete, tabla_implicada=nombre_tabla_curso_seguro)

    # --- Métodos para seguimiento de archivos procesados ---

    def _asegurar_existencia_tabla_seguimiento_archivos(self):
        """
        Asegura que la tabla para el seguimiento de archivos procesados exista en la BD.
        Esta función es llamada internamente por `_establecer_o_verificar_conexion_db`,
        por lo que la conexión y el cursor ya deberían estar activos y disponibles.
        """
        if not self._conexion_activa_db or not self._cursor_activo_db or self._conexion_activa_db.closed or self._cursor_activo_db.closed:
             registrador.critical("No hay conexión a BD o cursor disponible para asegurar la tabla de seguimiento. Esto indica un problema en la lógica de conexión interna.")
             raise ErrorBaseDeDatosVectorial("Conexión o cursor no disponible para asegurar tabla de seguimiento de archivos.")

        nombre_tabla_fijo_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS
        registrador.debug(f"Asegurando existencia de tabla de seguimiento de archivos: '{nombre_tabla_fijo_seguimiento}'.")
        try:
            # Verificar si la tabla ya existe
            self.cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{nombre_tabla_fijo_seguimiento}');")
            if (resultado_existencia_seguimiento := self.cursor.fetchone()) and resultado_existencia_seguimiento["exists"]:
                registrador.debug(f"Tabla de seguimiento '{nombre_tabla_fijo_seguimiento}' ya existe.")
                return # La tabla ya existe

            registrador.info(f"Tabla de seguimiento '{nombre_tabla_fijo_seguimiento}' no existe. Creando tabla...")
            sql_crear_tabla_fijo_seguimiento = f"""
            CREATE TABLE IF NOT EXISTS "{nombre_tabla_fijo_seguimiento}" (
                id_curso INTEGER NOT NULL,
                identificador_archivo TEXT NOT NULL, -- Podría ser un ID de Moodle, un hash de contenido, o un path único
                tiempo_modificacion_moodle BIGINT NOT NULL, -- Timestamp Unix de Moodle (o del archivo)
                procesado_en BIGINT NOT NULL, -- Timestamp Unix de cuándo fue procesado por EntrenAI
                PRIMARY KEY (id_curso, identificador_archivo) -- Clave primaria compuesta
            );
            """
            self.cursor.execute(sql_crear_tabla_fijo_seguimiento)
            self._confirmar_transaccion_actual() # Importante hacer commit después de CREATE TABLE
            registrador.info(f"Tabla de seguimiento de archivos '{nombre_tabla_fijo_seguimiento}' creada exitosamente.")
        except psycopg2.Error as e_db_seguimiento:
            registrador.error(f"Error de base de datos al asegurar la tabla de seguimiento '{nombre_tabla_fijo_seguimiento}': {e_db_seguimiento}")
            self._revertir_transaccion_actual() # Revertir si la creación falla
            raise ErrorBaseDeDatosVectorial(f"Error al asegurar tabla de seguimiento de archivos '{nombre_tabla_fijo_seguimiento}'.", e_db_seguimiento, tabla_implicada=nombre_tabla_fijo_seguimiento)
        except Exception as e_inesperado_seguimiento:
            registrador.exception(f"Error inesperado al asegurar la tabla de seguimiento '{nombre_tabla_fijo_seguimiento}': {e_inesperado_seguimiento}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado al asegurar tabla de seguimiento '{nombre_tabla_fijo_seguimiento}'.", e_inesperado_seguimiento, tabla_implicada=nombre_tabla_fijo_seguimiento)


    def obtener_marcas_de_tiempo_archivos_procesados_curso(self, id_curso: int) -> Dict[str, int]:
        """
        Obtiene un diccionario de {identificador_archivo: tiempo_modificacion_moodle}
        para todos los archivos procesados registrados para un curso específico.
        """
        self._establecer_o_verificar_conexion_db()
        nombre_tabla_fijo_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS
        registrador.debug(f"Obteniendo marcas de tiempo de archivos procesados para curso ID {id_curso} desde tabla '{nombre_tabla_fijo_seguimiento}'.")
        try:
            sql_consulta_marcas_tiempo = f'SELECT identificador_archivo, tiempo_modificacion_moodle FROM "{nombre_tabla_fijo_seguimiento}" WHERE id_curso = %s;'
            self.cursor.execute(sql_consulta_marcas_tiempo, (id_curso,))
            archivos_procesados_curso = {fila_resultado["identificador_archivo"]: fila_resultado["tiempo_modificacion_moodle"] for fila_resultado in self.cursor.fetchall()}
            registrador.info(f"Se encontraron {len(archivos_procesados_curso)} registros de archivos procesados para el curso ID {id_curso}.")
            return archivos_procesados_curso
        except psycopg2.Error as e_db_marcas:
            registrador.error(f"Error de base de datos al obtener marcas de tiempo para curso ID '{id_curso}': {e_db_marcas}")
            raise ErrorBaseDeDatosVectorial(f"Error al obtener marcas de tiempo para curso {id_curso}.", e_db_marcas, tabla_implicada=nombre_tabla_fijo_seguimiento)
        except Exception as e_inesperado_marcas:
            registrador.exception(f"Error inesperado al obtener marcas de tiempo para curso ID '{id_curso}': {e_inesperado_marcas}")
            raise ErrorBaseDeDatosVectorial(f"Error inesperado obteniendo marcas de tiempo para curso {id_curso}.", e_inesperado_marcas, tabla_implicada=nombre_tabla_fijo_seguimiento)

    def verificar_si_archivo_es_nuevo_o_modificado(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_actual_moodle: int) -> bool:
        """
        Comprueba si un archivo es nuevo (no está en seguimiento) o ha sido modificado
        (su `tiempo_modificacion_moodle` actual es mayor que el registrado).
        """
        self._establecer_o_verificar_conexion_db()
        nombre_tabla_fijo_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS
        registrador.debug(f"Verificando estado del archivo '{identificador_archivo}' (curso ID {id_curso}) con timestamp Moodle actual {tiempo_modificacion_actual_moodle} en tabla '{nombre_tabla_fijo_seguimiento}'.")
        try:
            sql_consulta_archivo_seguimiento = f'SELECT tiempo_modificacion_moodle FROM "{nombre_tabla_fijo_seguimiento}" WHERE id_curso = %s AND identificador_archivo = %s;'
            self.cursor.execute(sql_consulta_archivo_seguimiento, (id_curso, identificador_archivo))
            resultado_archivo_db = self.cursor.fetchone() # Debería ser único por PK

            if resultado_archivo_db is None:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) no encontrado en tabla de seguimiento. Se considera NUEVO.")
                return True # Archivo no encontrado, por lo tanto es nuevo.

            tiempo_modificacion_registrado_db = resultado_archivo_db["tiempo_modificacion_moodle"]
            if tiempo_modificacion_actual_moodle > tiempo_modificacion_registrado_db:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) ha sido MODIFICADO (Moodle: {tiempo_modificacion_actual_moodle} > DB: {tiempo_modificacion_registrado_db}).")
                return True # Archivo modificado (timestamp más reciente en Moodle).
            else:
                registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) NO ha cambiado (Moodle: {tiempo_modificacion_actual_moodle} <= DB: {tiempo_modificacion_registrado_db}).")
                return False # Archivo no modificado.

        except psycopg2.Error as e_db_verificar:
            registrador.error(f"Error de BD al verificar estado de archivo '{identificador_archivo}' (curso {id_curso}): {e_db_verificar}")
            # En caso de error de BD, es más seguro asumir que el archivo necesita (re)procesamiento.
            return True
        except Exception as e_inesperado_verificar:
            registrador.exception(f"Error inesperado al verificar estado de archivo '{identificador_archivo}' (curso {id_curso}): {e_inesperado_verificar}")
            return True # Asumir que necesita reprocesamiento por seguridad


    def marcar_archivo_como_procesado_en_seguimiento(self, id_curso: int, identificador_archivo: str, tiempo_modificacion_moodle: int) -> bool:
        """
        Registra o actualiza un archivo en la tabla de seguimiento, marcándolo como procesado
        con el `tiempo_modificacion_moodle` actual y el timestamp de procesamiento actual.
        """
        self._establecer_o_verificar_conexion_db()
        timestamp_unix_procesamiento_actual = int(time.time()) # Timestamp Unix actual
        nombre_tabla_fijo_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS
        registrador.info(f"Marcando archivo '{identificador_archivo}' (curso ID {id_curso}, ts Moodle: {tiempo_modificacion_moodle}) como procesado en tabla '{nombre_tabla_fijo_seguimiento}' con ts_procesado {timestamp_unix_procesamiento_actual}.")

        try:
            sql_upsert_seguimiento_archivo = f"""
            INSERT INTO "{nombre_tabla_fijo_seguimiento}" (id_curso, identificador_archivo, tiempo_modificacion_moodle, procesado_en)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_curso, identificador_archivo) DO UPDATE SET
                tiempo_modificacion_moodle = EXCLUDED.tiempo_modificacion_moodle,
                procesado_en = EXCLUDED.procesado_en;
            """
            self.cursor.execute(sql_upsert_seguimiento_archivo, (id_curso, identificador_archivo, tiempo_modificacion_moodle, timestamp_unix_procesamiento_actual))
            self._confirmar_transaccion_actual()
            registrador.info(f"Archivo '{identificador_archivo}' (curso {id_curso}) marcado como procesado exitosamente en tabla de seguimiento.")
            return True
        except psycopg2.Error as e_db_marcar:
            registrador.error(f"Error de BD al marcar archivo '{identificador_archivo}' (curso {id_curso}) como procesado: {e_db_marcar}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error al marcar archivo '{identificador_archivo}' como procesado.", e_db_marcar, tabla_implicada=nombre_tabla_fijo_seguimiento)
        except Exception as e_inesperado_marcar:
            registrador.exception(f"Error inesperado al marcar archivo '{identificador_archivo}' (curso {id_curso}) como procesado: {e_inesperado_marcar}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado marcando archivo '{identificador_archivo}' como procesado.", e_inesperado_marcar, tabla_implicada=nombre_tabla_fijo_seguimiento)

    def eliminar_registro_de_archivo_en_seguimiento(self, id_curso: int, identificador_archivo: str) -> bool:
        """
        Elimina un archivo de la tabla de seguimiento. Esto podría usarse si un archivo
        es eliminado de la fuente (ej. Moodle) y ya no debe considerarse para procesamiento.
        """
        self._establecer_o_verificar_conexion_db()
        nombre_tabla_fijo_seguimiento = self._NOMBRE_TABLA_SEGUIMIENTO_ARCHIVOS_PROCESADOS
        registrador.info(f"Eliminando seguimiento para archivo '{identificador_archivo}' (curso ID {id_curso}) de tabla '{nombre_tabla_fijo_seguimiento}'.")

        try:
            sql_eliminar_seguimiento_archivo = f'DELETE FROM "{nombre_tabla_fijo_seguimiento}" WHERE id_curso = %s AND identificador_archivo = %s;'
            self.cursor.execute(sql_eliminar_seguimiento_archivo, (id_curso, identificador_archivo))
            filas_afectadas_delete_seguimiento = self.cursor.rowcount
            self._confirmar_transaccion_actual()

            if filas_afectadas_delete_seguimiento > 0:
                registrador.info(f"Registro de seguimiento para archivo '{identificador_archivo}' (curso {id_curso}) eliminado. Filas afectadas: {filas_afectadas_delete_seguimiento}.")
            else:
                registrador.info(f"No se encontró registro de seguimiento para eliminar para archivo '{identificador_archivo}' (curso {id_curso}). Ninguna fila afectada.")
            return True # Operación exitosa incluso si no había nada que eliminar.
        except psycopg2.Error as e_db_eliminar_seguimiento:
            registrador.error(f"Error de BD al eliminar seguimiento para archivo '{identificador_archivo}' (curso {id_curso}): {e_db_eliminar_seguimiento}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error al eliminar registro de seguimiento del archivo '{identificador_archivo}'.", e_db_eliminar_seguimiento, tabla_implicada=nombre_tabla_fijo_seguimiento)
        except Exception as e_inesperado_eliminar_seguimiento:
            registrador.exception(f"Error inesperado al eliminar seguimiento para archivo '{identificador_archivo}' (curso {id_curso}): {e_inesperado_eliminar_seguimiento}")
            self._revertir_transaccion_actual()
            raise ErrorBaseDeDatosVectorial(f"Error inesperado eliminando registro de seguimiento del archivo '{identificador_archivo}'.", e_inesperado_eliminar_seguimiento, tabla_implicada=nombre_tabla_fijo_seguimiento)

    def _cerrar_conexion_db_interna(self):
        """Cierra el cursor y la conexión a la base de datos si están abiertos. Usado internamente."""
        if self._cursor_activo_db and not self._cursor_activo_db.closed:
            try:
                self._cursor_activo_db.close()
                registrador.debug("Cursor de base de datos cerrado internamente.")
            except psycopg2.Error as e_cerrar_cursor:
                registrador.warning(f"Error al cerrar el cursor de la BD: {e_cerrar_cursor}")
        self._cursor_activo_db = None # Asegurar que se limpie la referencia

        if self._conexion_activa_db and not self._conexion_activa_db.closed:
            try:
                self._conexion_activa_db.close()
                registrador.debug("Conexión a base de datos cerrada internamente.")
            except psycopg2.Error as e_cerrar_conexion:
                registrador.warning(f"Error al cerrar la conexión a la BD: {e_cerrar_conexion}")
        self._conexion_activa_db = None # Asegurar que se limpie la referencia

    def cerrar_conexion_a_db(self):
        """Método público para cerrar explícitamente la conexión a la base de datos."""
        registrador.info("Solicitud explícita para cerrar conexión a la base de datos.")
        self._cerrar_conexion_db_interna()

    def __del__(self):
        """Destructor para asegurar el cierre de la conexión al eliminar el objeto EnvoltorioPgVector."""
        registrador.debug(f"Destructor de EnvoltorioPgVector ({id(self)}) llamado. Cerrando conexión a BD si está activa.")
        self._cerrar_conexion_db_interna()

[end of entrenai_refactor/nucleo/bd/envoltorio_pgvector.py]
