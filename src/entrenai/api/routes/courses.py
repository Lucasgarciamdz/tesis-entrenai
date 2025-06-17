"""Endpoints para gestión de cursos."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from loguru import logger

from entrenai.core.clients.moodle_client import MoodleClient
from entrenai.api.models import MoodleCourse
from entrenai.config import get_config

router = APIRouter()


def get_moodle_client() -> MoodleClient:
    """Dependency para obtener cliente de Moodle."""
    config = get_config()
    return MoodleClient(config.moodle)


@router.get("/courses", response_model=List[MoodleCourse])
def get_courses(moodle: MoodleClient = Depends(get_moodle_client)):
    """Obtiene todos los cursos disponibles."""
    logger.info("Obteniendo lista de cursos")
    return moodle.get_all_courses()


@router.get("/courses/{course_id}", response_model=MoodleCourse)
def get_course(course_id: int, moodle: MoodleClient = Depends(get_moodle_client)):
    """Obtiene un curso específico."""
    logger.info(f"Obteniendo curso {course_id}")
    courses = moodle.get_all_courses()
    for course in courses:
        if course.id == course_id:
            return course
    raise HTTPException(status_code=404, detail="Curso no encontrado")
