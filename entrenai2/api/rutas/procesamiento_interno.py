import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException

from entrenai2.api.modelos import SolicitudProcesarArchivo
from entrenai2.configuracion.configuracion import config
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.proveedor_ia import ProveedorIA
from entrenai2.nucleo.clientes.cliente_moodle import ClienteMoodle
from entrenai2.nucleo.bd.envoltorio_pgvector import EnvoltorioPgvector
from entrenai2.nucleo.archivos.procesador_archivos import GestorProcesadoresArchivos
from entrenai2.nucleo.ia.gestor_embeddings import GestorEmbeddings

registrador = obtener_registrador(__name__)

enrutador = APIRouter(
    prefix="/api/v1/interno",
    tags=["Procesamiento Interno"],
)

@enrutador.post("/procesar-archivo")
async def procesar_archivo_endpoint(solicitud: SolicitudProcesarArchivo):
    """
    Endpoint interno para procesar un archivo de Moodle.
    Este endpoint es llamado por una tarea de Celery y orquesta todo el proceso.
    """
    nombre_archivo = solicitud.info_archivo_moodle.get("filename", "nombre_desconocido")
    registrador.info(f"Iniciando procesamiento para archivo: {nombre_archivo} del curso ID: {solicitud.id_curso}")

    bd_pgvector = None
    try:
        # 1. Instanciar dependencias
        cliente_moodle = ClienteMoodle()
        bd_pgvector = EnvoltorioPgvector()
        gestor_procesadores = GestorProcesadoresArchivos()
        cliente_ia = ProveedorIA.obtener_envoltorio_ia_por_proveedor()
        gestor_embeddings = GestorEmbeddings(cliente_ia)

        # 2. Descargar archivo
        directorio_descarga = Path(config.directorio_descargas) / str(solicitud.id_curso)
        directorio_descarga.mkdir(parents=True, exist_ok=True)
        
        ruta_archivo = cliente_moodle.descargar_archivo(
            solicitud.info_archivo_moodle["fileurl"], directorio_descarga, nombre_archivo
        )
        registrador.info(f"Archivo descargado en: {ruta_archivo}")

        # 3. Procesar y extraer texto
        texto_crudo = gestor_procesadores.procesar_archivo(ruta_archivo)
        if not texto_crudo:
            raise ValueError(f"No se pudo extraer texto del archivo: {nombre_archivo}")

        # 4. Formatear a Markdown
        texto_markdown = cliente_ia.formatear_a_markdown(texto_crudo)
        if not texto_markdown:
            raise RuntimeError(f"No se pudo formatear el texto a markdown para: {nombre_archivo}")

        # 5. Generar y almacenar embeddings
        fragmentos = gestor_embeddings.dividir_texto_en_fragmentos(texto_markdown)
        if not fragmentos:
            registrador.warning(f"No se generaron fragmentos para el archivo: {nombre_archivo}.")
        else:
            fragmentos_contextualizados = [gestor_embeddings.contextualizar_fragmento(f, nombre_archivo, f"frag_{i}") for i, f in enumerate(fragmentos)]
            embeddings = gestor_embeddings.generar_embeddings_para_fragmentos(fragmentos_contextualizados)
            
            fragmentos_db = gestor_embeddings.preparar_fragmentos_documento_para_bd_vectorial(
                id_documento=f"{solicitud.id_curso}_{nombre_archivo}",
                titulo_documento=nombre_archivo,
                nombre_archivo_fuente=nombre_archivo,
                textos_fragmentos=fragmentos_contextualizados,
                embeddings=embeddings,
                id_curso=solicitud.id_curso,
            )
            bd_pgvector.insertar_o_actualizar_fragmentos(solicitud.nombre_curso, fragmentos_db)

        # 6. Marcar como procesado
        bd_pgvector.marcar_archivo_como_procesado(
            solicitud.id_curso, nombre_archivo, solicitud.info_archivo_moodle["timemodified"]
        )

        # 7. Limpieza
        ruta_archivo.unlink(missing_ok=True)
        registrador.info(f"Procesamiento completado y archivo temporal eliminado para: {nombre_archivo}")

        return {
            "nombre_archivo": nombre_archivo,
            "estado": "exitoso",
            "fragmentos_insertados": len(fragmentos) if fragmentos else 0,
        }

    except Exception as e:
        registrador.error(f"Error procesando archivo {nombre_archivo}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail={"nombre_archivo": nombre_archivo, "estado": "error", "mensaje": str(e)})
    finally:
        if bd_pgvector:
            bd_pgvector.cerrar_conexion()
