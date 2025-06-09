from typing import List, Optional, Dict, Any

from entrenai_refactor.api import modelos as modelos_api # Modelos Pydantic para la API
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia, ErrorProveedorInteligencia

registrador = obtener_registrador(__name__)

class ErrorGestorEmbeddings(Exception):
    """Excepción personalizada para errores originados en el GestorEmbeddings."""
    def __init__(self, mensaje: str, error_original: Optional[Exception] = None):
        super().__init__(mensaje)
        self.error_original = error_original
        registrador.debug(f"Excepción ErrorGestorEmbeddings creada: {mensaje}, Original: {error_original}")

    def __str__(self):
        if self.error_original:
            return f"{super().__str__()} (Error original: {type(self.error_original).__name__}: {str(self.error_original)})"
        return super().__str__()

class GestorEmbeddings:
    """
    Clase responsable de gestionar la creación de embeddings a partir de texto.
    Incluye la división de texto en fragmentos (chunking), la contextualización
    de estos fragmentos, la generación de los vectores de embedding a través de
    un proveedor de inteligencia artificial, y la preparación de los datos para su almacenamiento.
    """

    def __init__(
        self,
        proveedor_ia: ProveedorInteligencia,
        tamano_fragmento_predeterminado: int = 1000,  # En número de caracteres
        solapamiento_fragmento_predeterminado: int = 150,  # En número de caracteres
    ):
        """
        Inicializa el GestorEmbeddings.

        Args:
            proveedor_ia: Instancia del ProveedorInteligencia ya inicializado.
            tamano_fragmento_predeterminado: Tamaño por defecto para dividir el texto en caracteres.
            solapamiento_fragmento_predeterminado: Solapamiento por defecto entre fragmentos en caracteres.
        """
        self.proveedor_ia = proveedor_ia
        self.tamano_fragmento_predeterminado = tamano_fragmento_predeterminado
        self.solapamiento_fragmento_predeterminado = solapamiento_fragmento_predeterminado
        registrador.info(
            f"GestorEmbeddings inicializado. Tamaño de fragmento predeterminado: {tamano_fragmento_predeterminado} caracteres, "
            f"Solapamiento predeterminado: {solapamiento_fragmento_predeterminado} caracteres."
        )

    def dividir_texto_en_fragmentos(
        self,
        texto_completo: str,
        tamano_max_fragmento: Optional[int] = None,
        solapamiento_entre_fragmentos: Optional[int] = None,
    ) -> List[str]:
        """
        Divide un texto largo en fragmentos (chunks) más pequeños y manejables.
        Esta implementación utiliza una división simple basada en caracteres.

        Args:
            texto_completo: El texto a dividir.
            tamano_max_fragmento: Opcional. Tamaño máximo de cada fragmento en caracteres.
                                   Si es None, usa el valor predeterminado del gestor.
            solapamiento_entre_fragmentos: Opcional. Número de caracteres de solapamiento entre fragmentos.
                                           Si es None, usa el valor predeterminado del gestor.

        Returns:
            Una lista de strings, donde cada string es un fragmento del texto original.

        Raises:
            ValueError: Si el solapamiento es mayor o igual al tamaño del fragmento,
                        o si los tamaños son inválidos.
            TypeError: Si el texto_completo no es un string.
        """
        tam_fragmento_actual = tamano_max_fragmento if tamano_max_fragmento is not None else self.tamano_fragmento_predeterminado
        solap_fragmento_actual = solapamiento_entre_fragmentos if solapamiento_entre_fragmentos is not None else self.solapamiento_fragmento_predeterminado

        if not isinstance(texto_completo, str):
            registrador.error(f"Se esperaba un string para dividir, pero se recibió {type(texto_completo)}.")
            raise TypeError("El texto_completo debe ser un string.")

        if tam_fragmento_actual <= 0:
            raise ValueError("El tamaño del fragmento debe ser un entero positivo.")
        if solap_fragmento_actual < 0:
            raise ValueError("El solapamiento del fragmento no puede ser negativo.")

        if solap_fragmento_actual >= tam_fragmento_actual:
            mensaje_error_solapamiento = (
                f"El solapamiento ({solap_fragmento_actual}) debe ser menor que el tamaño del fragmento ({tam_fragmento_actual})."
            )
            registrador.error(mensaje_error_solapamiento)
            raise ValueError(mensaje_error_solapamiento)

        registrador.info(
            f"Dividiendo texto de longitud {len(texto_completo)} caracteres. "
            f"Configuración de fragmentación: Tamaño={tam_fragmento_actual}, Solapamiento={solap_fragmento_actual}."
        )

        if not texto_completo.strip():
            registrador.info("El texto de entrada está vacío o solo contiene espacios. No se generarán fragmentos.")
            return []

        if len(texto_completo) <= tam_fragmento_actual:
            registrador.info("El texto completo es más corto o igual al tamaño del fragmento. Se devuelve como un solo fragmento.")
            return [texto_completo]

        lista_fragmentos: List[str] = []
        indice_inicio_actual = 0
        longitud_total_texto = len(texto_completo)

        while indice_inicio_actual < longitud_total_texto:
            indice_fin_actual = min(indice_inicio_actual + tam_fragmento_actual, longitud_total_texto)
            fragmento_actual = texto_completo[indice_inicio_actual:indice_fin_actual]
            lista_fragmentos.append(fragmento_actual)
            registrador.debug(f"Fragmento generado (índices {indice_inicio_actual}-{indice_fin_actual}): '{fragmento_actual[:50].replace('\n', ' ')}...'")

            if indice_fin_actual == longitud_total_texto:
                break

            paso_siguiente_fragmento = tam_fragmento_actual - solap_fragmento_actual
            indice_inicio_actual += paso_siguiente_fragmento

        registrador.info(f"El texto fue dividido en {len(lista_fragmentos)} fragmentos.")
        return lista_fragmentos

    @staticmethod
    def _contextualizar_texto_fragmento(
        texto_fragmento: str,
        nombre_archivo: Optional[str] = None,
        titulo_documento: Optional[str] = None
    ) -> str:
        """
        Añade información contextual (nombre de archivo, título del documento)
        al inicio de un fragmento de texto. Esta información puede ayudar al modelo
        de embedding a generar representaciones más ricas y específicas.

        Args:
            texto_fragmento: El texto original del fragmento.
            nombre_archivo: Opcional. Nombre del archivo de origen del fragmento.
            titulo_documento: Opcional. Título del documento al que pertenece el fragmento.

        Returns:
            El texto del fragmento con la información contextual prependiada, si se proporcionó.
            Si no se proporciona contexto, devuelve el texto del fragmento original.
        """
        elementos_contexto = []
        if nombre_archivo:
            elementos_contexto.append(f"Fuente del archivo: {nombre_archivo}.")
        if titulo_documento:
            elementos_contexto.append(f"Título del documento: {titulo_documento}.")

        if not elementos_contexto:
            return texto_fragmento

        prefijo_contextual = " ".join(elementos_contexto)
        texto_contextualizado = f"{prefijo_contextual}\n\nContenido del fragmento:\n{texto_fragmento}"
        registrador.debug(f"Contexto añadido al fragmento: '{prefijo_contextual}'")
        return texto_contextualizado

    def generar_embeddings_para_lista_de_textos(
        self,
        lista_de_textos: List[str],
        nombre_modelo_embedding: Optional[str] = None,
        nombre_archivo_origen: Optional[str] = None,
        titulo_documento_origen: Optional[str] = None
    ) -> List[Optional[List[float]]]:
        """
        Genera vectores de embedding para una lista de textos (fragmentos).
        Contextualiza cada texto con el nombre del archivo y título del documento
        antes de generar el embedding. Delega la generación al proveedor de IA configurado.
        Si la generación de un embedding falla para un texto, se guarda un None en su lugar.

        Args:
            lista_de_textos: Lista de strings (fragmentos) para los cuales generar embeddings.
            nombre_modelo_embedding: Opcional. Nombre específico del modelo de embedding a usar.
            nombre_archivo_origen: Opcional. Nombre del archivo de origen para todos los textos en la lista.
            titulo_documento_origen: Opcional. Título del documento de origen para todos los textos en la lista.

        Returns:
            Una lista de embeddings. Cada embedding es una lista de floats.
            Si un embedding falla, se incluye `None` en esa posición.
        """
        if not lista_de_textos:
            registrador.info("Lista de textos vacía, no se generarán embeddings.")
            return []

        registrador.info(f"Iniciando generación de embeddings para {len(lista_de_textos)} textos. Contexto global: Archivo='{nombre_archivo_origen}', Título='{titulo_documento_origen}'.")
        embeddings_generados: List[Optional[List[float]]] = []

        for indice, texto_original_fragmento in enumerate(lista_de_textos):
            registrador.debug(
                f"Procesando texto {indice + 1}/{len(lista_de_textos)} "
                f"(longitud original: {len(texto_original_fragmento)} caracteres) para embedding."
            )
            if not texto_original_fragmento.strip():
                registrador.warning(f"Texto {indice + 1} está vacío o solo contiene espacios. Se omitirá y se guardará None para su embedding.")
                embeddings_generados.append(None)
                continue

            texto_a_embeder = self._contextualizar_texto_fragmento(
                texto_fragmento=texto_original_fragmento,
                nombre_archivo=nombre_archivo_origen,
                titulo_documento=titulo_documento_origen
            )
            if texto_a_embeder != texto_original_fragmento:
                 registrador.debug(f"Texto {indice + 1} contextualizado. Longitud nueva: {len(texto_a_embeder)}.")

            try:
                embedding_actual = self.proveedor_ia.generar_embedding(
                    texto_entrada=texto_a_embeder, # Usar el texto contextualizado
                    nombre_modelo_especifico=nombre_modelo_embedding
                )
                if embedding_actual:
                    embeddings_generados.append(embedding_actual)
                    registrador.debug(f"Embedding generado para texto {indice + 1} (dimensión: {len(embedding_actual)}).")
                else:
                    registrador.warning(f"El proveedor de IA devolvió un embedding vacío/None para el texto contextualizado {indice + 1}. Se guardará None.")
                    embeddings_generados.append(None)
            except ErrorProveedorInteligencia as e_proveedor:
                 registrador.error(f"Error del proveedor de IA al generar embedding para texto {indice + 1}: {e_proveedor}. Se guardará None.")
                 embeddings_generados.append(None)
            except Exception as e_inesperado:
                registrador.exception(
                    f"Falló inesperadamente la generación de embedding para el texto {indice + 1}: {e_inesperado}. "
                    "Se guardará None para su embedding."
                )
                embeddings_generados.append(None)

        num_embeddings_exitosos = sum(1 for emb in embeddings_generados if emb is not None and len(emb) > 0)
        registrador.info(f"Generación de embeddings completada. Éxito para {num_embeddings_exitosos} de {len(lista_de_textos)} textos.")
        return embeddings_generados

    @staticmethod
    def construir_objetos_fragmento_para_bd(
        id_curso: int,
        id_documento: str,
        nombre_archivo_original: str,
        lista_textos_fragmentos: List[str], # Estos son los textos ORIGINALES, SIN CONTEXTO ADICIONAL PARA EMBEDDING
        lista_embeddings_fragmentos: List[Optional[List[float]]],
        titulo_documento: Optional[str] = None,
        metadatos_adicionales_por_fragmento: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> List[modelos_api.FragmentoDocumento]:
        """
        Prepara una lista de objetos `FragmentoDocumento` (modelo Pydantic)
        listos para ser almacenados en la base de datos vectorial.
        Asocia cada fragmento de texto original con su embedding y metadatos.

        Args:
            id_curso: ID del curso al que pertenece el documento.
            id_documento: Identificador único del documento (ej. hash o ID de Moodle).
            nombre_archivo_original: Nombre del archivo del cual provienen los fragmentos.
            lista_textos_fragmentos: Textos originales de los fragmentos (sin el contexto añadido para el embedding).
            lista_embeddings_fragmentos: Lista de embeddings correspondientes a los fragmentos (generados a partir de textos contextualizados).
                                          Puede contener None si algún embedding falló.
            titulo_documento: Opcional. Título del documento.
            metadatos_adicionales_por_fragmento: Opcional. Lista de diccionarios con metadatos
                                                 adicionales para cada fragmento.

        Returns:
            Una lista de instancias `modelos_api.FragmentoDocumento`.
            Los fragmentos sin un embedding válido son omitidos.
        """
        if len(lista_textos_fragmentos) != len(lista_embeddings_fragmentos):
            mensaje_error_longitud = "La cantidad de fragmentos de texto y de embeddings debe ser la misma."
            registrador.error(mensaje_error_longitud)
            raise ValueError(mensaje_error_longitud)

        if metadatos_adicionales_por_fragmento and len(lista_textos_fragmentos) != len(metadatos_adicionales_por_fragmento):
            mensaje_error_longitud_meta = "Si se proveen metadatos opcionales, su cantidad debe coincidir con la de fragmentos de texto."
            registrador.error(mensaje_error_longitud_meta)
            raise ValueError(mensaje_error_longitud_meta)

        registrador.info(f"Preparando {len(lista_textos_fragmentos)} objetos FragmentoDocumento para el documento ID '{id_documento}' del curso ID {id_curso}.")
        fragmentos_listos_para_bd: List[modelos_api.FragmentoDocumento] = []

        for i, texto_fragmento_original in enumerate(lista_textos_fragmentos): # Iterar sobre el texto original
            embedding_actual = lista_embeddings_fragmentos[i]
            if not embedding_actual:
                registrador.warning(f"Fragmento {i+1} ('{texto_fragmento_original[:30].replace('\n',' ')}...') del documento '{id_documento}' no tiene un embedding válido. Se omitirá.")
                continue

            metadatos_base_fragmento = {
                "nombre_archivo_fuente": nombre_archivo_original,
                "numero_fragmento_secuencia": i + 1,
                "longitud_fragmento_caracteres": len(texto_fragmento_original) # Longitud del texto original
            }
            if titulo_documento:
                metadatos_base_fragmento["titulo_documento_asociado"] = titulo_documento

            metadatos_finales_fragmento = metadatos_base_fragmento.copy()
            if metadatos_adicionales_por_fragmento and metadatos_adicionales_por_fragmento[i]:
                metadatos_finales_fragmento.update(metadatos_adicionales_por_fragmento[i]) # type: ignore

            try:
                fragmento_para_bd = modelos_api.FragmentoDocumento(
                    id_curso=id_curso,
                    id_documento=id_documento,
                    texto=texto_fragmento_original, # Guardar el texto original, no el contextualizado
                    embedding=embedding_actual,
                    metadatos=metadatos_finales_fragmento,
                )
                fragmentos_listos_para_bd.append(fragmento_para_bd)
            except Exception as e_modelo_pydantic:
                registrador.error(f"Error al crear objeto FragmentoDocumento para fragmento {i+1} del doc '{id_documento}': {e_modelo_pydantic}")

        registrador.info(f"Se prepararon {len(fragmentos_listos_para_bd)} objetos FragmentoDocumento válidos para la BD.")
        return fragmentos_listos_para_bd
