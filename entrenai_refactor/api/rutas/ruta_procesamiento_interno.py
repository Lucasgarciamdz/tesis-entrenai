import os # Para operaciones del sistema de archivos como eliminar archivos temporales
import traceback # Para el logging detallado de errores fatales en tareas de fondo
from pathlib import Path
from typing import List, Optional, Dict, Any # Tipos estándar, no se usan todos directamente aquí pero son comunes

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status

# Importar modelos Pydantic refactorizados
from entrenai_refactor.api import modelos as modelos_api
# Importar clases refactorizadas del núcleo de la aplicación
from entrenai_refactor.nucleo.clientes import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import (
    ProveedorInteligencia, ErrorProveedorInteligencia,
    GestorEmbeddings, ErrorGestorEmbeddings # Asumiendo que ErrorGestorEmbeddings existe y es relevante
)
from entrenai_refactor.nucleo.archivos import (
    GestorMaestroDeProcesadoresArchivos, ErrorProcesamientoArchivo, ErrorDependenciaFaltante
)
# Configuración global y sistema de logging
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__) # Registrador para este módulo

# Enrutador para endpoints de procesamiento interno, usualmente llamados por tareas asíncronas (Celery)
enrutador_procesamiento_interno = APIRouter(
    prefix="/v1/sistema/procesamiento-interno", # Prefijo para estos endpoints
    tags=["Sistema - Procesamiento Interno y Tareas Asíncronas"], # Etiqueta para OpenAPI
    # Se podría añadir 'include_in_schema=False' si estos endpoints no deben ser expuestos directamente
    # en la documentación de Swagger UI dirigida a usuarios finales.
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---
# NOTA: Estas funciones son muy similares a las de 'ruta_configuracion_curso.py'.
# En una aplicación más grande, se recomienda centralizarlas en un módulo de dependencias común
# para evitar duplicación y facilitar el mantenimiento. Se mantienen aquí con sufijos
# '_proc_interno' para distinguirlas en logs si fuera necesario, pero podrían ser las mismas.

def obtener_dependencia_cliente_moodle_pi() -> ClienteMoodle: # Sufijo _pi para "procesamiento interno"
    """Dependencia para obtener una instancia del ClienteMoodle para este enrutador."""
    try:
        return ClienteMoodle()
    except ErrorAPIMoodle as e_moodle:
        registrador.error(f"Error específico al crear instancia de ClienteMoodle (procesamiento interno): {e_moodle}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con Moodle para procesamiento interno: {str(e_moodle)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteMoodle (procesamiento interno): {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar la conexión con Moodle para procesamiento interno.")

def obtener_dependencia_envoltorio_pgvector_pi() -> EnvoltorioPgVector:
    """Dependencia para obtener una instancia del EnvoltorioPgVector para este enrutador."""
    try:
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error específico al crear instancia de EnvoltorioPgVector (procesamiento interno): {e_bd_vec}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial para procesamiento interno: {str(e_bd_vec)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de EnvoltorioPgVector (procesamiento interno): {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar el acceso a la base de datos vectorial para procesamiento interno.")

def obtener_dependencia_proveedor_inteligencia_pi() -> ProveedorInteligencia:
    """Dependencia para obtener una instancia del ProveedorInteligencia para este enrutador."""
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_prov_ia:
        registrador.error(f"Error específico al crear instancia de ProveedorInteligencia (procesamiento interno): {e_prov_ia}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA configurado para procesamiento interno: {str(e_prov_ia)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ProveedorInteligencia (procesamiento interno): {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al configurar el proveedor de IA para procesamiento interno.")

def obtener_dependencia_gestor_embeddings_pi( # Nombre de función refactorizado
    proveedor_ia: ProveedorInteligencia = Depends(obtener_dependencia_proveedor_inteligencia_pi) # Dependencia anidada
) -> GestorEmbeddings:
    """Dependencia para obtener una instancia del GestorEmbeddings."""
    try:
        return GestorEmbeddings(proveedor_ia=proveedor_ia) # Parámetro 'proveedor_ia' refactorizado
    except ErrorGestorEmbeddings as e_gestor_emb: # Asumiendo que GestorEmbeddings puede lanzar su propia excepción
        registrador.error(f"Error específico al crear instancia de GestorEmbeddings (procesamiento interno): {e_gestor_emb}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de embeddings para procesamiento interno: {str(e_gestor_emb)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de GestorEmbeddings (procesamiento interno): {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno del servidor al configurar el gestor de embeddings para procesamiento interno: {str(e_inesperado)}")

def obtener_dependencia_gestor_procesadores_archivos_pi() -> GestorMaestroDeProcesadoresArchivos: # Nombre de función refactorizado
    """Dependencia para obtener una instancia del GestorMaestroDeProcesadoresArchivos."""
    try:
        return GestorMaestroDeProcesadoresArchivos() # Nombre de clase refactorizado
    except Exception as e_inesperado: # GestorMaestroDeProcesadoresArchivos podría no tener errores complejos de inicialización
        registrador.exception(f"Error inesperado al crear instancia de GestorMaestroDeProcesadoresArchivos (procesamiento interno): {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de procesadores de archivos para procesamiento interno: {str(e_inesperado)}")


# --- Lógica Central de Procesamiento de Archivos de un Curso (Tarea Asíncrona) ---

async def _ejecutar_tarea_procesamiento_archivos_curso( # Nombre de función refactorizado
    id_curso_para_procesar: int, # Parámetro renombrado
    id_usuario_que_solicita: int, # Parámetro renombrado (para auditoría o lógica futura, no usado activamente aquí)
    cliente_moodle: ClienteMoodle,
    envoltorio_bd: EnvoltorioPgVector, # Parámetro renombrado
    proveedor_ia: ProveedorInteligencia,
    gestor_embeddings: GestorEmbeddings,
    gestor_archivos: GestorMaestroDeProcesadoresArchivos # Parámetro renombrado
):
    """
    Tarea principal, usualmente ejecutada en segundo plano (ej. por Celery o BackgroundTasks de FastAPI),
    para procesar todos los archivos relevantes de un curso. Esto incluye:
    1. Obtener el nombre del curso para usarlo en identificadores (ej. nombre de tabla vectorial).
    2. Localizar la sección y carpeta designada en Moodle para los archivos de EntrenAI.
    3. Listar los archivos en dicha carpeta.
    4. Para cada archivo:
        a. Verificar si es nuevo o ha sido modificado desde el último procesamiento.
        b. Si es nuevo/modificado: descargar, extraer texto, formatear a Markdown (opcional),
           generar embeddings para sus fragmentos, e insertar/actualizar en la BD vectorial.
        c. Marcar el archivo como procesado en la tabla de seguimiento.
    5. Registrar un resumen del proceso.
    """
    registrador.info(f"Inicio de procesamiento de archivos (tarea asíncrona/interna) para el curso ID: {id_curso_para_procesar}, solicitado por usuario ID: {id_usuario_que_solicita}.")
    try:
        # Paso 1: Obtener nombre del curso. Este nombre se usa para la tabla vectorial.
        nombre_curso_para_tabla_bd: Optional[str] = None
        try:
            # Similar a _aux_obtener_nombre_curso en ruta_configuracion_curso.py, pero adaptado.
            # Asumimos que el id_usuario_que_solicita podría ser relevante para filtrar cursos.
            cursos_del_usuario_solicitante = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_usuario_que_solicita)
            curso_objeto_moodle = next((c for c in cursos_del_usuario_solicitante if c.id == id_curso_para_procesar), None)
            if curso_objeto_moodle:
                nombre_curso_para_tabla_bd = curso_objeto_moodle.nombre_a_mostrar or curso_objeto_moodle.nombre_completo
            else: # Fallback: buscar en todos los cursos si no se encontró en los del usuario.
                todos_los_cursos_moodle_instancia = cliente_moodle.obtener_todos_los_cursos_disponibles()
                curso_objeto_moodle_todos = next((c for c in todos_los_cursos_moodle_instancia if c.id == id_curso_para_procesar), None)
                if curso_objeto_moodle_todos:
                    nombre_curso_para_tabla_bd = curso_objeto_moodle_todos.nombre_a_mostrar or curso_objeto_moodle_todos.nombre_completo

            if not nombre_curso_para_tabla_bd: # Si aún no se encuentra, usar un nombre genérico basado en ID.
                nombre_curso_para_tabla_bd = f"curso_{id_curso_para_procesar}" # Nombre de fallback
                registrador.warning(f"No se pudo obtener el nombre del curso {id_curso_para_procesar} desde Moodle. Se usará el nombre genérico '{nombre_curso_para_tabla_bd}' para la tabla vectorial y otros identificadores.")
        except ErrorAPIMoodle as e_moodle_api_nombre:
            registrador.error(f"Error de API Moodle al obtener el nombre del curso {id_curso_para_procesar} para el procesamiento de archivos: {e_moodle_api_nombre}. Se usará un nombre genérico para la tabla.")
            nombre_curso_para_tabla_bd = f"curso_{id_curso_para_procesar}" # Fallback si la API de Moodle falla

        # Paso 2: Identificar la sección y carpeta de EntrenAI en Moodle donde residen los documentos.
        nombre_seccion_entrenai_configurada = configuracion_global.moodle.nombre_carpeta_recursos_ia # Nombre de la SECCIÓN, campo refactorizado
        # Asumimos que el nombre de la CARPETA dentro de esa sección es el mismo que el de la sección.
        nombre_carpeta_documentos_curso = nombre_seccion_entrenai_configurada

        seccion_entrenai_en_moodle = cliente_moodle.obtener_seccion_por_nombre(id_curso_para_procesar, nombre_seccion_entrenai_configurada)
        if not seccion_entrenai_en_moodle or not seccion_entrenai_en_moodle.id: # Asegurar que la sección y su ID existan
            registrador.warning(f"No se encontró la sección configurada '{nombre_seccion_entrenai_configurada}' en el curso {id_curso_para_procesar}. No se pueden procesar archivos de esta fuente.")
            return # Terminar la tarea si la sección principal de EntrenAI no existe en el curso.

        # Obtener el módulo de tipo 'folder' (carpeta) usando su nombre dentro de la sección encontrada.
        modulo_carpeta_recursos_ia = cliente_moodle.obtener_modulo_de_curso_por_nombre(id_curso_para_procesar, seccion_entrenai_en_moodle.id, nombre_carpeta_documentos_curso, "folder")
        if not modulo_carpeta_recursos_ia or not modulo_carpeta_recursos_ia.id: # El 'id' aquí es el 'cmid' (ID del módulo de curso)
            registrador.warning(f"No se encontró la carpeta de documentos '{nombre_carpeta_documentos_curso}' en la sección '{nombre_seccion_entrenai_configurada}' del curso {id_curso_para_procesar}. No hay archivos para procesar.")
            return

        # Paso 3: Obtener la lista de archivos contenidos en la carpeta de Moodle.
        lista_archivos_en_carpeta_moodle = cliente_moodle.obtener_archivos_de_carpeta(modulo_carpeta_recursos_ia.id) # Se usa el ID del módulo (cmid)
        if not lista_archivos_en_carpeta_moodle:
            registrador.info(f"No se encontraron archivos en la carpeta '{nombre_carpeta_documentos_curso}' (módulo ID {modulo_carpeta_recursos_ia.id}) para el curso {id_curso_para_procesar}. Nada que procesar en esta ejecución.")
            return

        registrador.info(f"Se encontraron {len(lista_archivos_en_carpeta_moodle)} archivos en la carpeta de Moodle para el curso {id_curso_para_procesar}. Iniciando bucle de procesamiento individual de archivos.")

        # Paso 4: Iterar sobre cada archivo encontrado y procesarlo individualmente.
        contador_archivos_procesados_correctamente = 0
        contador_archivos_omitidos_por_no_cambios = 0

        # Crear directorios para descargas y archivos Markdown generados, si no existen.
        directorio_descargas_especifico_curso = Path(configuracion_global.ruta_absoluta_directorio_descargas) / str(id_curso_para_procesar)
        directorio_descargas_especifico_curso.mkdir(parents=True, exist_ok=True)
        directorio_markdown_especifico_curso = Path(configuracion_global.ruta_absoluta_directorio_datos) / "markdown_cursos" / str(id_curso_para_procesar)
        directorio_markdown_especifico_curso.mkdir(parents=True, exist_ok=True)

        for archivo_moodle_a_procesar in lista_archivos_en_carpeta_moodle:
            # Usar 'nombre_original_archivo' como identificador único dentro del contexto del curso.
            # Podría mejorarse usando 'ruta_relativa_archivo' si los nombres no son únicos globalmente en la carpeta.
            identificador_unico_del_archivo = archivo_moodle_a_procesar.nombre_original_archivo # Campo refactorizado
            timestamp_modificacion_archivo_moodle = archivo_moodle_a_procesar.timestamp_ultima_modificacion # Campo refactorizado

            registrador.debug(f"Evaluando archivo: '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}), última modificación en Moodle: {timestamp_modificacion_archivo_moodle}.")

            # Verificar si el archivo es nuevo o ha sido modificado desde el último procesamiento registrado.
            if envoltorio_bd.verificar_si_archivo_es_nuevo_o_modificado(id_curso_para_procesar, identificador_unico_del_archivo, timestamp_modificacion_archivo_moodle): # Método refactorizado
                registrador.info(f"Procesando archivo nuevo o modificado: '{identificador_unico_del_archivo}' para el curso ID: {id_curso_para_procesar}.")
                ruta_archivo_descargado_localmente: Optional[Path] = None # Para control en bloque finally
                try:
                    # Descargar el archivo desde Moodle.
                    ruta_archivo_descargado_localmente = cliente_moodle.descargar_archivo_moodle( # Método refactorizado
                        url_archivo_moodle_original=str(archivo_moodle_a_procesar.url_descarga_directa_archivo), # Campo refactorizado
                        directorio_destino_descarga=directorio_descargas_especifico_curso,
                        nombre_final_archivo=archivo_moodle_a_procesar.nombre_original_archivo # Campo refactorizado
                    )
                    registrador.info(f"Archivo '{identificador_unico_del_archivo}' descargado en: {ruta_archivo_descargado_localmente}.")

                    # Extraer texto del archivo descargado usando el gestor de procesadores.
                    texto_contenido_extraido_archivo = gestor_archivos.procesar_archivo_segun_tipo(ruta_archivo_descargado_localmente) # Método refactorizado

                    if texto_contenido_extraido_archivo and texto_contenido_extraido_archivo.strip(): # Si se extrajo texto y no está vacío
                        # Opcional: Formatear el texto extraído a Markdown (si es necesario o deseado).
                        # La decisión de formatear a Markdown aquí o delegarlo puede depender de la estrategia general.
                        # Por ahora, asumimos que el proveedor de IA puede manejar texto crudo o que el formateo es beneficioso.
                        ruta_archivo_markdown_generado = directorio_markdown_especifico_curso / f"{ruta_archivo_descargado_localmente.stem}.md"
                        texto_contenido_en_markdown = proveedor_ia.formatear_texto_a_markdown( # Método refactorizado
                            texto_original=texto_contenido_extraido_archivo,
                            ruta_archivo_para_guardar=ruta_archivo_markdown_generado
                        )

                        # Dividir el texto (Markdown o crudo) en fragmentos manejables para embeddings.
                        lista_fragmentos_de_texto = gestor_embeddings.dividir_texto_en_fragmentos(texto_contenido_en_markdown) # Método refactorizado

                        # Generar embeddings para cada fragmento.
                        # Aquí se aplica la contextualización dentro de generar_embeddings_para_lista_de_textos.
                        lista_embeddings_generados_fragmentos = gestor_embeddings.generar_embeddings_para_lista_de_textos( # Método refactorizado
                            lista_de_textos=lista_fragmentos_de_texto,
                            nombre_archivo_origen=archivo_moodle_a_procesar.nombre_original_archivo, # Para contexto
                            titulo_documento_origen=archivo_moodle_a_procesar.nombre_original_archivo # Usar nombre como título por defecto
                        )

                        # Preparar objetos Pydantic para la inserción en la base de datos.
                        lista_objetos_fragmento_para_bd = gestor_embeddings.construir_objetos_fragmento_para_bd( # Método refactorizado
                            id_curso=id_curso_para_procesar, # Campo refactorizado
                            id_documento=identificador_unico_del_archivo,
                            nombre_archivo_original=archivo_moodle_a_procesar.nombre_original_archivo, # Campo refactorizado
                            titulo_documento=archivo_moodle_a_procesar.nombre_original_archivo, # Título para metadatos
                            lista_textos_fragmentos=lista_fragmentos_de_texto,
                            lista_embeddings_fragmentos=lista_embeddings_generados_fragmentos
                        )

                        # Insertar o actualizar los fragmentos y sus embeddings en la base de datos vectorial (PGVector).
                        envoltorio_bd.insertar_o_actualizar_fragmentos_documento( # Método refactorizado
                            identificador_curso=nombre_curso_para_tabla_bd, # Usar el nombre del curso para la tabla
                            fragmentos_a_guardar=lista_objetos_fragmento_para_bd # Parámetro refactorizado
                        )
                        registrador.info(f"Archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}) procesado: texto extraído, formateado (opcional), fragmentado y embeddings almacenados en BD.")
                    else:
                        registrador.warning(f"No se extrajo contenido textual del archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}) o el contenido estaba vacío. No se generarán embeddings para este archivo.")

                    # Marcar el archivo como procesado en la tabla de seguimiento, independientemente de si se extrajo texto
                    # (para no reintentar procesar archivos vacíos o no soportados repetidamente).
                    envoltorio_bd.marcar_archivo_como_procesado_en_seguimiento(id_curso_para_procesar, identificador_unico_del_archivo, timestamp_modificacion_archivo_moodle) # Método refactorizado
                    contador_archivos_procesados_correctamente += 1

                # Captura de excepciones específicas del flujo de procesamiento de un archivo
                except ErrorDependenciaFaltante as e_error_dependencia_archivo:
                    registrador.error(f"Dependencia faltante para procesar el archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}): {e_error_dependencia_archivo}. Se omite este archivo.")
                except ErrorProcesamientoArchivo as e_error_procesamiento_archivo:
                    registrador.error(f"Error específico de procesamiento para el archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}): {e_error_procesamiento_archivo}. Se omite este archivo.")
                except ErrorAPIMoodle as e_error_api_moodle_descarga: # Error al descargar archivo de Moodle
                     registrador.error(f"Error de API Moodle al descargar el archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}): {e_error_api_moodle_descarga}. Se omite este archivo.")
                except (ErrorProveedorInteligencia, ErrorGestorEmbeddings, ErrorBaseDeDatosVectorial) as e_error_nucleo_ia_bd: # Errores de IA o BD
                    registrador.error(f"Error del núcleo de IA o Base de Datos al procesar el archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}): {e_error_nucleo_ia_bd}. Se omite este archivo.")
                except Exception as e_error_general_procesamiento_archivo: # Capturar cualquier otro error inesperado para un archivo
                    registrador.exception(f"Error general inesperado al procesar el archivo '{identificador_unico_del_archivo}' (curso {id_curso_para_procesar}): {e_error_general_procesamiento_archivo}. Se omite este archivo.")
                finally:
                    # Limpiar el archivo local descargado después de procesarlo (o intentarlo), para no ocupar espacio.
                    if ruta_archivo_descargado_localmente and ruta_archivo_descargado_localmente.exists():
                        try:
                            os.remove(ruta_archivo_descargado_localmente)
                            registrador.debug(f"Archivo local temporal '{ruta_archivo_descargado_localmente}' eliminado tras procesamiento.")
                        except OSError as e_error_os_remove: # Error al eliminar el archivo temporal
                            registrador.error(f"No se pudo eliminar el archivo local temporal '{ruta_archivo_descargado_localmente}': {e_error_os_remove}")
                    # Considerar si se debe mantener el archivo Markdown generado en 'directorio_markdown_especifico_curso' o eliminarlo también.
                    # Por ahora, se mantiene.
            else: # El archivo no es nuevo ni ha sido modificado
                registrador.info(f"El archivo '{identificador_unico_del_archivo}' del curso {id_curso_para_procesar} no ha sido modificado desde el último procesamiento registrado. Se omite en esta ejecución.")
                contador_archivos_omitidos_por_no_cambios +=1

        registrador.info(
            f"Procesamiento de archivos (tarea asíncrona/interna) para el curso ID: {id_curso_para_procesar} finalizado. "
            f"Archivos procesados/actualizados con éxito en esta ejecución: {contador_archivos_procesados_correctamente}. "
            f"Archivos omitidos por no presentar cambios: {contador_archivos_omitidos_por_no_cambios}."
        )

    except Exception as e_error_fatal_tarea_curso: # Error muy general que impide iniciar o continuar el procesamiento del curso
        # Este es un error a nivel de la tarea completa para el curso, no de un archivo individual.
        registrador.error(f"Error fatal durante la ejecución de la tarea de procesamiento de archivos para el curso {id_curso_para_procesar}: {e_error_fatal_tarea_curso}")
        registrador.error(traceback.format_exc()) # Loguear el traceback completo para depuración de errores fatales.
        # Aquí se podría notificar a un sistema de monitoreo o reintentar la tarea si la infraestructura lo permite.


@enrutador_procesamiento_interno.post("/curso/procesar-archivos-en-segundo-plano", # Ruta en español
                                      summary="Disparador para Procesamiento Asíncrono de Archivos de un Curso (Llamado por Celery)",
                                      description="Este endpoint está diseñado para ser llamado por una tarea Celery. Recibe los IDs necesarios e invoca la lógica de procesamiento de archivos del curso en una tarea de fondo de FastAPI para liberar rápidamente al worker de Celery.")
async def disparar_procesamiento_archivos_curso_en_segundo_plano( # Nombre de función refactorizado
    solicitud_desde_celery: modelos_api.SolicitudProcesamientoArchivosDeCurso, # Modelo Pydantic refactorizado
    tareas_en_segundo_plano_fastapi: BackgroundTasks, # Mecanismo de FastAPI para tareas de fondo
    # Inyección de dependencias para ser pasadas a la tarea de fondo de FastAPI
    cliente_moodle: ClienteMoodle = Depends(obtener_dependencia_cliente_moodle_pi),
    envoltorio_bd: EnvoltorioPgVector = Depends(obtener_dependencia_envoltorio_pgvector_pi),
    proveedor_ia: ProveedorInteligencia = Depends(obtener_dependencia_proveedor_inteligencia_pi),
    gestor_embeddings: GestorEmbeddings = Depends(obtener_dependencia_gestor_embeddings_pi),
    gestor_archivos: GestorMaestroDeProcesadoresArchivos = Depends(obtener_dependencia_gestor_procesadores_archivos_pi)
):
    """
    Endpoint que recibe una solicitud (usualmente de un worker Celery) para procesar
    los archivos de un curso. Añade la lógica de procesamiento principal a las tareas
    de fondo de FastAPI para no bloquear la respuesta al llamador (Celery).
    """
    registrador.info(
        f"Recibida solicitud HTTP (posiblemente de Celery) para iniciar procesamiento de archivos en segundo plano del curso ID: {solicitud_desde_celery.id_curso} "
        f"solicitado por usuario ID: {solicitud_desde_celery.id_usuario_moodle_solicitante}." # Campo refactorizado
    )

    # Añadir la función de lógica principal a las tareas de fondo de FastAPI.
    # Esto permite que el endpoint devuelva una respuesta rápidamente, mientras el trabajo pesado
    # se ejecuta en un hilo separado gestionado por FastAPI.
    tareas_en_segundo_plano_fastapi.add_task(
        _ejecutar_tarea_procesamiento_archivos_curso, # Función refactorizada
        id_curso_para_procesar=solicitud_desde_celery.id_curso, # Parámetro renombrado
        id_usuario_que_solicita=solicitud_desde_celery.id_usuario_moodle_solicitante, # Parámetro renombrado
        cliente_moodle=cliente_moodle,
        envoltorio_bd=envoltorio_bd, # Parámetro renombrado
        proveedor_ia=proveedor_ia,
        gestor_embeddings=gestor_embeddings,
        gestor_archivos=gestor_archivos # Parámetro renombrado
    )

    mensaje_respuesta_api = (
        f"El procesamiento de los archivos para el curso {solicitud_desde_celery.id_curso} "
        f"ha sido aceptado y añadido a la cola de tareas de fondo de FastAPI."
    )
    registrador.info(mensaje_respuesta_api)
    # Devolver una respuesta inmediata para liberar al worker de Celery.
    return {"mensaje": mensaje_respuesta_api, "id_curso_solicitado": solicitud_desde_celery.id_curso}

[end of entrenai_refactor/api/rutas/ruta_procesamiento_interno.py]
