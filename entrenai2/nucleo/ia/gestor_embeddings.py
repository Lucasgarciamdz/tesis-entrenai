import uuid
from typing import List, Optional, Dict, Any, Union

from entrenai2.api.modelos import FragmentoDocumento
from entrenai2.configuracion.registrador import obtener_registrador
from entrenai2.nucleo.ia.envoltorio_gemini import EnvoltorioGemini
from entrenai2.nucleo.ia.envoltorio_ollama import EnvoltorioOllama

registrador = obtener_registrador(__name__)


class ErrorGestorEmbeddings(Exception):
    """Excepción personalizada para errores de GestorEmbeddings."""
    pass


class GestorEmbeddings:
    """
    Gestiona la división de texto, chunking, contextualización y generación de embeddings.
    """

    def __init__(
        self,
        envoltorio_ia: Union[EnvoltorioOllama, EnvoltorioGemini],
        tamano_fragmento_defecto: int = 1000,
        solapamiento_fragmento_defecto: int = 200,
    ):
        self.envoltorio_ia = envoltorio_ia
        self.tamano_fragmento_defecto = tamano_fragmento_defecto
        self.solapamiento_fragmento_defecto = solapamiento_fragmento_defecto
        registrador.info(
            f"GestorEmbeddings inicializado con tamaño de fragmento {tamano_fragmento_defecto} "
            f"y solapamiento {solapamiento_fragmento_defecto}."
        )

    def dividir_texto_en_fragmentos(
        self,
        texto: str,
        tamano_fragmento: Optional[int] = None,
        solapamiento_fragmento: Optional[int] = None,
    ) -> List[str]:
        """
        Divide un texto largo en fragmentos más pequeños.
        """
        tf = tamano_fragmento or self.tamano_fragmento_defecto
        sf = solapamiento_fragmento or self.solapamiento_fragmento_defecto

        if sf >= tf:
            raise ValueError(
                "El solapamiento del fragmento debe ser menor que el tamaño del fragmento."
            )

        registrador.info(
            f"Dividiendo texto (longitud: {len(texto)}) en fragmentos (tamaño: {tf}, solapamiento: {sf})."
        )

        fragmentos: List[str] = []
        indice_inicio = 0
        longitud_texto = len(texto)

        if longitud_texto == 0:
            return []
        if longitud_texto <= tf:
            return [texto]

        while indice_inicio < longitud_texto:
            indice_fin = min(indice_inicio + tf, longitud_texto)
            fragmentos.append(texto[indice_inicio:indice_fin])

            if indice_fin == longitud_texto:
                break

            indice_inicio += tf - sf
            if indice_inicio >= longitud_texto:
                break

        registrador.info(f"Texto dividido en {len(fragmentos)} fragmentos.")
        return fragmentos

    @staticmethod
    def contextualizar_fragmento(
        texto_fragmento: str,
        titulo_documento: Optional[str] = None,
        nombre_archivo_fuente: Optional[str] = None,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Añade contexto simple a un fragmento de texto usando metadatos.
        """
        partes_contexto = []
        if nombre_archivo_fuente:
            partes_contexto.append(f"Fuente del Archivo: {nombre_archivo_fuente}")
        if titulo_documento:
            partes_contexto.append(f"Título del Documento: {titulo_documento}")

        prefijo_contexto = "\n".join(partes_contexto)
        if prefijo_contexto:
            return f"{prefijo_contexto}\n\nContenido del Fragmento:\n{texto_fragmento}"
        else:
            return texto_fragmento

    def generar_embeddings_para_fragmentos(
        self, fragmentos_contextualizados: List[str], modelo_embedding: Optional[str] = None
    ) -> List[List[float]]:
        """
        Genera embeddings para una lista de fragmentos de texto (contextualizados).
        """
        if not fragmentos_contextualizados:
            return []

        registrador.info(f"Generando embeddings para {len(fragmentos_contextualizados)} fragmentos...")
        embeddings: List[List[float]] = []
        for i, texto_fragmento in enumerate(fragmentos_contextualizados):
            try:
                registrador.debug(
                    f"Generando embedding para fragmento {i + 1}/{len(fragmentos_contextualizados)} (longitud: {len(texto_fragmento)} caracteres)"
                )
                emb = self.envoltorio_ia.generar_embedding(
                    texto=texto_fragmento, modelo=modelo_embedding
                )
                embeddings.append(emb)
            except Exception as e:
                registrador.error(
                    f"Falló la generación de embedding para el fragmento {i + 1}: {e}. Omitiendo este fragmento."
                )
                embeddings.append([])
        registrador.info(
            f"Embeddings generados exitosamente para {sum(1 for emb in embeddings if emb)} fragmentos."
        )
        return embeddings

    @staticmethod
    def preparar_fragmentos_documento_para_bd_vectorial(
        id_curso: int,
        id_documento: str,
        nombre_archivo_fuente: str,
        titulo_documento: Optional[str],
        textos_fragmentos: List[str],
        embeddings: List[List[float]],
        metadatos_adicionales: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> List[FragmentoDocumento]:
        """
        Prepara objetos FragmentoDocumento listos para la BD Vectorial, incluyendo IDs únicos y metadatos.
        """
        if len(textos_fragmentos) != len(embeddings):
            raise ValueError(
                "El número de fragmentos de texto y embeddings debe coincidir."
            )
        if metadatos_adicionales and len(textos_fragmentos) != len(metadatos_adicionales):
            raise ValueError(
                "El número de fragmentos de texto y metadatos_adicionales debe coincidir si se proveen metadatos."
            )

        fragmentos_documento: List[FragmentoDocumento] = []
        for i, texto_fragmento in enumerate(textos_fragmentos):
            id_fragmento = str(uuid.uuid4())
            metadata = {
                "id_curso": id_curso,
                "id_documento": id_documento,
                "nombre_archivo_fuente": nombre_archivo_fuente,
                "texto_original": texto_fragmento, # Guardar el texto original en metadata
            }
            if titulo_documento:
                metadata["titulo_documento"] = titulo_documento

            if metadatos_adicionales and metadatos_adicionales[i] is not None:
                metadata.update(metadatos_adicionales[i]) # type: ignore

            fragmentos_documento.append(
                FragmentoDocumento(
                    id=id_fragmento,
                    id_curso=id_curso,
                    id_documento=id_documento,
                    texto=texto_fragmento,
                    embedding=embeddings[i] if embeddings[i] else None,
                    metadata=metadata,
                )
            )
        registrador.info(
            f"Preparados {len(fragmentos_documento)} objetos FragmentoDocumento para la BD Vectorial."
        )
        return fragmentos_documento
