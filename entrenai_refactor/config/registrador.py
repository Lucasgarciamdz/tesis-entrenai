import logging
import sys

# Importar la instancia de configuración global del módulo de configuración refactorizado.
# Asegurarse de que el nombre del campo para el nivel de log coincida con el refactorizado.
from entrenai_refactor.config.configuracion import configuracion_global

# Nombre base para los loggers de la aplicación, podría usarse para filtrado o configuración jerárquica.
# No se usa directamente en obtener_registrador, pero es una buena práctica definirlo.
NOMBRE_BASE_REGISTRADOR_APP = "entrenai_refactor"

def obtener_registrador(nombre_modulo: str) -> logging.Logger:
    """
    Configura y devuelve una instancia de registrador (logger) para un módulo específico
    dentro de la aplicación EntrenAI.

    Esta función asegura que todos los registradores generados para la aplicación
    compartan una configuración de logging consistente (formato, nivel, manejador de salida),
    basada en las variables definidas en el objeto `configuracion_global`.

    Args:
        nombre_modulo: El nombre del registrador, que típicamente debería ser el valor
                       de `__name__` del módulo que invoca esta función. Esto ayuda
                       a identificar el origen de los mensajes de log.

    Returns:
        Una instancia de `logging.Logger` debidamente configurada.
    """
    # Construir un nombre jerárquico para el logger si se desea, ej: "entrenai_refactor.modulo.submodulo"
    # Esto permite configuraciones más granulares por jerarquía si es necesario en el futuro.
    # Por ahora, se usa el nombre_modulo directamente.
    registrador_modulo = logging.getLogger(nombre_modulo)

    # Evitar añadir manejadores (handlers) duplicados si el registrador ya fue configurado previamente.
    # Esto es crucial para no tener múltiples salidas del mismo mensaje de log.
    if not registrador_modulo.handlers:
        # Establecer el nivel de log para este registrador desde la configuración global.
        # Usar el nombre de campo refactorizado: nivel_registro_log.
        nivel_log_configurado_str = configuracion_global.nivel_registro_log.upper()
        nivel_log_numerico = logging.getLevelName(nivel_log_configurado_str) # Convertir string a int (ej. "INFO" a 20)
        registrador_modulo.setLevel(nivel_log_numerico)

        # Crear un manejador (handler) para enviar los logs a la consola (salida estándar, stdout).
        manejador_consola = logging.StreamHandler(sys.stdout)
        # Establecer el nivel de log también para el manejador; usualmente el mismo que el logger.
        manejador_consola.setLevel(nivel_log_numerico)

        # Definir el formato de los mensajes de log para que sea informativo.
        formato_log = logging.Formatter(
            "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s (Archivo: %(filename)s, Línea: %(lineno)d)"
        )
        manejador_consola.setFormatter(formato_log)

        # Añadir el manejador configurado al registrador.
        registrador_modulo.addHandler(manejador_consola)

        # Configuración de la propagación de logs:
        # Si se establece a False, los logs de este registrador no se pasarán a los
        # manejadores de los registradores de nivel superior (ej. el registrador raíz de logging).
        # Para la mayoría de los casos de uso de una aplicación, es bueno dejarlo como True (valor por defecto)
        # o gestionarlo explícitamente si hay una jerarquía de loggers compleja y se quiere evitar duplicación
        # si el logger raíz también está configurado para escribir en consola.
        # Por simplicidad y para asegurar que los logs aparezcan al menos una vez, se puede dejar en True
        # si el logger raíz no tiene manejadores que dupliquen la salida.
        # registrador_modulo.propagate = False

    # Devolver el registrador configurado (o previamente configurado).
    return registrador_modulo

# Ejemplo de cómo silenciar o ajustar el nivel de log de una librería de terceros muy verbosa:
# logging.getLogger("nombre_libreria_ruidosa").setLevel(logging.WARNING)
# Esto se haría preferiblemente una sola vez al inicio de la aplicación, por ejemplo, aquí o en principal.py.

[end of entrenai_refactor/config/registrador.py]
