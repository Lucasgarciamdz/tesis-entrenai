from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Response # HTTPException y status no se usan directamente aquí, pero Response sí.
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Importar los enrutadores (routers) desde el paquete de rutas de la API
from entrenai_refactor.api.rutas import (
    enrutador_config_curso,
    enrutador_busqueda,
    enrutador_procesamiento_interno
)
from entrenai_refactor.config.configuracion import configuracion_global # Configuración global de la aplicación
from entrenai_refactor.config.registrador import obtener_registrador # Sistema de logging

registrador = obtener_registrador(__name__) # Registrador específico para este módulo (principal.py)

@asynccontextmanager
async def ciclo_vida_app(app: FastAPI): # Nombre de la función y parámetro 'app' son convencionales en FastAPI
    """
    Context manager para manejar el ciclo de vida de la aplicación FastAPI.
    Se ejecuta al iniciar y finalizar la aplicación.
    """
    # Lógica de inicio de la aplicación
    registrador.info("Iniciando la API de EntrenAI (versión refactorizada)...")
    registrador.info(f"Configuración de Logging: Nivel={configuracion_global.nivel_registro_log}")
    registrador.info(f"Configuración de API: Host={configuracion_global.host_api_fastapi}, Puerto={configuracion_global.puerto_api_fastapi}")

    # Verificar y loguear la existencia del directorio de archivos estáticos
    directorio_archivos_estaticos = Path(__file__).parent / "estaticos"
    if not directorio_archivos_estaticos.is_dir():
        registrador.warning(f"El directorio de archivos estáticos ('{directorio_archivos_estaticos}') NO fue encontrado. La interfaz web simple no estará disponible.")
    else:
        registrador.info(f"Directorio de archivos estáticos encontrado en: '{directorio_archivos_estaticos}'.")

    yield # Punto donde la aplicación se ejecuta

    # Lógica de cierre de la aplicación
    registrador.info("Cerrando la API de EntrenAI (versión refactorizada)...")
    # Aquí se podrían añadir tareas de limpieza si fueran necesarias (ej. cerrar conexiones a BD si no se manejan por petición)

# Instancia principal de la aplicación FastAPI. Cambiado a 'aplicacion' para consistencia.
aplicacion = FastAPI(
    title="API de EntrenAI",
    description="API para la gestión de inteligencia artificial personalizada para cursos en Moodle, desarrollada con FastAPI.",
    version="1.1.0", # Versión que podría reflejar la refactorización
    lifespan=ciclo_vida_app, # Usar la función de ciclo de vida definida
    # Se podrían añadir otros metadatos de OpenAPI aquí (contact, license_info, etc.)
)

# Configuración del Middleware CORS (Cross-Origin Resource Sharing)
# NOTA: 'allow_origins=["*"]' es muy permisivo. Para producción, se debe restringir a dominios específicos.
registrador.info("Configurando middleware CORS con orígenes permitidos: ['*'] (permisivo, ideal para desarrollo). Considerar restringir en producción.")
aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir todos los orígenes (ej. para desarrollo local con diferentes puertos)
    allow_credentials=True, # Permitir el envío de credenciales (cookies, encabezados de autorización)
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], # Métodos HTTP permitidos
    allow_headers=["*"], # Permitir todos los encabezados en las peticiones
)

# --- Endpoints Raíz y de Utilidad de la Aplicación ---

@aplicacion.get("/",
                summary="Endpoint Raíz de la API de EntrenAI",
                description="Proporciona un mensaje de bienvenida y confirma que la API está en funcionamiento y accesible.")
async def obtener_mensaje_bienvenida_raiz(): # Nombre de función más descriptivo
    """Devuelve un mensaje de bienvenida para la API."""
    registrador.info("Endpoint raíz '/' fue accedido exitosamente.")
    return {"mensaje": "¡Bienvenido/a a la API de EntrenAI! El sistema está operativo."}

@aplicacion.get("/estado_salud", # Ruta en español
                summary="Verificación de Estado de Salud de la API",
                description="Endpoint simple para verificar el estado operativo y la salud general de la API. Útil para monitoreo.")
