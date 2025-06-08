from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Importaciones directas para evitar importaciones circulares potenciales
import entrenai2.api.rutas.configuracion_curso as configuracion_curso
import entrenai2.api.rutas.busqueda as busqueda
import entrenai2.api.rutas.procesamiento_interno as procesamiento_interno
from entrenai2.configuracion.configuracion import configuracion_base
from entrenai2.configuracion.registrador import obtener_registrador

# Inicializar el registrador para este módulo
registrador = obtener_registrador(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicio
    registrador.info("Iniciando API de Entrenai...")
    registrador.info(f"Nivel de log configurado en: {configuracion_base.nivel_log}")
    registrador.info(f"Host de FastAPI: {configuracion_base.host_fastapi}")
    registrador.info(f"Puerto de FastAPI: {configuracion_base.puerto_fastapi}")
    
    # Verificar que el directorio estático existe
    directorio_estatico = Path(__file__).parent / "estaticos"
    if not directorio_estatico.exists():
        registrador.warning(f"Directorio estático no encontrado en: {directorio_estatico}")
    else:
        registrador.info(f"Directorio estático encontrado en: {directorio_estatico}")
    
    yield

    # Cierre
    registrador.info("Cerrando API de Entrenai...")


# Inicializar la aplicación FastAPI
aplicacion = FastAPI(
    title="API de Entrenai",
    description="API para el sistema Entrenai, integrando Moodle, PgVector, Ollama y N8N.",
    version="0.1.0",
    lifespan=lifespan,
)

# Configuración de CORS
aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@aplicacion.get("/")
async def leer_raiz():
    registrador.info("Endpoint raíz '/' fue llamado.")
    return {"message": "¡Bienvenido a la API de Entrenai!"}


@aplicacion.get("/salud")
async def verificacion_salud():
    registrador.debug("Endpoint de estado '/salud' fue llamado.")
    return {"estado": "saludable"}


@aplicacion.get("/favicon.ico")
async def favicon():
    ruta_favicon = Path("entrenai2/api/estaticos/favicon.ico")
    return FileResponse(ruta_favicon) if ruta_favicon.exists() else {"detail": "No favicon"}


# Incluir enrutadores
aplicacion.include_router(configuracion_curso.enrutador)
aplicacion.include_router(busqueda.enrutador)
aplicacion.include_router(procesamiento_interno.enrutador)

# Montar archivos estáticos con ruta absoluta
directorio_estatico = Path(__file__).parent / "estaticos"
if directorio_estatico.exists():
    aplicacion.mount("/ui", StaticFiles(directory=str(directorio_estatico), html=True), name="estaticos")
    registrador.info(f"Archivos estáticos montados desde: {directorio_estatico}")
else:
    registrador.warning(f"Directorio estático no encontrado: {directorio_estatico}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "entrenai2.api.main:aplicacion",
        host=configuracion_base.host_fastapi,
        port=configuracion_base.puerto_fastapi,
        log_level=configuracion_base.nivel_log.lower(),
        reload=True,
    )
