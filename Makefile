# Makefile para el Proyecto Entrenai

# Intérprete de Python por defecto
PYTHON = python3

# Directorio del entorno virtual
VENV_DIR = .venv
VENV_ACTIVATE = . $(VENV_DIR)/bin/activate

# Argumentos por defecto para ejecutar FastAPI
RUN_ARGS = --host $(shell grep FASTAPI_HOST .env | cut -d '=' -f2) --port $(shell grep FASTAPI_PORT .env | cut -d '=' -f2) --reload

.PHONY: ayuda instalar correr probar limpiar servicios-levantar servicios-bajar servicios-logs servicios-reiniciar correr-worker-celery prueba

ayuda:
	@echo "Comandos disponibles:"
	@echo "  instalar         : Crea un entorno virtual e instala las dependencias"
	@echo "  correr           : Ejecuta la aplicación FastAPI"
	@echo "  probar           : Ejecuta las pruebas con pytest"
	@echo "  limpiar          : Elimina el entorno virtual y los archivos de caché"
	@echo "  servicios-levantar: Inicia los servicios de Docker Compose en modo detached"
	@echo "  servicios-bajar  : Detiene los servicios de Docker Compose"
	@echo "  servicios-logs   : Muestra los logs de los servicios de Docker Compose"
	@echo "  servicios-reiniciar: Reinicia los servicios de Docker Compose"
	@echo "  correr-worker-celery: Ejecuta un worker de Celery localmente"
	@echo "  prueba           : Levanta un sistema de demo completo (placeholder)"

instalar: $(VENV_DIR)/bin/activate
$(VENV_DIR)/bin/activate: requirements.txt
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_ACTIVATE); pip install --upgrade pip
	$(VENV_ACTIVATE); pip install -r requirements.txt
	@echo "Entorno virtual creado y dependencias instaladas."
	@touch $(VENV_DIR)/bin/activate

correr: $(VENV_DIR)/bin/activate .env
	@echo "Iniciando la aplicación FastAPI..."
	$(VENV_ACTIVATE); uvicorn entrenai2.api.main:aplicacion $(RUN_ARGS)

correr-worker-celery: $(VENV_DIR)/bin/activate .env
	@echo "Iniciando worker de Celery..."
	$(VENV_ACTIVATE); celery -A entrenai2.celery.aplicacion_celery_minimal.aplicacion worker -l INFO -P threads

probar: $(VENV_DIR)/bin/activate
	@echo "Ejecutando pruebas..."
	$(VENV_ACTIVATE); pytest

limpiar:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@echo "Entorno virtual y archivos de caché eliminados."

# Comandos de Docker Compose
servicios-levantar: .env
	@echo "Iniciando servicios de Docker..."
	docker compose up -d --remove-orphans --build

servicios-bajar:
	@echo "Deteniendo servicios de Docker..."
	docker compose down

servicios-logs:
	@echo "Mostrando logs de los servicios de Docker..."
	docker compose logs -f

servicios-reiniciar: servicios-bajar servicios-levantar

# Comando de prueba general
prueba: servicios-levantar
	@echo "Sistema de demo levantado."
	# Aquí se podrían añadir más pasos, como poblar la base de datos con datos de prueba.

# Asegurar que .env exista para los comandos que lo necesiten
.env:
	@echo "Error: Archivo .env no encontrado. Por favor, copia .env.example a .env y configúralo."
	@exit 1