async def verificar_estado_salud_api(): # Nombre de función más descriptivo
    """Devuelve el estado de salud de la API."""
    registrador.debug("Endpoint de verificación de salud '/estado_salud' fue accedido.")
    return {"estado_api": "saludable", "mensaje": "La API de EntrenAI se encuentra operativa."}

@aplicacion.get("/favicon.ico", include_in_schema=False) # No incluir en la documentación de OpenAPI
async def obtener_icono_favicon_app(): # Nombre de función más descriptivo
    """Sirve el archivo favicon.ico si existe en el directorio de estáticos."""
    ruta_archivo_favicon_estatico = Path(__file__).parent / "estaticos" / "favicon.ico"
    if ruta_archivo_favicon_estatico.is_file():
        registrador.debug("Sirviendo archivo favicon.ico desde directorio de estáticos.")
        return FileResponse(ruta_archivo_favicon_estatico)
    else:
        # Si no hay favicon, devolver No Content para evitar errores en el navegador
        registrador.debug("Solicitud de favicon.ico, pero el archivo no fue encontrado en estáticos. Devolviendo 204 No Content.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Inclusión de los diferentes Enrutadores (Routers) de la API ---
# Cada enrutador agrupa endpoints relacionados con una funcionalidad específica.
registrador.info("Incluyendo enrutadores específicos de la API en la aplicación principal...")
aplicacion.include_router(enrutador_config_curso, prefix="/configuracion", tags=["Configuración de Cursos"])
aplicacion.include_router(enrutador_busqueda, prefix="/busqueda", tags=["Búsqueda Semántica"])
aplicacion.include_router(enrutador_procesamiento_interno, prefix="/sistema", tags=["Procesamiento Interno y Tareas"])
registrador.info("Todos los enrutadores específicos han sido incluidos y configurados con sus prefijos y etiquetas.")

# --- Montaje de Archivos Estáticos (para una posible Interfaz de Usuario web simple) ---
# Esto permite servir archivos HTML, CSS, JS desde un directorio 'estaticos' en la misma API.
directorio_estatico_para_interfaz = Path(__file__).parent / "estaticos"
if directorio_estatico_para_interfaz.is_dir():
    aplicacion.mount(
        "/interfaz_usuario", # Ruta base para acceder a los archivos estáticos (ej. http://localhost:8000/interfaz_usuario/index.html)
        StaticFiles(directory=str(directorio_estatico_para_interfaz), html=True), # Sirve index.html en la raíz de esta ruta montada
        name="interfaz_usuario_estatica" # Nombre para referencia interna en FastAPI
    )
    registrador.info(f"Archivos estáticos para interfaz de usuario montados desde '{directorio_estatico_para_interfaz}' en la ruta URL '/interfaz_usuario'.")
else:
    registrador.warning(
        f"El directorio de archivos estáticos para la interfaz de usuario ('{directorio_estatico_para_interfaz}') no fue encontrado. "
        "La interfaz web simple (si se esperaba) no estará disponible a través de la API."
    )

# --- Bloque para Ejecución Directa de la Aplicación (principalmente para desarrollo local) ---
# Este bloque permite ejecutar la API directamente con Uvicorn usando 'python principal.py'.
if __name__ == "__main__":
    import uvicorn # Servidor ASGI para FastAPI
    registrador.info("Iniciando servidor Uvicorn para desarrollo directamente desde el script principal.py...")

    # Usar configuración global para host, puerto y nivel de log definidos en el archivo de configuración.
    uvicorn.run(
        "entrenai_refactor.api.principal:aplicacion", # Ruta al objeto de la aplicación FastAPI (ahora 'aplicacion')
        host=configuracion_global.host_api_fastapi,
        port=configuracion_global.puerto_api_fastapi,
        log_level=configuracion_global.nivel_registro_log.lower(), # Uvicorn espera el nivel de log en minúsculas
        reload=True # Habilitar recarga automática en cambios de código (solo para desarrollo)
        # Se podrían añadir más opciones de Uvicorn aquí si es necesario (ej. workers, ssl_keyfile)
    )
[end of entrenai_refactor/api/principal.py]
