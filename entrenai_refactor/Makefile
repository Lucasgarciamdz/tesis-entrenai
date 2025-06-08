# Makefile para el Proyecto EntrenAI Refactorizado (dentro de entrenai_refactor/)

# Intérprete de Python por defecto
PYTHON = python3

# Directorio del entorno virtual (dentro de entrenai_refactor)
VENV_DIR = .venv
VENV_ACTIVATE = . $(VENV_DIR)/bin/activate

# Archivos de entorno (dentro de entrenai_refactor)
ENV_FILE_LOCAL = .env
ENV_FILE_DOCKER = .env.docker

# Argumentos para ejecutar FastAPI localmente, leyendo del .env local
# Usamos un truco para leer variables del .env; requiere que las variables NO tengan espacios alrededor del '='
FASTAPI_HOST_LOCAL = $(shell grep -E '^FASTAPI_HOST\s*=' $(ENV_FILE_LOCAL) | cut -d '=' -f2)
FASTAPI_PORT_LOCAL = $(shell grep -E '^FASTAPI_PORT\s*=' $(ENV_FILE_LOCAL) | cut -d '=' -f2)
RUN_ARGS_LOCAL = --host $(FASTAPI_HOST_LOCAL) --port $(FASTAPI_PORT_LOCAL) --reload

# Comprobar si los archivos .env existen y mostrar advertencia si no.
# Esta es una forma simple, make no es ideal para lógica compleja.
check_env_local:
	@if [ ! -f "$(ENV_FILE_LOCAL)" ]; then \
		echo "ADVERTENCIA: Archivo de entorno local '$(ENV_FILE_LOCAL)' no encontrado."; \
		echo "Por favor, copie '.env.example' a '$(ENV_FILE_LOCAL)' y configúrelo para ejecuciones locales."; \
		echo "Algunos comandos podrían no funcionar correctamente."; \
	fi

check_env_docker:
	@if [ ! -f "$(ENV_FILE_DOCKER)" ]; then \
		echo "ADVERTENCIA: Archivo de entorno para Docker '$(ENV_FILE_DOCKER)' no encontrado."; \
		echo "Por favor, copie '.env.example' a '$(ENV_FILE_DOCKER)' y configúrelo para Docker Compose."; \
		echo "El comando 'make levantar-servicios' podría fallar o usar configuraciones por defecto."; \
	fi

.PHONY: ayuda instalar correr-api correr-worker-celery probar limpiar levantar-servicios bajar-servicios logs-servicios reiniciar-servicios levantar-demo

ayuda:
	@echo "Comandos disponibles para el proyecto EntrenAI (desde el directorio entrenai_refactor/):"
	@echo ""
	@echo "  Desarrollo Local:"
	@echo "    instalar                : Crea un entorno virtual '.venv/' e instala las dependencias de 'requirements.txt'."
	@echo "    correr-api              : Ejecuta la aplicación FastAPI localmente (Uvicorn con recarga). Requiere './.env'."
	@echo "    correr-worker-celery    : Ejecuta un worker de Celery localmente. Requiere './.env' y Redis."
	@echo "    probar                  : Ejecuta las pruebas con pytest (si están configuradas)."
	@echo "    limpiar                 : Elimina el entorno virtual y los archivos de caché de Python."
	@echo ""
	@echo "  Gestión de Servicios Docker (usando './docker-compose.yml' y './.env.docker'):"
	@echo "    levantar-servicios      : Inicia todos los servicios definidos en Docker Compose en modo detached (segundo plano)."
	@echo "    bajar-servicios         : Detiene y elimina los contenedores de los servicios de Docker Compose."
	@echo "    logs-servicios          : Muestra los logs en tiempo real de todos los servicios Docker."
	@echo "    reiniciar-servicios     : Reinicia todos los servicios de Docker Compose."
	@echo ""
	@echo "  Otros:"
	@echo "    levantar-demo           : Placeholder para un futuro comando que levante un sistema de demo completo."
	@echo "    ayuda                   : Muestra este mensaje de ayuda."

