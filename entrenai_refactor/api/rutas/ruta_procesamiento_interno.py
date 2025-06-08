import os
import traceback # Para el logging de errores fatales en tareas de fondo
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status

# Importar modelos Pydantic refactorizados (usando sus nuevos nombres en español)
from entrenai_refactor.api import modelos as modelos_api_traducidos
# Importar clases refactorizadas del núcleo
from entrenai_refactor.nucleo.clientes import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.bd import EnvoltorioPgVector, ErrorBaseDeDatosVectorial
from entrenai_refactor.nucleo.ia import (
    ProveedorInteligencia, ErrorProveedorInteligencia,
    GestorEmbeddings, ErrorGestorEmbeddings
)
from entrenai_refactor.nucleo.archivos import (
    GestorMaestroDeProcesadoresArchivos, ErrorProcesamientoArchivo, ErrorDependenciaFaltante
)
# Configuración y logging
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador_procesamiento_interno = APIRouter( # Renombrado para claridad
    prefix="/api/v1/procesamiento-interno",
    tags=["Procesamiento Interno y Tareas Asíncronas"],
)

# --- Funciones de Dependencia (Inyección de Dependencias de FastAPI) ---
# NOTA: Estas funciones son similares a las de 'ruta_configuracion_curso.py'.
# En una aplicación más grande, se recomienda centralizarlas en un módulo de dependencias común.

def dependencia_cliente_moodle_proc_interno() -> ClienteMoodle:
    """Dependencia para obtener una instancia del ClienteMoodle para este enrutador."""
    try:
        return ClienteMoodle()
    except ErrorAPIMoodle as e_moodle:
        registrador.error(f"Error específico al crear instancia de ClienteMoodle: {e_moodle}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con Moodle: {str(e_moodle)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ClienteMoodle: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar la conexión con Moodle.")

def dependencia_envoltorio_pgvector_proc_interno() -> EnvoltorioPgVector:
    """Dependencia para obtener una instancia del EnvoltorioPgVector para este enrutador."""
    try:
        return EnvoltorioPgVector()
    except ErrorBaseDeDatosVectorial as e_bd_vec:
        registrador.error(f"Error específico al crear instancia de EnvoltorioPgVector: {e_bd_vec}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial: {str(e_bd_vec)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de EnvoltorioPgVector: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el acceso a la base de datos vectorial.")

def dependencia_proveedor_inteligencia_proc_interno() -> ProveedorInteligencia:
    """Dependencia para obtener una instancia del ProveedorInteligencia para este enrutador."""
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e_prov_ia:
        registrador.error(f"Error específico al crear instancia de ProveedorInteligencia: {e_prov_ia}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA configurado: {str(e_prov_ia)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de ProveedorInteligencia: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el proveedor de IA.")

def dependencia_gestor_embeddings_proc_interno(
    proveedor_ia: ProveedorInteligencia = Depends(dependencia_proveedor_inteligencia_proc_interno)
) -> GestorEmbeddings:
    """Dependencia para obtener una instancia del GestorEmbeddings."""
    try:
        return GestorEmbeddings(proveedor_ia_configurado=proveedor_ia) # Usar el nombre de parámetro refactorizado
    except ErrorGestorEmbeddings as e_gestor_emb: # Asumiendo que GestorEmbeddings puede lanzar su propia excepción
        registrador.error(f"Error específico al crear instancia de GestorEmbeddings: {e_gestor_emb}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de embeddings: {str(e_gestor_emb)}")
    except Exception as e_inesperado:
        registrador.exception(f"Error inesperado al crear instancia de GestorEmbeddings: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno al configurar el gestor de embeddings: {str(e_inesperado)}")

def dependencia_gestor_procesadores_archivos_proc_interno() -> GestorMaestroDeProcesadoresArchivos:
    """Dependencia para obtener una instancia del GestorMaestroDeProcesadoresArchivos."""
    try:
        return GestorMaestroDeProcesadoresArchivos() # Usar el nombre de clase refactorizado
    except Exception as e_inesperado: # GestorMaestroDeProcesadoresArchivos podría no tener errores de inicialización complejos
        registrador.exception(f"Error inesperado al crear instancia de GestorMaestroDeProcesadoresArchivos: {e_inesperado}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de procesadores de archivos: {str(e_inesperado)}")


