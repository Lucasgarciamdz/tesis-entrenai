import uuid
from typing import List, Optional, Dict, Any

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia
# Asumiendo que ProveedorInteligencia es la clase que unifica Ollama y Gemini

registrador = obtener_registrador(__name__)

class ErrorGestorEmbeddings(Exception):
    """Excepción personalizada para errores del GestorEmbeddings."""
    pass

class GestorEmbeddings:
    """
    Gestiona la división de texto, fragmentación (chunking), contextualización y generación de embeddings.
    """

    def __init__(
        self,
        proveedor_ia: ProveedorInteligencia, # Recibe el proveedor unificado
        tamano_fragmento_defecto: int = 1000,  # En caracteres
        solapamiento_fragmento_defecto: int = 150,  # En caracteres
    ):
        self.proveedor_ia = proveedor_ia # Este proveedor ya tiene el envoltorio activo (Ollama o Gemini)
        self.tamano_fragmento_defecto = tamano_fragmento_defecto
        self.solapamiento_fragmento_defecto = solapamiento_fragmento_defecto
        registrador.info(
            f"GestorEmbeddings inicializado con tamaño de fragmento por defecto: {tamano_fragmento_defecto} "
            f"y solapamiento por defecto: {solapamiento_fragmento_defecto}."
        )

    def dividir_texto_en_fragmentos(
        self,
        texto: str,
        tamano_fragmento: Optional[int] = None,
        solapamiento_fragmento: Optional[int] = None,
    ) -> List[str]:
        """
        Divide un texto largo en fragmentos (chunks) más pequeños.
        Utiliza una lógica simple de división basada en caracteres.
        """
        tam_frag = tamano_fragmento or self.tamano_fragmento_defecto
        solap_frag = solapamiento_fragmento or self.solapamiento_fragmento_defecto

        if solap_frag >= tam_frag:
            raise ValueError("El solapamiento del fragmento debe ser menor que el tamaño del fragmento.")

        registrador.info(
            f"Dividiendo texto (longitud: {len(texto)}) en fragmentos (tamaño: {tam_frag}, solapamiento: {solap_frag})."
        )

        fragmentos: List[str] = []
        indice_inicio = 0
        longitud_texto = len(texto)

        if longitud_texto == 0:
            return []
        if longitud_texto <= tam_frag: # Si el texto es más corto o igual al tamaño del fragmento, es un solo fragmento.
            return [texto]

        while indice_inicio < longitud_texto:
            indice_fin = min(indice_inicio + tam_frag, longitud_texto)
            fragmentos.append(texto[indice_inicio:indice_fin])

            if indice_fin == longitud_texto: # Se alcanzó el final del texto
                break

            # Mover el inicio para el siguiente fragmento, considerando el solapamiento
            indice_inicio += tam_frag - solap_frag

            # Seguridad para evitar bucles infinitos si tam_frag - solap_frag es 0 o negativo, aunque ya validado.
            if indice_inicio >= indice_fin :
                registrador.warning("Avance de fragmento no positivo, deteniendo para evitar bucle.")
                break


        registrador.info(f"Texto dividido en {len(fragmentos)} fragmentos.")
        return fragmentos

    @staticmethod # No necesita 'self' ya que es una función de utilidad pura
    def contextualizar_fragmento(
        texto_fragmento: str,
        titulo_documento: Optional[str] = None,
        nombre_archivo_fuente: Optional[str] = None,
        metadatos_extra: Optional[Dict[str, Any]] = None, # No se usa en esta implementación simple
    ) -> str:
        """
        Añade contexto simple a un fragmento de texto usando metadatos.
        Esta versión antepone el nombre del archivo fuente y el título del documento si se proporcionan.
        """
        partes_contexto = []
        if nombre_archivo_fuente:
            partes_contexto.append(f"Fuente del Archivo: {nombre_archivo_fuente}")
        if titulo_documento:
            partes_contexto.append(f"Título del Documento: {titulo_documento}")

        prefijo_contexto = "\n".join(partes_contexto)
        if prefijo_contexto:
            # Devolver el fragmento con el contexto añadido al principio.
            return f"{prefijo_contexto}\n\nContenido del Fragmento:\n{texto_fragmento}"
        else:
            # Si no hay contexto para añadir, devolver el fragmento original.
            return texto_fragmento

    def generar_embeddings_para_fragmentos(
        self, fragmentos_contextualizados: List[str], modelo_embedding: Optional[str] = None
    ) -> List[List[float]]:
        """
        Genera embeddings para una lista de fragmentos de texto (ya contextualizados).
        Delega la generación al proveedor de IA activo.
        """
        if not fragmentos_contextualizados:
            return []

        registrador.info(f"Generando embeddings para {len(fragmentos_contextualizados)} fragmentos...")
        embeddings_generados: List[List[float]] = []
        for i, texto_fragmento in enumerate(fragmentos_contextualizados):
            try:
                registrador.debug(
                    f"Generando embedding para fragmento {i + 1}/{len(fragmentos_contextualizados)} "
                    f"(longitud: {len(texto_fragmento)} caracteres)"
                )
                # Llama al método del ProveedorInteligencia, que a su vez usa el envoltorio activo.
                emb = self.proveedor_ia.generar_embedding(texto=texto_fragmento, modelo=modelo_embedding)
                embeddings_generados.append(emb)
            except Exception as e:
                registrador.error(
                    f"Falló la generación de embedding para el fragmento {i + 1}: {e}. "
                    "Se añadirá un embedding vacío para este fragmento."
                )
                embeddings_generados.append([]) # Añadir lista vacía para mantener correspondencia con fragmentos

        num_embeddings_exitosos = sum(1 for emb in embeddings_generados if emb)
        registrador.info(f"Embeddings generados para {num_embeddings_exitosos} de {len(fragmentos_contextualizados)} fragmentos.")
        return embeddings_generados

    @staticmethod
    def preparar_fragmentos_documento_para_bd(
        id_curso: int,
        id_documento: str, # Podría ser un hash del contenido del archivo o nombre único
        nombre_archivo_fuente: str,
        titulo_documento: Optional[str],
        textos_fragmentos: List[str], # Fragmentos ya contextualizados o no, según se decida
        embeddings: List[List[float]],
        metadatos_adicionales: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> List[modelos_api.FragmentoDocumento]:
        """
        Prepara objetos FragmentoDocumento listos para la base de datos vectorial.
        Incluye IDs únicos para cada fragmento y metadatos relevantes.
        """
        if len(textos_fragmentos) != len(embeddings):
            raise ValueError("El número de fragmentos de texto y embeddings debe coincidir.")
        if metadatos_adicionales and len(textos_fragmentos) != len(metadatos_adicionales):
            raise ValueError("El número de fragmentos de texto y metadatos_adicionales debe coincidir si se proveen.")

        fragmentos_para_bd: List[modelos_api.FragmentoDocumento] = []
        for i, texto_fragmento_actual in enumerate(textos_fragmentos):
            # El ID del fragmento se genera automáticamente por el modelo Pydantic si no se provee.
            # id_fragmento_uuid = str(uuid.uuid4())

            metadatos_fragmento = {
                # "id_curso": id_curso, # id_curso ya es un campo directo en FragmentoDocumento
                # "id_documento": id_documento, # id_documento ya es un campo directo
                "nombre_archivo_fuente": nombre_archivo_fuente,
                # "texto_original_fragmento": texto_fragmento_actual, # El campo 'texto' ya lo tiene
            }
            if titulo_documento:
                metadatos_fragmento["titulo_documento"] = titulo_documento

            if metadatos_adicionales and metadatos_adicionales[i]:
                metadatos_fragmento.update(metadatos_adicionales[i]) # type: ignore

            fragmento_bd = modelos_api.FragmentoDocumento(
                # id_fragmento se genera por defecto en el modelo
                id_curso=id_curso,
                id_documento=id_documento,
                texto=texto_fragmento_actual, # Este debería ser el texto original del fragmento, no el contextualizado
                embedding=embeddings[i] if embeddings[i] else None, # Guardar None si el embedding falló
                metadatos=metadatos_fragmento,
            )
            fragmentos_para_bd.append(fragmento_bd)

        registrador.info(f"Preparados {len(fragmentos_para_bd)} objetos FragmentoDocumento para la BD.")
        return fragmentos_para_bd

[end of entrenai_refactor/nucleo/ia/gestor_embeddings.py]
