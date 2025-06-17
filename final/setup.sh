#!/bin/bash

# =============================================================================
# ENTRENAI - SCRIPT DE CONFIGURACIÓN INICIAL
# =============================================================================

set -e  # Salir si hay errores

echo "🚀 Configurando Entrenai..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para imprimir mensajes coloreados
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar si Docker está instalado
if ! command -v docker &> /dev/null; then
    print_error "Docker no está instalado. Por favor instala Docker primero."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose no está instalado. Por favor instala Docker Compose primero."
    exit 1
fi

print_success "Docker y Docker Compose están instalados."

# Crear archivo .env si no existe
if [ ! -f .env ]; then
    print_status "Creando archivo .env desde .env.example..."
    cp .env.example .env
    print_success "Archivo .env creado. Puedes editarlo con tus configuraciones."
else
    print_warning "El archivo .env ya existe. No se sobreescribirá."
fi

# Crear directorios necesarios
print_status "Creando directorios necesarios..."
mkdir -p data/uploads
mkdir -p data/tmp
mkdir -p logs

print_success "Directorios creados."

# Construir imágenes Docker
print_status "Construyendo imágenes Docker..."
docker-compose build

print_success "Imágenes construidas."

# Iniciar servicios
print_status "Iniciando servicios Docker..."
docker-compose up -d

print_success "Servicios iniciados."

# Esperar a que los servicios estén listos
print_status "Esperando a que los servicios estén listos..."
sleep 15

# Verificar estado de los servicios
print_status "Verificando estado de los servicios..."
docker-compose ps

# Configurar Ollama
print_status "Configurando modelo de Ollama..."
if docker exec entrenai_ollama ollama list | grep -q "llama3.2"; then
    print_success "El modelo llama3.2 ya está instalado."
else
    print_status "Descargando modelo llama3.2... (esto puede tomar varios minutos)"
    docker exec entrenai_ollama ollama pull llama3.2
    print_success "Modelo llama3.2 descargado."
fi

# Verificar que la aplicación responde
print_status "Verificando que la aplicación responde..."
sleep 5

if curl -f http://localhost:8000/health &> /dev/null; then
    print_success "¡Aplicación funcionando correctamente!"
else
    print_warning "La aplicación podría no estar completamente lista. Verifica los logs con: make logs-app"
fi

echo ""
echo "==============================================================================="
echo -e "${GREEN}🎉 ¡ENTRENAI CONFIGURADO EXITOSAMENTE!${NC}"
echo "==============================================================================="
echo ""
echo "📍 Servicios disponibles:"
echo "   • Aplicación web: http://localhost:8000"
echo "   • API docs: http://localhost:8000/docs"
echo "   • Health check: http://localhost:8000/health"
echo ""
echo "🛠️  Comandos útiles:"
echo "   • Ver logs: make logs-app"
echo "   • Detener servicios: make docker-down"
echo "   • Reiniciar servicios: make restart"
echo "   • Ver estado: make status"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Edita el archivo .env con tus configuraciones"
echo "   2. Reinicia los servicios si cambias configuración: make restart"
echo "   3. Visita http://localhost:8000 para usar la aplicación"
echo ""
echo "🆘 Ayuda: make help"
echo "==============================================================================="