# --- Lógica de Procesamiento de Curso en Segundo Plano ---

async def _tarea_asincrona_procesar_archivos_curso( # Nombre traducido y más descriptivo
    id_curso: int,
    id_usuario_solicitante: int, # Mantener para auditoría o lógica futura
    cliente_moodle: ClienteMoodle,
    envoltorio_bd_pgvector: EnvoltorioPgVector,
    proveedor_ia: ProveedorInteligencia,
    gestor_embeddings: GestorEmbeddings,
    gestor_procesadores_archivos: GestorMaestroDeProcesadoresArchivos # Nombre de variable y tipo refactorizados
):
    """
    Tarea ejecutada en segundo plano para procesar todos los archivos de un curso:
    descarga, extracción de texto, formateo a Markdown, generación de embeddings,
    e inserción/actualización en la base de datos vectorial.
    """
    registrador.info(f"Inicio de procesamiento asíncrono de archivos para el curso ID: {id_curso}, solicitado por usuario ID: {id_usuario_solicitante}.")
    try:
        # 1. Obtener nombre del curso (necesario para el nombre de la tabla vectorial)
        # Esta lógica es similar a _aux_obtener_nombre_curso pero adaptada para un contexto de tarea de fondo.
        nombre_curso_para_tabla_db: Optional[str] = None
        try:
            # Intentar obtener cursos del usuario solicitante primero (podría ser un profesor)
            cursos_del_usuario = cliente_moodle.obtener_cursos_de_usuario(id_usuario=id_usuario_solicitante)
            curso_objeto = next((c for c in cursos_del_usuario if c.id == id_curso), None)
            if curso_objeto:
                nombre_curso_para_tabla_db = curso_objeto.nombre_a_mostrar or curso_objeto.nombre_completo
            else: # Fallback: buscar en todos los cursos si no se encontró en los del usuario
                todos_los_cursos_moodle = cliente_moodle.obtener_todos_los_cursos_disponibles()
                curso_objeto_todos = next((c for c in todos_los_cursos_moodle if c.id == id_curso), None)
                if curso_objeto_todos:
                    nombre_curso_para_tabla_db = curso_objeto_todos.nombre_a_mostrar or curso_objeto_todos.nombre_completo

            if not nombre_curso_para_tabla_db: # Si aún no se encuentra, usar un nombre genérico
                nombre_curso_para_tabla_db = f"curso_{id_curso}"
                registrador.warning(f"No se pudo obtener el nombre del curso {id_curso} desde Moodle. Se usará el nombre genérico: '{nombre_curso_para_tabla_db}' para la tabla vectorial.")
        except ErrorAPIMoodle as e_moodle_api:
            registrador.error(f"Error de API Moodle al obtener el nombre del curso {id_curso} para el procesamiento: {e_moodle_api}. Se usará un nombre genérico para la tabla.")
            nombre_curso_para_tabla_db = f"curso_{id_curso}" # Fallback si la API de Moodle falla

        # 2. Identificar la sección y carpeta de EntrenAI en Moodle donde están los documentos.
        nombre_seccion_entrenai_config = configuracion_global.moodle.nombre_carpeta_recursos_ia # CAMBIADO # Nombre de la SECCIÓN configurado
        # El nombre de la CARPETA dentro de esa sección podría ser el mismo o diferente. Asumamos que es el mismo por ahora.
        nombre_carpeta_documentos_entrenai = nombre_seccion_entrenai_config

        seccion_entrenai_moodle = cliente_moodle.obtener_seccion_por_nombre(id_curso, nombre_seccion_entrenai_config)
        if not seccion_entrenai_moodle or not seccion_entrenai_moodle.id: # Asegurar que la sección y su ID existan
            registrador.warning(f"No se encontró la sección configurada '{nombre_seccion_entrenai_config}' en el curso {id_curso}. No se procesarán archivos de esta fuente.")
            return # Terminar si la sección principal no existe

        # Obtener el módulo de carpeta usando su nombre dentro de la sección encontrada.
        modulo_carpeta_documentos = cliente_moodle.obtener_modulo_de_curso_por_nombre(id_curso, seccion_entrenai_moodle.id, nombre_carpeta_documentos_entrenai, "folder")
        if not modulo_carpeta_documentos or not modulo_carpeta_documentos.id: # El 'id' aquí es el cmid
            registrador.warning(f"No se encontró la carpeta de documentos '{nombre_carpeta_documentos_entrenai}' en la sección '{nombre_seccion_entrenai_config}' del curso {id_curso}.")
            return

        # 3. Obtener la lista de archivos de la carpeta de Moodle.
        lista_archivos_moodle = cliente_moodle.obtener_archivos_de_carpeta(modulo_carpeta_documentos.id) # Se usa el ID del módulo (cmid)
        if not lista_archivos_moodle:
            registrador.info(f"No se encontraron archivos en la carpeta '{nombre_carpeta_documentos_entrenai}' para el curso {id_curso}. Nada que procesar.")
            return

        registrador.info(f"Se encontraron {len(lista_archivos_moodle)} archivos en la carpeta de Moodle para el curso {id_curso}. Iniciando bucle de procesamiento individual.")

        # 4. Iterar sobre cada archivo y procesarlo.
        contador_archivos_procesados_exito = 0
        contador_archivos_omitidos_sin_cambios = 0

        directorio_descargas_curso = Path(configuracion_global.ruta_absoluta_directorio_descargas) / str(id_curso) # CAMBIADO
        directorio_descargas_curso.mkdir(parents=True, exist_ok=True)
        directorio_markdown_curso = Path(configuracion_global.ruta_absoluta_directorio_datos) / "markdown_cursos" / str(id_curso) # CAMBIADO
        directorio_markdown_curso.mkdir(parents=True, exist_ok=True)

        for archivo_moodle_actual in lista_archivos_moodle:
            # Usar nombre_archivo como identificador único dentro del contexto del curso.
            # Podría mejorarse usando 'ruta_archivo' si los nombres no son únicos globalmente en la carpeta.
            identificador_unico_archivo = archivo_moodle_actual.nombre_archivo
            timestamp_modificacion_moodle = archivo_moodle_actual.timestamp_modificacion

            registrador.debug(f"Evaluando archivo: '{identificador_unico_archivo}' (última modificación en Moodle: {timestamp_modificacion_moodle}).")

            # Verificar si el archivo es nuevo o ha sido modificado desde el último procesamiento.
            if envoltorio_bd_pgvector.verificar_si_archivo_es_nuevo_o_modificado(id_curso, identificador_unico_archivo, timestamp_modificacion_moodle):
                registrador.info(f"Procesando archivo nuevo o modificado: '{identificador_unico_archivo}' para el curso ID: {id_curso}.")
                ruta_archivo_local_descargado: Optional[Path] = None
                try:
                    # Descargar archivo
                    ruta_archivo_local_descargado = cliente_moodle.descargar_archivo_moodle(
                        url_archivo_moodle=str(archivo_moodle_actual.url_descarga_archivo),
                        directorio_destino_descarga=directorio_descargas_curso,
                        nombre_final_archivo=archivo_moodle_actual.nombre_archivo
                    )
                    registrador.info(f"Archivo '{identificador_unico_archivo}' descargado en: {ruta_archivo_local_descargado}.")

                    # Extraer texto del archivo descargado
                    texto_contenido_extraido = gestor_procesadores_archivos.procesar_archivo_segun_tipo(ruta_archivo_local_descargado)

                    if texto_contenido_extraido and texto_contenido_extraido.strip():
                        # Formatear a Markdown
                        ruta_archivo_markdown_guardado = directorio_markdown_curso / f"{ruta_archivo_local_descargado.stem}.md"
                        texto_contenido_markdown = proveedor_ia.formatear_texto_a_markdown(
                            texto_contenido_extraido,
                            ruta_archivo_para_guardar=ruta_archivo_markdown_guardado # Método refactorizado
                        )

                        # Dividir en fragmentos
                        lista_fragmentos_texto = gestor_embeddings.dividir_texto_en_fragmentos(texto_contenido_markdown)

                        # Generar embeddings para los fragmentos
                        lista_embeddings_generados = gestor_embeddings.generar_embeddings_para_lista_de_fragmentos(lista_fragmentos_texto)

                        # Preparar objetos para la base de datos
                        lista_objetos_fragmento_bd = gestor_embeddings.construir_objetos_fragmento_para_bd(
                            id_del_curso=id_curso,
                            id_del_documento=identificador_unico_archivo,
                            nombre_archivo_original=archivo_moodle_actual.nombre_archivo,
                            titulo_del_documento=archivo_moodle_actual.nombre_archivo, # Usar nombre de archivo como título por defecto
                            lista_textos_fragmentos=lista_fragmentos_texto,
                            lista_embeddings_fragmentos=lista_embeddings_generados
                        )

                        # Insertar/actualizar en PGVector
                        envoltorio_bd_pgvector.insertar_o_actualizar_fragmentos(
                            identificador_curso=nombre_curso_para_tabla_db, # Usar el nombre de tabla correcto
                            fragmentos_documento=lista_objetos_fragmento_bd
                        )
                        registrador.info(f"Archivo '{identificador_unico_archivo}' procesado, formateado, fragmentado y embeddings almacenados.")
                    else:
                        registrador.warning(f"No se extrajo contenido textual del archivo '{identificador_unico_archivo}'. No se generarán embeddings.")

                    # Marcar como procesado independientemente de si se extrajo texto (para no reintentar archivos vacíos)
                    envoltorio_bd_pgvector.marcar_archivo_como_procesado_en_seguimiento(id_curso, identificador_unico_archivo, timestamp_modificacion_moodle)
                    contador_archivos_procesados_exito += 1

                except ErrorDependenciaFaltante as e_dep_falta:
                    registrador.error(f"Dependencia faltante para procesar '{identificador_unico_archivo}': {e_dep_falta}. Omitiendo archivo.")
                except ErrorProcesamientoArchivo as e_proc_arc:
                    registrador.error(f"Error específico de procesamiento para el archivo '{identificador_unico_archivo}': {e_proc_arc}. Omitiendo archivo.")
                except ErrorAPIMoodle as e_moodle_descarga:
                     registrador.error(f"Error de API Moodle al descargar el archivo '{identificador_unico_archivo}': {e_moodle_descarga}. Omitiendo archivo.")
                except (ErrorProveedorInteligencia, ErrorGestorEmbeddings, ErrorBaseDeDatosVectorial) as e_nucleo_ia_bd:
                    registrador.error(f"Error del núcleo de IA o Base de Datos al procesar el archivo '{identificador_unico_archivo}': {e_nucleo_ia_bd}. Omitiendo archivo.")
                except Exception as e_general_archivo: # Capturar cualquier otro error inesperado para un archivo
                    registrador.exception(f"Error general inesperado al procesar el archivo '{identificador_unico_archivo}': {e_general_archivo}. Omitiendo archivo.")
                finally:
                    # Limpiar el archivo local descargado después de procesarlo (o intentarlo)
                    if ruta_archivo_local_descargado and ruta_archivo_local_descargado.exists():
                        try:
                            os.remove(ruta_archivo_local_descargado)
                            registrador.debug(f"Archivo local temporal '{ruta_archivo_local_descargado}' eliminado.")
                        except OSError as e_os_remove:
                            registrador.error(f"No se pudo eliminar el archivo local temporal '{ruta_archivo_local_descargado}': {e_os_remove}")
                    # Considerar si se debe mantener el archivo Markdown generado o eliminarlo también.
            else:
                registrador.info(f"El archivo '{identificador_unico_archivo}' del curso {id_curso} no ha sido modificado desde el último procesamiento. Se omite.")
                contador_archivos_omitidos_sin_cambios +=1

        registrador.info(
            f"Procesamiento asíncrono para el curso ID: {id_curso} finalizado. "
            f"Archivos procesados/actualizados con éxito: {contador_archivos_procesados_exito}. "
            f"Archivos omitidos (sin cambios): {contador_archivos_omitidos_sin_cambios}."
        )

    except Exception as e_error_fatal_tarea: # Error muy general que impide iniciar o continuar el procesamiento del curso
        registrador.error(f"Error fatal durante la ejecución de la tarea de procesamiento asíncrono para el curso {id_curso}: {e_error_fatal_tarea}")
        registrador.error(traceback.format_exc()) # Loguear el traceback completo para depuración


