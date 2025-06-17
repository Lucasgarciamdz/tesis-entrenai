"""Modelos de datos simplificados para Entrenai."""

from .base import *
from .moodle import *
from .setup import *

__all__ = [
    "BaseResponse",
    "ErrorResponse", 
    "MoodleCourse",
    "MoodleSection",
    "MoodleModule",
    "MoodleFile",
    "SetupRequest",
    "SetupResponse",
    "FileProcessRequest",
    "ProcessingStatus"
]
