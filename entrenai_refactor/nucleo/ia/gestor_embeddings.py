import uuid
from typing import List, Optional, Dict, Any

from entrenai_refactor.api import modelos as modelos_api
from entrenai_refactor.config.registrador import obtener_registrador
from entrenai_refactor.nucleo.ia.proveedor_inteligencia import ProveedorInteligencia

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
    Incluye la división de texto en fragmentos (chunking), la adición de contexto a estos
    fragmentos (opcional), y la generación de los vectores de embedding a través
    de un proveedor de inteligencia artificial configurado.
    """

    def __init__(
        self,
        proveedor_ia_configurado: ProveedorInteligencia,
        tamano_fragmento_predeterminado: int = 1000,  # En número de caracteres
        solapamiento_fragmento_predeterminado: int = 150,  # En número de caracteres
    ):
        """
        Inicializa el GestorEmbeddings.

        Args:
            proveedor_ia_configurado: Instancia del ProveedorInteligencia ya inicializado.
            tamano_fragmento_predeterminado: Tamaño por defecto para dividir el texto.
            solapamiento_fragmento_predeterminado: Solapamiento por defecto entre fragmentos.
        """
        self.proveedor_ia = proveedor_ia_configurado
        self.tamano_fragmento_predeterminado = tamano_fragmento_predeterminado
        self.solapamiento_fragmento_predeterminado = solapamiento_fragmento_predeterminado
        registrador.info(
            f"GestorEmbeddings inicializado. Tamaño de fragmento predeterminado: {tamano_fragmento_predeterminado} caracteres, "
            f"Solapamiento predeterminado: {solapamiento_fragmento_predeterminado} caracteres."
        )

    def dividir_texto_en_fragmentos(
        self,
        texto_completo: str,
        tamano_max_fragmento: Optional[int] = None, # Permitir override del tamaño
        solapamiento_entre_fragmentos: Optional[int] = None, # Permitir override del solapamiento
    ) -> List[str]:
        """
        Divide un texto largo en fragmentos (chunks) más pequeños y manejables.
        Actualmente utiliza una lógica simple de división basada en caracteres.
        """
        tam_fragmento_actual = tamano_max_fragmento or self.tamano_fragmento_predeterminado
        solap_fragmento_actual = solapamiento_entre_fragmentos or self.solapamiento_fragmento_predeterminado

        if not isinstance(texto_completo, str):
            registrador.error(f"Se esperaba un string para dividir, pero se recibió {type(texto_completo)}.")
            # Podría lanzar un TypeError o devolver lista vacía según política de errores.
            return []

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

        if not texto_completo.strip(): # Si el texto está vacío o solo espacios en blanco
            registrador.info("El texto de entrada está vacío o solo contiene espacios. No se generarán fragmentos.")
            return []

        # Si el texto es más corto o igual al tamaño del fragmento, no necesita división.
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
            registrador.debug(f"Fragmento generado (índices {indice_inicio_actual}-{indice_fin_actual}): '{fragmento_actual[:50]}...'")

            # Si el final del fragmento actual es el final del texto, hemos terminado.
            if indice_fin_actual == longitud_total_texto:
                break

            # Mover el índice de inicio para el siguiente fragmento, aplicando el solapamiento.
            avance_para_siguiente_fragmento = tam_fragmento_actual - solap_fragmento_actual
            if avance_para_siguiente_fragmento <= 0:
                # Esta condición no debería alcanzarse si la validación de solapamiento funciona,
                # pero es una salvaguarda contra bucles infinitos.
                registrador.critical("El avance calculado para el siguiente fragmento es cero o negativo. Deteniendo la fragmentación.")
                break
            indice_inicio_actual += avance_para_siguiente_fragmento

        registrador.info(f"El texto fue dividido en {len(lista_fragmentos)} fragmentos.")
        return lista_fragmentos

    @staticmethod
    def _contextualizar_fragmento_individual( # Renombrado para indicar que es para un solo fragmento
        texto_del_fragmento: str,
        titulo_del_documento: Optional[str] = None,
        nombre_del_archivo_fuente: Optional[str] = None,
        # metadatos_adicionales_fragmento: Optional[Dict[str, Any]] = None, # No se usa en esta implementación simple
    ) -> str:
        """
        Añade información contextual simple (como nombre de archivo y título)
        al inicio de un fragmento de texto.
        """
        elementos_de_contexto = []
        if nombre_del_archivo_fuente:
            elementos_de_contexto.append(f"Nombre del Archivo Original: {nombre_del_archivo_fuente}")
        if titulo_del_documento:
            elementos_de_contexto.append(f"Título del Documento Asociado: {titulo_del_documento}")

        prefijo_contextual = "\n".join(elementos_de_contexto)

        if prefijo_contextual:
            # Devuelve el fragmento con el contexto añadido al principio.
            fragmento_contextualizado = f"{prefijo_contextual}\n\n--- Inicio del Contenido del Fragmento ---\n{texto_del_fragmento}\n--- Fin del Contenido del Fragmento ---"
            registrador.debug(f"Contexto añadido al fragmento. Prefijo: '{prefijo_contextual}'.")
            return fragmento_contextualizado
        else:
            # Si no hay contexto para añadir, devuelve el fragmento original.
            registrador.debug("No se añadió contexto adicional al fragmento (sin metadatos provistos).")
            return texto_del_fragmento

    def generar_embeddings_para_lista_de_fragmentos(
        self,
        lista_de_textos_fragmentados: List[str],
        nombre_modelo_embedding: Optional[str] = None
    ) -> List[Optional[List[float]]]: # La lista puede contener None si un embedding falla
        """
        Genera vectores de embedding para una lista de fragmentos de texto.
        Delega la generación al proveedor de IA configurado (Ollama o Gemini).
        Si la generación de un embedding falla, se guarda un None en su lugar.
        """
        if not lista_de_textos_fragmentados:
            registrador.info("Lista de fragmentos vacía, no se generarán embeddings.")
            return []

        registrador.info(f"Iniciando generación de embeddings para {len(lista_de_textos_fragmentados)} fragmentos de texto.")
        embeddings_generados: List[Optional[List[float]]] = []

        for indice, texto_fragmento_actual in enumerate(lista_de_textos_fragmentados):
            registrador.debug(
                f"Procesando fragmento {indice + 1}/{len(lista_de_textos_fragmentados)} "
                f"(longitud: {len(texto_fragmento_actual)} caracteres) para embedding."
            )
            if not texto_fragmento_actual.strip():
                registrador.warning(f"Fragmento {indice + 1} está vacío o solo contiene espacios. Se omitirá y se guardará None para su embedding.")
                embeddings_generados.append(None)
                continue
            try:
                # Llama al método del ProveedorInteligencia, que internamente usa el envoltorio activo (Ollama o Gemini)
                embedding_actual = self.proveedor_ia.generar_embedding(texto=texto_fragmento_actual, modelo=nombre_modelo_embedding)
                if embedding_actual:
                    embeddings_generados.append(embedding_actual)
                    registrador.debug(f"Embedding generado para fragmento {indice + 1} (dimensión: {len(embedding_actual)}).")
                else: # Si el proveedor devuelve None o lista vacía por alguna razón
                    registrador.warning(f"El proveedor de IA devolvió un embedding vacío/None para el fragmento {indice + 1}. Se guardará None.")
                    embeddings_generados.append(None)
            except ErrorGestorEmbeddings as e_gestor: # Si el proveedor lanza nuestra propia excepción
                 registrador.error(f"Error del gestor de embeddings al procesar fragmento {indice + 1}: {e_gestor}. Se guardará None para su embedding.")
                 embeddings_generados.append(None)
            except Exception as e_inesperado: # Captura cualquier otra excepción del proveedor o subyacente
                registrador.error(
                    f"Falló la generación de embedding para el fragmento {indice + 1}: {e_inesperado}. "
                    "Se guardará None para su embedding."
                )
                embeddings_generados.append(None)

        num_embeddings_exitosos = sum(1 for emb in embeddings_generados if emb is not None and len(emb) > 0)
        registrador.info(f"Generación de embeddings completada. Éxito para {num_embeddings_exitosos} de {len(lista_de_textos_fragmentados)} fragmentos.")
        return embeddings_generados

    @staticmethod
    def construir_objetos_fragmento_para_bd(
        id_del_curso: int,
        id_del_documento: str, # Identificador único del documento (ej. hash o ID de Moodle)
        nombre_archivo_original: str,
        titulo_del_documento: Optional[str],
        lista_textos_fragmentos: List[str], # Textos originales de los fragmentos (no contextualizados)
        lista_embeddings_fragmentos: List[Optional[List[float]]],
        lista_metadatos_opcionales_por_fragmento: Optional[List[Optional[Dict[str, Any]]]] = None,
    ) -> List[modelos_api.FragmentoDocumento]:
        """
        Prepara una lista de objetos `FragmentoDocumento` (modelo Pydantic)
        listos para ser almacenados en la base de datos vectorial.
        Asocia cada fragmento de texto con su embedding y metadatos correspondientes.
        """
        if len(lista_textos_fragmentos) != len(lista_embeddings_fragmentos):
            mensaje_error_longitud1 = "La cantidad de fragmentos de texto y de embeddings debe ser la misma."
            registrador.error(mensaje_error_longitud1)
            raise ValueError(mensaje_error_longitud1)

        if lista_metadatos_opcionales_por_fragmento and len(lista_textos_fragmentos) != len(lista_metadatos_opcionales_por_fragmento):
            mensaje_error_longitud2 = "Si se proveen metadatos opcionales, su cantidad debe coincidir con la de fragmentos de texto."
            registrador.error(mensaje_error_longitud2)
            raise ValueError(mensaje_error_longitud2)

        registrador.info(f"Preparando {len(lista_textos_fragmentos)} objetos FragmentoDocumento para el documento ID '{id_del_documento}' del curso ID {id_del_curso}.")
        fragmentos_listos_para_bd: List[modelos_api.FragmentoDocumento] = []

        for i, texto_fragmento_actual in enumerate(lista_textos_fragmentos):
            embedding_actual = lista_embeddings_fragmentos[i]
            if embedding_actual is None or not embedding_actual: # Si el embedding es None o lista vacía
                registrador.warning(f"Fragmento {i+1} del documento '{id_del_documento}' no tiene un embedding válido. Se omitirá su preparación para la BD.")
                continue # Omitir este fragmento

            # Construir metadatos base para este fragmento
            metadatos_completos_fragmento = {
                "nombre_archivo_fuente": nombre_archivo_original,
                "numero_fragmento": i + 1, # Añadir número de secuencia del fragmento
                "longitud_fragmento_caracteres": len(texto_fragmento_actual)
            }
            if titulo_del_documento:
                metadatos_completos_fragmento["titulo_documento_asociado"] = titulo_del_documento

            # Añadir metadatos específicos del fragmento si se proporcionaron
            if lista_metadatos_opcionales_por_fragmento and lista_metadatos_opcionales_por_fragmento[i]:
                metadatos_completos_fragmento.update(lista_metadatos_opcionales_por_fragmento[i]) # type: ignore

            # Crear el objeto Pydantic. El id_fragmento se generará automáticamente por el modelo si no se provee.
            try:
                fragmento_para_bd = modelos_api.FragmentoDocumento(
                    id_curso=id_del_curso,
                    id_documento=id_del_documento,
                    texto=texto_fragmento_actual, # Texto original del fragmento
                    embedding=embedding_actual,
                    metadatos=metadatos_completos_fragmento,
                )
                fragmentos_listos_para_bd.append(fragmento_para_bd)
            except Exception as e_modelo: # Captura errores de validación de Pydantic
                registrador.error(f"Error al crear objeto FragmentoDocumento para fragmento {i+1} del doc '{id_del_documento}': {e_modelo}")
                # Decidir si continuar con otros fragmentos o fallar todo el proceso. Por ahora, se omite el fragmento.

        registrador.info(f"Se prepararon {len(fragmentos_listos_para_bd)} objetos FragmentoDocumento válidos para la BD.")
        return fragmentos_listos_para_bd

[end of entrenai_refactor/nucleo/ia/gestor_embeddings_refactorizado.py]