@enrutador_procesamiento_interno.post("/curso/procesar-archivos", # Ruta renombrada para claridad
                                      summary="Iniciar Procesamiento Asíncrono de Archivos de un Curso",
                                      description="Dispara una tarea en segundo plano (Celery) para procesar todos los archivos asociados a un curso (descarga, extracción de texto, generación de embeddings, etc.).")
async def solicitar_procesamiento_asincrono_curso( # Nombre de función traducido
    solicitud_procesamiento: modelos_api_traducidos.SolicitudProcesamientoArchivosCurso, # Modelo traducido
    tareas_en_segundo_plano: BackgroundTasks, # Mecanismo de FastAPI para tareas de fondo (si no se usa Celery directamente desde aquí)
    # Inyección de dependencias para ser pasadas a la tarea de fondo
    cliente_moodle: ClienteMoodle = Depends(dependencia_cliente_moodle_proc_interno),
    envoltorio_bd_pgvector: EnvoltorioPgVector = Depends(dependencia_envoltorio_pgvector_proc_interno),
    proveedor_ia: ProveedorInteligencia = Depends(dependencia_proveedor_inteligencia_proc_interno),
    gestor_embeddings: GestorEmbeddings = Depends(dependencia_gestor_embeddings_proc_interno),
    gestor_procesadores_archivos: GestorMaestroDeProcesadoresArchivos = Depends(dependencia_gestor_procesadores_archivos_proc_interno)
):
    registrador.info(
        f"Recibida solicitud HTTP para iniciar procesamiento de archivos del curso ID: {solicitud_procesamiento.id_curso} "
        f"por el usuario ID: {solicitud_procesamiento.id_usuario_solicitante}." # Campo traducido
    )

    # Aquí se podría añadir la lógica para encolar en Celery si este endpoint es solo un disparador.
    # Si la tarea Celery llama a este endpoint, entonces la lógica de BackgroundTasks es adecuada
    # para no bloquear la respuesta al worker de Celery.
    # Por el nombre "delegar_procesamiento_curso" en ruta_configuracion_curso, parece que ese otro endpoint
    # es el que realmente encola en Celery, y la tarea Celery podría llamar a este endpoint interno,
    # o directamente a la función _tarea_asincrona_procesar_archivos_curso.
    # Asumiendo que este endpoint es llamado por Celery o una tarea interna y debe ejecutar la lógica.

    tareas_en_segundo_plano.add_task(
        _tarea_asincrona_procesar_archivos_curso, # Función refactorizada
        id_curso=solicitud_procesamiento.id_curso,
        id_usuario_solicitante=solicitud_procesamiento.id_usuario_solicitante, # Campo traducido
        cliente_moodle=cliente_moodle,
        envoltorio_bd_pgvector=envoltorio_bd_pgvector,
        proveedor_ia=proveedor_ia,
        gestor_embeddings=gestor_embeddings,
        gestor_procesadores_archivos=gestor_procesadores_archivos
    )

    mensaje_respuesta = (
        f"El procesamiento de los archivos para el curso {solicitud_procesamiento.id_curso} "
        f"ha sido iniciado en segundo plano."
    )
    registrador.info(mensaje_respuesta)
    return {"mensaje": mensaje_respuesta}

[end of entrenai_refactor/api/rutas/ruta_procesamiento_interno.py]
