import os
import traceback
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.nucleo.clientes.cliente_moodle import ClienteMoodle, ErrorAPIMoodle
from entrenai_refactor.nucleo.bd.envoltorio_pgvector import EnvoltorioPgVector, ErrorEnvoltorioPgVector
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia, ErrorProveedorInteligencia
from entrenai_refactor.nucleo.ia.gestor_embeddings import GestorEmbeddings, ErrorGestorEmbeddings
from entrenai_refactor.nucleo.archivos.procesador_archivos import GestorProcesadoresArchivos, ErrorProcesamientoArchivo
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1/procesamiento-interno",
    tags=["Procesamiento Interno Asíncrono"],
    # Se podría añadir un response_model por defecto para errores 500 si es común
)

# --- Funciones de Dependencia (Reutilizadas o Definidas) ---
# Estas funciones ya están definidas en ruta_configuracion_curso.py.
# En una app FastAPI real, estas se definirían en un módulo de dependencias compartido.
# Por ahora, las redefiniré aquí para mantener el archivo autocontenido según la estructura actual.

def obtener_cliente_moodle() -> ClienteMoodle:
    try:
        return ClienteMoodle()
    except Exception as e:
        registrador.error(f"Error al crear instancia de ClienteMoodle: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con Moodle: {str(e)}")

def obtener_envoltorio_pgvector() -> EnvoltorioPgVector:
    try:
        return EnvoltorioPgVector()
    except Exception as e:
        registrador.error(f"Error al crear instancia de EnvoltorioPgVector: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo conectar con la base de datos vectorial: {str(e)}")

