# Makefile para el Proyecto Entrenai

# Intérprete de Python por defecto
PYTHON = python3

# Directorio del entorno virtual
VENV_DIR = .venv
VENV_ACTIVATE = . $(VENV_DIR)/bin/activate

# Argumentos por defecto para ejecutar FastAPI
# Asume que el Makefile está en entrenai_refactor y .env en el directorio padre (raíz del proyecto)
RUN_ARGS = --host $(shell grep FASTAPI_HOST ../.env | cut -d '=' -f2) --port $(shell grep FASTAPI_PORT ../.env | cut -d '=' -f2) --reload

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
# Asume que requirements.txt está en el mismo directorio que el Makefile (entrenai_refactor)
$(VENV_DIR)/bin/activate: requirements.txt
	test -d $(VENV_DIR) || $(PYTHON) -m venv $(VENV_DIR)
	$(VENV_ACTIVATE); pip install --upgrade pip
	$(VENV_ACTIVATE); pip install -r requirements.txt
	@echo "Entorno virtual creado y dependencias instaladas."
	@touch $(VENV_DIR)/bin/activate

# Asume que .env está en el directorio padre
correr: $(VENV_DIR)/bin/activate ../.env
	@echo "Iniciando la aplicación FastAPI..."
	# PYTHONPATH=. para asegurar que los módulos locales de entrenai_refactor se encuentren
	$(VENV_ACTIVATE); PYTHONPATH=. uvicorn api.principal:aplicacion $(RUN_ARGS)

# Asume que .env está en el directorio padre
correr-worker-celery: $(VENV_DIR)/bin/activate ../.env
	@echo "Iniciando worker de Celery..."
	# PYTHONPATH=. para asegurar que los módulos locales de entrenai_refactor se encuentren
	$(VENV_ACTIVATE); PYTHONPATH=. celery -A celery.tareas:aplicacion worker -l INFO -P threads

probar: $(VENV_DIR)/bin/activate
	@echo "Ejecutando pruebas..."
	$(VENV_ACTIVATE); pytest

limpiar:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@echo "Entorno virtual y archivos de caché eliminados."

# Comandos de Docker Compose
# Asume que docker-compose.yml está en el mismo directorio que este Makefile (entrenai_refactor)
# y que .env está en el directorio padre
servicios-levantar: ../.env
	@echo "Iniciando servicios de Docker (desde entrenai_refactor/docker-compose.yml)..."
	docker compose -f docker-compose.yml up -d --remove-orphans --build

servicios-bajar:
	@echo "Deteniendo servicios de Docker (desde entrenai_refactor/docker-compose.yml)..."
	docker compose -f docker-compose.yml down

servicios-logs:
	@echo "Mostrando logs de los servicios de Docker (desde entrenai_refactor/docker-compose.yml)..."
	docker compose -f docker-compose.yml logs -f

servicios-reiniciar: servicios-bajar servicios-levantar

# Comando de prueba general
prueba: servicios-levantar
	@echo "Sistema de demo levantado."
	# Aquí se podrían añadir más pasos, como poblar la base de datos con datos de prueba.

# Asegurar que .env exista en el directorio padre para los comandos que lo necesiten
../.env:
	@echo "Error: Archivo ../.env no encontrado. Por favor, copia .env.example a .env en la raíz del proyecto y configúralo."
	@exit 1
