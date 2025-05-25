import logging
import sys

from src.entrenai.config import base_config


def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(base_config.log_level)

    # Create handlers if not already present
    if not logger.handlers:
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(base_config.log_level)

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # Prevent log propagation to the root logger if it's not desired
    # logger.propagate = False

    return logger


# Example of a global logger for the application if needed,
# though it's often better to get loggers per module: logging.getLogger(__name__)
# app_logger = get_logger("entrenai_app")