def obtener_proveedor_inteligencia() -> ProveedorInteligencia:
    try:
        return ProveedorInteligencia()
    except ErrorProveedorInteligencia as e:
        registrador.error(f"Error al crear instancia de ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"No se pudo inicializar el proveedor de IA: {str(e)}")
    except Exception as e:
        registrador.error(f"Error inesperado al crear ProveedorInteligencia: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al configurar el proveedor de IA.")

def obtener_gestor_embeddings(proveedor_ia: ProveedorInteligencia = Depends(obtener_proveedor_inteligencia)) -> GestorEmbeddings:
    try:
        return GestorEmbeddings(proveedor_ia=proveedor_ia)
    except Exception as e:
        registrador.error(f"Error al crear instancia de GestorEmbeddings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de embeddings: {str(e)}")

def obtener_gestor_procesadores_archivos() -> GestorProcesadoresArchivos:
    try:
        return GestorProcesadoresArchivos()
    except Exception as e:
        registrador.error(f"Error al crear instancia de GestorProcesadoresArchivos: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"No se pudo inicializar el gestor de procesadores de archivos: {str(e)}")


# --- Lógica de Procesamiento en Segundo Plano ---

async def _procesar_curso_async(
    id_curso: int,
    id_usuario: int, # Aunque no se use directamente en esta lógica, es bueno tenerlo para auditoría o futuras expansiones
    cliente_moodle: ClienteMoodle,
    bd_pgvector: EnvoltorioPgVector,
    proveedor_ia: ProveedorInteligencia,
    gestor_embeddings: GestorEmbeddings,
    gestor_procesadores: GestorProcesadoresArchivos
):
    registrador.info(f"Inicio de procesamiento asíncrono para curso ID: {id_curso}, iniciado por usuario ID: {id_usuario}")
    try:
        # 1. Obtener nombre del curso (necesario para el nombre de la tabla vectorial)
        # Usaremos una versión simplificada de _obtener_nombre_curso_operaciones aquí
        nombre_curso_para_tabla: Optional[str] = None
        try:
            cursos_usuario = cliente_moodle.obtener_cursos_usuario(id_usuario) # Podría ser id_profesor_defecto
            curso_obj = next((c for c in cursos_usuario if c.id == id_curso), None)
            if curso_obj:
                nombre_curso_para_tabla = curso_obj.nombre_a_mostrar or curso_obj.nombre_completo
            else: # Fallback a todos los cursos si no se encuentra en los del usuario
                todos_los_cursos = cliente_moodle.obtener_todos_los_cursos()
                curso_obj_todos = next((c for c in todos_los_cursos if c.id == id_curso), None)
                if curso_obj_todos:
                    nombre_curso_para_tabla = curso_obj_todos.nombre_a_mostrar or curso_obj_todos.nombre_completo

            if not nombre_curso_para_tabla:
                 # Como último recurso, si el curso existe pero no se pudo obtener el nombre fácilmente
                nombre_curso_para_tabla = f"curso_{id_curso}"
                registrador.warning(f"No se pudo obtener el nombre del curso {id_curso} de Moodle. Usando nombre genérico: '{nombre_curso_para_tabla}' para la tabla vectorial.")

        except ErrorAPIMoodle as e_moodle:
            registrador.error(f"Error API Moodle obteniendo nombre del curso {id_curso} para procesamiento: {e_moodle}. Usando nombre genérico.")
            nombre_curso_para_tabla = f"curso_{id_curso}" # Fallback si falla la API

        # 2. Identificar sección y carpeta de EntrenAI en Moodle
        nombre_seccion_entrenai = configuracion_global.moodle.nombre_carpeta_curso # Este es el nombre de la SECCIÓN
        nombre_carpeta_documentos = "Documentos EntrenAI" # Nombre fijo de la CARPETA dentro de la sección

        seccion_entrenai = cliente_moodle.obtener_seccion_por_nombre(id_curso, nombre_seccion_entrenai)
        if not seccion_entrenai:
            registrador.warning(f"No se encontró la sección '{nombre_seccion_entrenai}' en el curso {id_curso}. No se procesarán archivos.")
            return

        carpeta_docs = cliente_moodle.obtener_modulo_curso_por_nombre(id_curso, seccion_entrenai.id, nombre_carpeta_documentos, "folder")
        if not carpeta_docs or not carpeta_docs.id_instancia: # id_instancia es el ID de la carpeta en sí
            registrador.warning(f"No se encontró la carpeta '{nombre_carpeta_documentos}' en la sección '{nombre_seccion_entrenai}' del curso {id_curso}.")
            return

        # 3. Obtener lista de archivos de la carpeta
        archivos_moodle = cliente_moodle.obtener_archivos_carpeta(carpeta_docs.id) # Se usa el ID del módulo (cmid)
        if not archivos_moodle:
            registrador.info(f"No se encontraron archivos en la carpeta '{nombre_carpeta_documentos}' para el curso {id_curso}.")
            return

        registrador.info(f"Encontrados {len(archivos_moodle)} archivos en Moodle para curso {id_curso}. Iniciando procesamiento...")

        # 4. Iterar y procesar archivos
        archivos_procesados_count = 0
        archivos_omitidos_count = 0
        for archivo_moodle in archivos_moodle:
            identificador_archivo = archivo_moodle.nombre_archivo # Usar nombre_archivo como identificador único dentro del curso
            # El identificador podría ser más robusto, ej. combinando ruta_archivo si hay duplicados de nombres.
            # Por ahora, asumimos que nombre_archivo es suficientemente único en la carpeta.

            registrador.debug(f"Verificando archivo: '{identificador_archivo}' (modificado en Moodle: {archivo_moodle.tiempo_modificacion})")
            if bd_pgvector.es_archivo_nuevo_o_modificado(id_curso, identificador_archivo, archivo_moodle.tiempo_modificacion):
                registrador.info(f"Procesando archivo nuevo o modificado: '{identificador_archivo}' para curso {id_curso}")

                ruta_descarga_base = Path(configuracion_global.ruta_directorio_descargas) / str(id_curso)
                ruta_descarga_base.mkdir(parents=True, exist_ok=True)

                ruta_archivo_local: Optional[Path] = None
                ruta_markdown_guardado: Optional[Path] = None
                try:
                    ruta_archivo_local = cliente_moodle.descargar_archivo(
                        url_archivo=str(archivo_moodle.url_archivo), # Asegurar que es string
                        directorio_descarga=ruta_descarga_base,
                        nombre_archivo=archivo_moodle.nombre_archivo
                    )

                    texto_extraido = gestor_procesadores.procesar_archivo(ruta_archivo_local)
                    if texto_extraido and texto_extraido.strip():
                        ruta_markdown_dir = Path(configuracion_global.ruta_directorio_datos) / "markdown_cursos" / str(id_curso)
                        ruta_markdown_dir.mkdir(parents=True, exist_ok=True)
                        ruta_markdown_guardado = ruta_markdown_dir / f"{ruta_archivo_local.stem}.md"

                        texto_markdown = proveedor_ia.formatear_a_markdown(texto_extraido, ruta_guardado=ruta_markdown_guardado)

                        fragmentos_texto = gestor_embeddings.dividir_texto_en_fragmentos(texto_markdown)

                        # Contextualización (opcional, podría hacerse antes de dividir o si los fragmentos son muy genéricos)
                        # Por ahora, asumimos que el texto markdown ya tiene suficiente contexto inherente.
                        # fragmentos_contextualizados = [
                        #    gestor_embeddings.contextualizar_fragmento(f, archivo_moodle.nombre_archivo, archivo_moodle.nombre_archivo)
                        #    for f in fragmentos_texto
                        # ]
                        # embeddings = gestor_embeddings.generar_embeddings_para_fragmentos(fragmentos_contextualizados)

                        embeddings = gestor_embeddings.generar_embeddings_para_fragmentos(fragmentos_texto)

                        lista_fragmentos_bd = gestor_embeddings.preparar_fragmentos_documento_para_bd(
                            id_curso=id_curso,
                            id_documento=identificador_archivo, # Usar el identificador del archivo
                            nombre_archivo_fuente=archivo_moodle.nombre_archivo,
                            titulo_documento=archivo_moodle.nombre_archivo, # Usar nombre_archivo como título por defecto
                            textos_fragmentos=fragmentos_texto,
                            embeddings=embeddings
                        )

                        bd_pgvector.insertar_actualizar_fragmentos(
                            nombre_curso_o_id_curso=nombre_curso_para_tabla, # Usar el nombre de tabla correcto
                            fragmentos=lista_fragmentos_bd
                        )
                        registrador.info(f"Archivo '{identificador_archivo}' procesado e indexado.")
                    else:
                        registrador.warning(f"No se extrajo texto del archivo '{identificador_archivo}'. No se procesarán embeddings.")

                    bd_pgvector.marcar_archivo_como_procesado(id_curso, identificador_archivo, archivo_moodle.tiempo_modificacion)
                    archivos_procesados_count += 1

                except ErrorProcesamientoArchivo as e_proc:
                    registrador.error(f"Error de procesamiento para archivo '{identificador_archivo}': {e_proc}")
                except ErrorAPIMoodle as e_moodle_dl:
                     registrador.error(f"Error descargando archivo '{identificador_archivo}': {e_moodle_dl}")
                except (ErrorProveedorInteligencia, ErrorGestorEmbeddings, ErrorEnvoltorioPgVector) as e_ia_db:
                    registrador.error(f"Error de IA o BD procesando archivo '{identificador_archivo}': {e_ia_db}")
                except Exception as e_gen:
                    registrador.exception(f"Error general inesperado procesando archivo '{identificador_archivo}': {e_gen}")
                finally:
                    # Limpiar archivos temporales
                    if ruta_archivo_local and ruta_archivo_local.exists():
                        try:
                            os.remove(ruta_archivo_local)
                            registrador.debug(f"Archivo local temporal eliminado: {ruta_archivo_local}")
                        except OSError as e_os:
                            registrador.error(f"Error eliminando archivo local temporal {ruta_archivo_local}: {e_os}")
                    # Considerar si se quiere mantener el archivo markdown o eliminarlo también.
                    # if ruta_markdown_guardado and ruta_markdown_guardado.exists():
                    #     os.remove(ruta_markdown_guardado)
            else:
                registrador.info(f"Archivo '{identificador_archivo}' para curso {id_curso} no ha cambiado. Omitiendo.")
                archivos_omitidos_count +=1

        registrador.info(f"Procesamiento asíncrono para curso ID: {id_curso} completado. "
                         f"Archivos procesados/actualizados: {archivos_procesados_count}. Archivos omitidos: {archivos_omitidos_count}.")

    except Exception as e_fatal:
        registrador.error(f"Error fatal durante el procesamiento asíncrono del curso {id_curso}: {e_fatal}")
        registrador.error(traceback.format_exc())


@enrutador.post("/curso",
                 summary="Procesar Contenido de Curso Asíncronamente",
                 description="Inicia el procesamiento completo del contenido de un curso (descarga, extracción, embeddings) en segundo plano.")
async def procesar_contenido_curso_endpoint(
    solicitud: modelos_api.SolicitudProcesamientoArchivos,
    tareas_fondo: BackgroundTasks,
    cliente_moodle: ClienteMoodle = Depends(obtener_cliente_moodle),
    bd_pgvector: EnvoltorioPgVector = Depends(obtener_envoltorio_pgvector),
    proveedor_ia: ProveedorInteligencia = Depends(obtener_proveedor_inteligencia),
    gestor_embeddings: GestorEmbeddings = Depends(obtener_gestor_embeddings),
    gestor_procesadores: GestorProcesadoresArchivos = Depends(obtener_gestor_procesadores_archivos)
):
    registrador.info(f"Recibida solicitud para procesar curso ID: {solicitud.id_curso} por usuario ID: {solicitud.id_usuario}")

    tareas_fondo.add_task(
        _procesar_curso_async,
        id_curso=solicitud.id_curso,
        id_usuario=solicitud.id_usuario,
        cliente_moodle=cliente_moodle,
        bd_pgvector=bd_pgvector,
        proveedor_ia=proveedor_ia,
        gestor_embeddings=gestor_embeddings,
        gestor_procesadores=gestor_procesadores
    )

    return {"mensaje": f"Procesamiento del curso {solicitud.id_curso} iniciado en segundo plano."}

[end of entrenai_refactor/api/rutas/ruta_procesamiento_interno.py]
