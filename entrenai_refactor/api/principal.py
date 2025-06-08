from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Importar los enrutadores refactorizados desde el paquete de rutas
from entrenai_refactor.api.rutas import (
    enrutador_config_curso,
    enrutador_busqueda,
    enrutador_procesamiento_interno
)
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

@asynccontextmanager
async def ciclo_vida_aplicacion(app: FastAPI): # Nombre de función traducido
    # Lógica de inicio de la aplicación
    registrador.info("Iniciando la API de EntrenAI (versión refactorizada)...")
    registrador.info(f"Nivel de registro (log level) configurado: {configuracion_global.nivel_registro_log}") # CAMBIADO
    registrador.info(f"Host para la API configurado: {configuracion_global.host_api_fastapi}") # CAMBIADO
    registrador.info(f"Puerto para la API configurado: {configuracion_global.puerto_api_fastapi}") # CAMBIADO

    directorio_para_archivos_estaticos = Path(__file__).parent / "estaticos" # Variable traducida
    if not directorio_para_archivos_estaticos.is_dir():
        registrador.warning(f"El directorio de archivos estáticos NO fue encontrado en la ruta: {directorio_para_archivos_estaticos}")
    else:
        registrador.info(f"Directorio de archivos estáticos encontrado en: {directorio_para_archivos_estaticos}")

    yield

    # Lógica de cierre de la aplicación
    registrador.info("Cerrando la API de EntrenAI (versión refactorizada)...")

# Instancia de la aplicación FastAPI
aplicacion_fastapi = FastAPI( # Variable traducida
    title="API de EntrenAI", # Título ya en español
    description="API para la gestión de inteligencia artificial personalizada para cursos en Moodle, desarrollada con FastAPI.", # Descripción ya en español
    version="1.1.0", # Versión actualizada para reflejar refactorización
    lifespan=ciclo_vida_aplicacion, # Usar función de ciclo de vida traducida
)

# Configuración del Middleware CORS (Cross-Origin Resource Sharing)
# NOTA: 'allow_origins=["*"]' es permisivo. Para producción, restringir a dominios específicos.
registrador.info("Configurando middleware CORS con orígenes permitidos: ['*'] (permisivo para desarrollo).")
aplicacion_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir todos los orígenes (considerar restringir en producción)
    allow_credentials=True, # Permitir credenciales (cookies, encabezados de autorización)
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], # Métodos HTTP permitidos
    allow_headers=["*"], # Permitir todos los encabezados
)

# --- Endpoints Raíz de la Aplicación ---

@aplicacion_fastapi.get("/",
                         summary="Endpoint Raíz de la API",
                         description="Proporciona un mensaje de bienvenida y confirma que la API está en funcionamiento.")
async def leer_endpoint_raiz(): # Nombre de función traducido
    registrador.info("Endpoint raíz '/' fue accedido.")
    return {"mensaje": "¡Bienvenido/a a la API de EntrenAI!"}

@aplicacion_fastapi.get("/salud",
                         summary="Verificación de Estado de Salud",
                         description="Endpoint simple para verificar el estado operativo y la salud general de la API.")
async def realizar_verificacion_de_salud(): # Nombre de función traducido
    registrador.debug("Endpoint de verificación de salud '/salud' fue accedido.")
    return {"estado_api": "saludable", "mensaje": "La API de EntrenAI está operativa."}

@aplicacion_fastapi.get("/favicon.ico", include_in_schema=False) # Mantener ruta, no incluir en OpenAPI
async def obtener_icono_favicon(): # Nombre de función traducido
    ruta_archivo_favicon = Path(__file__).parent / "estaticos" / "favicon.ico"
    if ruta_archivo_favicon.is_file():
        registrador.debug("Sirviendo archivo favicon.ico.")
        return FileResponse(ruta_archivo_favicon)
    else:
        registrador.debug("Solicitud de favicon.ico, pero el archivo no fue encontrado. Devolviendo 204 No Content.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Inclusión de los diferentes Enrutadores (Routers) de la API ---
registrador.info("Incluyendo enrutadores específicos de la API en la aplicación principal...")
aplicacion_fastapi.include_router(enrutador_config_curso) # Usar variable importada
aplicacion_fastapi.include_router(enrutador_busqueda)     # Usar variable importada
aplicacion_fastapi.include_router(enrutador_procesamiento_interno) # Usar variable importada
registrador.info("Todos los enrutadores específicos han sido incluidos exitosamente.")

# --- Montaje de Archivos Estáticos para la Interfaz de Usuario (si existe) ---
directorio_estatico_api_principal = Path(__file__).parent / "estaticos" # Variable traducida
if directorio_estatico_api_principal.is_dir():
    aplicacion_fastapi.mount(
        "/interfaz", # Ruta base para acceder a los archivos estáticos
        StaticFiles(directory=str(directorio_estatico_api_principal), html=True), # Servir index.html en la raíz
        name="interfaz_usuario_estatica" # Nombre para referencia interna (traducido)
    )
    registrador.info(f"Archivos estáticos montados desde '{directorio_estatico_api_principal}' en la ruta URL '/interfaz'.")
else:
    registrador.warning(
        f"El directorio de archivos estáticos '{directorio_estatico_api_principal}' no fue encontrado. "
        "La interfaz de usuario web simple (si existe) no estará disponible a través de la API."
    )

# --- Bloque para Ejecución Directa de la Aplicación (principalmente para desarrollo) ---
if __name__ == "__main__":
    import uvicorn
    registrador.info("Iniciando servidor Uvicorn para desarrollo directamente desde principal.py...")

    # Usar configuración global para host, puerto y nivel de log
    uvicorn.run(
        "entrenai_refactor.api.principal:aplicacion_fastapi", # Ruta al objeto de la aplicación FastAPI
        host=configuracion_global.host_api_fastapi, # CAMBIADO
        port=configuracion_global.puerto_api_fastapi, # CAMBIADO
        log_level=configuracion_global.nivel_registro_log.lower(), # CAMBIADO # Uvicorn espera minúsculas para log_level
        reload=True # Habilitar recarga automática en cambios (solo para desarrollo)
    )
[end of entrenai_refactor/api/principal.py]