instalar: $(VENV_DIR)/bin/activate
# Instala dependencias desde requirements.txt y requirements.celery.txt que están en este directorio.
$(VENV_DIR)/bin/activate: requirements.txt requirements.celery.txt
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_ACTIVATE); pip install --upgrade pip
	$(VENV_ACTIVATE); pip install -r requirements.txt
	$(VENV_ACTIVATE); pip install -r requirements.celery.txt
	@echo "Entorno virtual '$(VENV_DIR)' creado y dependencias instaladas."
	@touch $(VENV_DIR)/bin/activate # Actualizar timestamp para make

correr-api: check_env_local $(VENV_DIR)/bin/activate
	@echo "Iniciando la aplicación FastAPI localmente..."
	@echo "Usando host: $(FASTAPI_HOST_LOCAL), puerto: $(FASTAPI_PORT_LOCAL) (de $(ENV_FILE_LOCAL))"
	# PYTHONPATH=. asegura que los módulos locales de entrenai_refactor se encuentren correctamente.
	$(VENV_ACTIVATE); PYTHONPATH=. uvicorn api.principal:aplicacion_fastapi $(RUN_ARGS_LOCAL)

correr-worker-celery: check_env_local $(VENV_DIR)/bin/activate
	@echo "Iniciando worker de Celery localmente..."
	# PYTHONPATH=. para que Celery encuentre los módulos de la aplicación.
	# '-A entrenai_refactor.celery' apunta al __init__.py del paquete celery, que importa 'aplicacion_celery'.
	$(VENV_ACTIVATE); PYTHONPATH=. celery -A entrenai_refactor.celery worker -l INFO -P threads

probar: $(VENV_DIR)/bin/activate
	@echo "Ejecutando pruebas con pytest..."
	$(VENV_ACTIVATE); PYTHONPATH=. pytest tests/
	@echo "Pruebas finalizadas. Revisa la salida para ver los resultados."

limpiar:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@echo "Entorno virtual, archivos __pycache__ y .pytest_cache eliminados."

# Comandos de Docker Compose
# Usan docker-compose.yml y .env.docker en el directorio actual (entrenai_refactor/)
levantar-servicios: check_env_docker
	@echo "Iniciando servicios de Docker definidos en './docker-compose.yml'..."
	@echo "Se utilizará el archivo de entorno './$(ENV_FILE_DOCKER)'."
	docker compose -f docker-compose.yml --env-file $(ENV_FILE_DOCKER) up -d --remove-orphans --build

bajar-servicios:
	@echo "Deteniendo servicios de Docker definidos en './docker-compose.yml'..."
	docker compose -f docker-compose.yml down

logs-servicios:
	@echo "Mostrando logs de los servicios de Docker (presiona Ctrl+C para salir)..."
	docker compose -f docker-compose.yml logs -f

reiniciar-servicios: bajar-servicios levantar-servicios
	@echo "Servicios Docker reiniciados."

levantar-demo: levantar-servicios
	@echo "Sistema de demo (servicios Docker) levantado."
	@echo "Accede a la API en http://localhost:<PUERTO_FASTAPI_HOST> (ver .env.docker)."
	# Aquí se podrían añadir más pasos, como poblar la base de datos con datos de prueba,
	# o abrir un navegador a la interfaz de usuario.
	# Ejemplo: $(PYTHON) -m webbrowser http://localhost:$(shell grep FASTAPI_HOST_PORT $(ENV_FILE_DOCKER) | cut -d '=' -f2)

# Nota: La comprobación explícita de la existencia de .env y .env.docker se hace al inicio de los targets relevantes.
# Esto evita que 'make' falle si los archivos no existen pero el comando no los requiere directamente.
# Por ejemplo, 'make ayuda' no necesita los .env.
