from typing import List, Optional

from src.entrenai.api.models import MoodleFile, MoodleModule
from src.entrenai.config.logger import get_logger
from src.entrenai.core.clients.moodle_client import MoodleClient, MoodleAPIError

logger = get_logger(__name__)


class MoodleFileDiscoveryService:
    """Service for discovering files in Moodle course folders."""
    
    def __init__(self, moodle_client: MoodleClient):
        self.moodle = moodle_client
    
    def discover_course_files(
        self, 
        course_id: int, 
        section_name: str, 
        folder_name: str
    ) -> List[MoodleFile]:
        """
        Discovers files in a specific folder within a course section.
        Returns empty list if section/folder not found or on error.
        """
        logger.info(
            f"Discovering files in course {course_id}, section '{section_name}', folder '{folder_name}'"
        )
        
        try:
            # Get all course contents
            all_course_contents = self.moodle._make_request(
                "core_course_get_contents", payload_params={"courseid": course_id}
            )
            if not isinstance(all_course_contents, list):
                logger.error(f"Invalid course contents format for course {course_id}")
                return []

            # Find target section
            section_id = self._find_target_section(all_course_contents, section_name)
            if not section_id:
                logger.warning(
                    f"Section '{section_name}' not found in course {course_id}"
                )
                return []

            # Find folder module in section
            folder_module = self._find_folder_module(course_id, section_id, folder_name)
            if not folder_module:
                logger.warning(
                    f"Folder '{folder_name}' not found in section '{section_name}' of course {course_id}"
                )
                return []

            # Get files from folder
            moodle_files = self.moodle.get_folder_files(folder_cmid=folder_module.id)
            logger.info(
                f"Found {len(moodle_files)} files in folder '{folder_name}' of course {course_id}"
            )
            
            return moodle_files

        except MoodleAPIError as e:
            logger.error(f"Moodle API error discovering files in course {course_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error discovering files in course {course_id}: {e}")
            return []

    def _find_target_section(
        self, 
        course_contents: List, 
        section_name: str
    ) -> Optional[int]:
        """Find section ID by name in course contents."""
        for section_data in course_contents:
            if section_data.get("name") == section_name:
                section_id = section_data.get("id")
                logger.info(f"Found section '{section_name}' with ID: {section_id}")
                return section_id
        return None

    def _find_folder_module(
        self, 
        course_id: int, 
        section_id: int, 
        folder_name: str
    ) -> Optional[MoodleModule]:
        """Find folder module by name in section."""
        try:
            folder_module = self.moodle.get_course_module_by_name(
                course_id, section_id, folder_name, "folder"
            )
            if folder_module and folder_module.id:
                logger.info(
                    f"Found folder '{folder_name}' with cmid: {folder_module.id}"
                )
                return folder_module
            return None
        except Exception as e:
            logger.error(
                f"Error finding folder '{folder_name}' in section {section_id}: {e}"
            )
            return None
