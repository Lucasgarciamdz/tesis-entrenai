import logging

class Configuracion:
    def __init__(self):
        self.logger = logging.getLogger("entrenai")
        self.moodle_url = "https://moodle.ejemplo.com"
        self.pgvector_url = "postgresql://usuario:clave@localhost:5432/pgvector"
        self.n8n_url = "https://n8n.ejemplo.com"
        self.logger.info("Configuración cargada correctamente.")

config = Configuracion() 