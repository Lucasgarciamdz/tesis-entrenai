from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Response # Añadido Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from entrenai_refactor.api.rutas import ruta_configuracion_curso, ruta_busqueda, ruta_procesamiento_interno
from entrenai_refactor.config.configuracion import configuracion_global
from entrenai_refactor.config.registrador import obtener_registrador

registrador = obtener_registrador(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicio de la aplicación
    registrador.info("Iniciando API de EntrenAI Refactorizado...")
    registrador.info(f"Nivel de log configurado: {configuracion_global.nivel_log}")
    registrador.info(f"Host API configurado: {configuracion_global.host_api}")
    registrador.info(f"Puerto API configurado: {configuracion_global.puerto_api}")

    directorio_estatico = Path(__file__).parent / "estaticos"
    if not directorio_estatico.is_dir():
        registrador.warning(f"Directorio de archivos estáticos NO encontrado en: {directorio_estatico}")
    else:
        registrador.info(f"Directorio de archivos estáticos encontrado en: {directorio_estatico}")

    yield

    # Cierre de la aplicación
    registrador.info("Cerrando API de EntrenAI Refactorizado...")

# Instancia de la aplicación FastAPI
aplicacion = FastAPI(
    title="API de EntrenAI Refactorizado",
    description="API en español para la gestión de inteligencia artificial personalizada para cursos en Moodle, utilizando FastAPI.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configuración del Middleware CORS
aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# --- Endpoints Raíz ---

@aplicacion.get("/", summary="Endpoint Raíz", description="Mensaje de bienvenida de la API.")
async def leer_raiz():
    registrador.info("Endpoint raíz '/' fue accedido.")
    return {"mensaje": "¡Bienvenido/a a la API de EntrenAI Refactorizado!"}

@aplicacion.get("/salud", summary="Chequeo de Salud", description="Verifica el estado de salud de la API.")
async def verificacion_salud():
    registrador.debug("Endpoint de salud '/salud' fue accedido.")
    return {"estado": "saludable"}

@aplicacion.get("/favicon.ico", include_in_schema=False)
async def obtener_favicon():
    ruta_favicon = Path(__file__).parent / "estaticos" / "favicon.ico"
    if ruta_favicon.is_file():
        return FileResponse(ruta_favicon)
    else:
        registrador.debug("Solicitud de favicon.ico, pero no se encontró el archivo.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Inclusión de Enrutadores (Routers) ---
registrador.info("Incluyendo enrutadores de la API...")
aplicacion.include_router(ruta_configuracion_curso.enrutador)
aplicacion.include_router(ruta_busqueda.enrutador)
aplicacion.include_router(ruta_procesamiento_interno.enrutador)
registrador.info("Enrutadores incluidos exitosamente.")

# --- Montaje de Archivos Estáticos ---
directorio_estatico_api = Path(__file__).parent / "estaticos"
if directorio_estatico_api.is_dir():
    aplicacion.mount(
        "/interfaz",
        StaticFiles(directory=str(directorio_estatico_api), html=True),
        name="interfaz_usuario"
    )
    registrador.info(f"Archivos estáticos montados desde '{directorio_estatico_api}' en la ruta '/interfaz'.")
else:
    registrador.warning(
        f"Directorio de archivos estáticos '{directorio_estatico_api}' no encontrado. "
        "La interfaz de usuario web no estará disponible."
    )

# --- Bloque para Ejecución Directa (para desarrollo) ---
if __name__ == "__main__":
    import uvicorn
    registrador.info("Ejecutando Uvicorn para desarrollo...")

    uvicorn.run(
        "entrenai_refactor.api.principal:aplicacion",
        host=configuracion_global.host_api,
        port=configuracion_global.puerto_api,
        log_level=configuracion_global.nivel_log.lower(),
        reload=True
    )
[end of entrenai_refactor/api/principal.py]
