import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict

from src.entrenai.config.logger import get_logger

# Import base_config to get db_path, assuming it's added to BaseConfig or a specific FileConfig
from src.entrenai.config import base_config

logger = get_logger(__name__)


class FileTrackerError(Exception):
    """Custom exception for FileTracker errors."""

    pass


class FileTracker:
    """
    Tracks processed files and their modification timestamps using an SQLite database.
    """

    TABLE_NAME = "processed_files"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or base_config.file_tracker_db_path)
        self._ensure_db_and_table()
        logger.info(f"FileTracker inicializado con base de datos: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establece y devuelve una conexión a la base de datos."""
        try:
            # The directory for the SQLite DB file must exist.
            # os.makedirs(self.db_path.parent, exist_ok=True) # Done in config.py now
            conn = sqlite3.connect(self.db_path)
            return conn
        except sqlite3.Error as e:
            logger.error(
                f"Error al conectar con la base de datos de FileTracker en {self.db_path}: {e}"
            )
            raise FileTrackerError(
                f"No se pudo conectar a la base de datos: {e}"
            ) from e

    def _ensure_db_and_table(self):
        """Asegura que la base de datos y la tabla necesaria existan."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        course_id INTEGER NOT NULL,
                        file_identifier TEXT NOT NULL, -- e.g., filename or unique Moodle file ID
                        moodle_timemodified INTEGER NOT NULL,
                        processed_at INTEGER NOT NULL,
                        PRIMARY KEY (course_id, file_identifier)
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(
                f"Error al asegurar la existencia de la tabla de FileTracker: {e}"
            )
            raise FileTrackerError(
                f"Falló la configuración de la tabla de la base de datos: {e}"
            ) from e

    def is_file_new_or_modified(
        self, course_id: int, file_identifier: str, moodle_timemodified: int
    ) -> bool:
        """
        Checks if a file is new or has been modified since the last processing.
        'file_identifier' can be a filename or a more stable Moodle file ID if available.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT moodle_timemodified FROM {self.TABLE_NAME}
                    WHERE course_id = ? AND file_identifier = ?
                    """,
                    (course_id, file_identifier),
                )
                row = cursor.fetchone()
                if row is None:
                    logger.debug(
                        f"Archivo '{file_identifier}' en curso {course_id} es nuevo."
                    )
                    return True  # Archivo no encontrado en el tracker, es nuevo

                last_processed_moodle_ts = row[0]
                if moodle_timemodified > last_processed_moodle_ts:
                    logger.debug(
                        f"Archivo '{file_identifier}' en curso {course_id} modificado "
                        f"(ts Moodle: {moodle_timemodified} > ts rastreado: {last_processed_moodle_ts})."
                    )
                    return True  # El archivo ha sido modificado en Moodle

                logger.debug(
                    f"Archivo '{file_identifier}' en curso {course_id} no ha cambiado."
                )
                return False  # El archivo no es nuevo ni ha sido modificado
        except sqlite3.Error as e:
            logger.error(
                f"Error al verificar archivo '{file_identifier}' en curso {course_id}: {e}"
            )
            # En caso de error de BD, asumir conservadoramente que el archivo necesita procesamiento
            return True
        except Exception as e:
            logger.exception(
                f"Error inesperado al verificar archivo '{file_identifier}' en curso {course_id}: {e}"
            )
            return True

    def mark_file_as_processed(
        self, course_id: int, file_identifier: str, moodle_timemodified: int
    ):
        """Marks a file as processed with its current Moodle modification timestamp."""
        processed_at_ts = int(time.time())
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.TABLE_NAME} 
                    (course_id, file_identifier, moodle_timemodified, processed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (course_id, file_identifier, moodle_timemodified, processed_at_ts),
                )
                conn.commit()
                logger.info(
                    f"Archivo '{file_identifier}' en curso {course_id} marcado como procesado "
                    f"(ts Moodle: {moodle_timemodified}, Procesado en: {processed_at_ts})."
                )
        except sqlite3.Error as e:
            logger.error(
                f"Error al marcar archivo '{file_identifier}' en curso {course_id} como procesado: {e}"
            )
            raise FileTrackerError(
                f"Falló al marcar archivo como procesado: {e}"
            ) from e

    def get_processed_files_timestamps(self, course_id: int) -> Dict[str, int]:
        """
        Recupera un diccionario de identificadores de archivos procesados y sus timemodified de Moodle
        para un curso dado.
        """
        timestamps: Dict[str, int] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT file_identifier, moodle_timemodified FROM {self.TABLE_NAME}
                    WHERE course_id = ?
                    """,
                    (course_id,),
                )
                for row in cursor.fetchall():
                    timestamps[row[0]] = row[1]
            return timestamps
        except sqlite3.Error as e:
            logger.error(
                f"Error al recuperar archivos procesados para el curso {course_id}: {e}"
            )
            return {}  # Devolver dict vacío en caso de error
        except Exception as e:
            logger.exception(
                f"Error inesperado al recuperar archivos procesados para el curso {course_id}: {e}"
            )
            return {}
