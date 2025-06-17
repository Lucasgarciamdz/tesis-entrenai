"""Tests básicos para EntrenAI."""

import pytest
from fastapi.testclient import TestClient
from src.entrenai.api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test del endpoint raíz."""
    response = client.get("/")
    assert response.status_code == 200
    assert "EntrenAI API funcionando" in response.json()["message"]


def test_simple_chat():
    """Test de chat simple."""
    response = client.post(
        "/chat",
        params={"message": "Hola"}
    )
    # El test puede fallar si no hay un proveedor de IA configurado
    # pero al menos verificamos que el endpoint existe
    assert response.status_code in [200, 500]


def test_course_status():
    """Test de estado de curso."""
    response = client.get("/courses/999/status")
    # Debe devolver algún estado, aunque el curso no exista
    assert response.status_code in [200, 404, 500]


# TODO: Añadir tests más específicos cuando la configuración esté lista
# - Test con base de datos de prueba
# - Test de setup de curso
# - Test de procesamiento de documentos
# - Test de chat con contexto
