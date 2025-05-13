import requests
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import MoodleConfig
from src.entrenai.core.models import (
    MoodleCourse,
    MoodleSection,
    MoodleModule,
    MoodleFile,
)
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)


class MoodleAPIError(Exception):
    """Custom exception for Moodle API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

    def __str__(self):
        return f"{super().__str__()} (Status Code: {self.status_code}, Response: {self.response_data})"


class MoodleClient:
    """Client for interacting with the Moodle Web Services API."""

    base_url: Optional[str]  # Class annotation for base_url

    def __init__(
        self, config: MoodleConfig, session: Optional[requests.Session] = None
    ):
        self.config = config
        if not config.url:
            logger.error(
                "Moodle URL is not configured. MoodleClient will not be functional."
            )
            self.base_url = None
        else:
            clean_url = config.url + "/" if not config.url.endswith("/") else config.url
            self.base_url = urljoin(clean_url, "webservice/rest/server.php")

        self.session = session or requests.Session()
        if self.config.token:
            self.session.params = {
                "wstoken": self.config.token,
                "moodlewsrestformat": "json",
            }  # type: ignore

        if self.base_url:
            logger.info(
                f"MoodleClient initialized for URL: {self.base_url.rsplit('/', 1)[0]}"
            )
        else:
            logger.warning("MoodleClient initialized without a valid base URL.")

    def _format_moodle_params(
        self, in_args: Any, prefix: str = "", out_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if out_dict is None:
            out_dict = {}
        if not isinstance(in_args, (list, dict)):
            out_dict[prefix] = in_args
            return out_dict
        if isinstance(in_args, list):
            for idx, item in enumerate(in_args):
                self._format_moodle_params(item, f"{prefix}[{idx}]", out_dict)
        elif isinstance(in_args, dict):
            for key, item in in_args.items():
                self._format_moodle_params(
                    item, f"{prefix}[{key}]" if prefix else key, out_dict
                )
        return out_dict

    def _make_request(
        self,
        wsfunction: str,
        payload_params: Optional[Dict[str, Any]] = None,
        http_method: str = "POST",
    ) -> Any:
        if not self.base_url:
            raise MoodleAPIError("Moodle base URL is not configured")

        query_params_for_url = {
            "wstoken": self.config.token,
            "moodlewsrestformat": "json",
            "wsfunction": wsfunction,
        }
        formatted_api_payload = (
            self._format_moodle_params(payload_params) if payload_params else {}
        )
        response: Optional[requests.Response] = None

        try:
            logger.debug(
                f"Calling Moodle API '{wsfunction}' method {http_method.upper()}. URL: {self.base_url}"
            )
            if http_method.upper() == "POST":
                response = self.session.post(
                    self.base_url,
                    params=query_params_for_url,
                    data=formatted_api_payload,
                )
            elif http_method.upper() == "GET":
                all_get_params = {**query_params_for_url, **formatted_api_payload}
                response = self.session.get(self.base_url, params=all_get_params)
            else:
                raise MoodleAPIError(f"Unsupported HTTP method: {http_method}")
            response.raise_for_status()
            json_data = response.json()
            if isinstance(json_data, dict) and "exception" in json_data:
                err_msg = json_data.get("message", "Unknown Moodle error")
                logger.error(
                    f"Moodle API error for '{wsfunction}': {json_data.get('errorcode')} - {err_msg}"
                )
                raise MoodleAPIError(message=err_msg, response_data=json_data)
            return json_data
        except requests.exceptions.HTTPError as http_err:
            resp_text = (
                http_err.response.text
                if http_err.response is not None
                else "No response"
            )
            status = (
                http_err.response.status_code if http_err.response is not None else None
            )
            logger.error(
                f"HTTP error for '{wsfunction}': {http_err} - Response: {resp_text}"
            )
            raise MoodleAPIError(
                f"HTTP error: {status}", status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception for '{wsfunction}': {req_err}")
            raise MoodleAPIError(str(req_err)) from req_err
        except ValueError as json_err:  # JSONDecodeError
            resp_text = response.text if response is not None else "No response"
            logger.error(
                f"JSON decode error for '{wsfunction}': {json_err} - Response: {resp_text}"
            )
            raise MoodleAPIError(
                f"Failed to decode JSON: {json_err}", response_data=resp_text
            ) from json_err

    def get_courses_by_user(self, user_id: int) -> List[MoodleCourse]:
        if user_id <= 0:
            raise ValueError("Invalid user_id.")
        logger.info(f"Fetching courses for user_id: {user_id}")
        try:
            courses_data = self._make_request(
                "core_enrol_get_users_courses", {"userid": user_id}
            )
            if not isinstance(
                courses_data, list
            ):  # Handle cases where Moodle might wrap in 'courses'
                if (
                    isinstance(courses_data, dict)
                    and "courses" in courses_data
                    and isinstance(courses_data["courses"], list)
                ):
                    courses_data = courses_data["courses"]
                else:
                    raise MoodleAPIError(
                        "Courses data not in expected list format.",
                        response_data=courses_data,
                    )
            return [MoodleCourse(**cd) for cd in courses_data]
        except MoodleAPIError as e:
            logger.error(f"Failed to get courses for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.exception(
                f"Unexpected error in get_courses_by_user for user {user_id}: {e}"
            )
            raise MoodleAPIError(f"Unexpected error fetching courses: {e}")

    def get_section_by_name(
        self, course_id: int, section_name: str
    ) -> Optional[MoodleSection]:
        """Retrieves a specific section by its name within a course."""
        logger.info(f"Searching for section '{section_name}' in course {course_id}")
        try:
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )
            if not isinstance(course_contents, list):
                logger.error(f"Expected list of sections, got {type(course_contents)}")
                return None
            for section_data in course_contents:
                if section_data.get("name") == section_name:
                    logger.info(
                        f"Found section '{section_name}' with ID: {section_data.get('id')}"
                    )
                    return MoodleSection(**section_data)
            logger.info(f"Section '{section_name}' not found in course {course_id}.")
            return None
        except MoodleAPIError as e:
            logger.error(f"API error searching for section '{section_name}': {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error searching for section '{section_name}': {e}"
            )
            return None

    def create_course_section(
        self, course_id: int, section_name: str, position: int = 0
    ) -> Optional[MoodleSection]:
        logger.info(
            f"Ensuring section '{section_name}' in course {course_id} at position {position}"
        )
        existing_section = self.get_section_by_name(course_id, section_name)
        if existing_section:
            logger.info(
                f"Section '{section_name}' already exists with ID {existing_section.id}. Using existing."
            )
            return existing_section

        logger.info(f"Section '{section_name}' not found. Attempting to create.")
        try:
            create_payload = {"courseid": course_id, "position": position, "number": 1}
            created_data = self._make_request(
                "local_wsmanagesections_create_sections", create_payload
            )
            if not isinstance(created_data, list) or not created_data:
                raise MoodleAPIError(
                    "Failed to create section structure.", response_data=created_data
                )

            new_section_info = created_data[0]
            # Try to get section ID using either 'id' or 'sectionid' field
            new_section_id = new_section_info.get("id") or new_section_info.get(
                "sectionid"
            )
            if new_section_id is None:
                raise MoodleAPIError(
                    "Created section data missing 'id' or 'sectionid'.",
                    response_data=new_section_info,
                )

            logger.info(
                f"Section structure created (ID: {new_section_id}). Updating name to '{section_name}'."
            )
            # Update the section with new name and visibility
            update_payload = {
                "courseid": course_id,
                "sections": [
                    {"id": new_section_id, "name": section_name, "visible": 1}
                ],
            }
            self._make_request(
                "local_wsmanagesections_update_sections", payload_params=update_payload
            )
            # Retrieve created section via plugin get_sections
            get_payload = {"courseid": course_id, "sectionids": [new_section_id]}
            sections_data = self._make_request(
                "local_wsmanagesections_get_sections", payload_params=get_payload
            )
            if isinstance(sections_data, list) and sections_data:
                sec_info = sections_data[0]
                return MoodleSection(**sec_info)
            return None
        except MoodleAPIError as e:
            logger.error(f"Error creating section '{section_name}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error creating section '{section_name}': {e}")
            return None

    def create_module_in_section(
        self,
        course_id: int,
        section_id: int,
        module_name: str,
        mod_type: str,
        instance_params: Optional[Dict[str, Any]] = None,
        common_module_options: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[MoodleModule]:
        """Creates or returns an existing module in the specified course section.

        This method uses the local_wsmanagesections plugin to create modules in Moodle.
        It first checks if the module already exists for idempotency.
        Currently supports 'url' and 'folder' module types.
        """
        # Check if module already exists (for idempotency)
        existing_module = self.get_course_module_by_name(
            course_id, section_id, module_name, mod_type
        )
        if existing_module:
            logger.info(
                f"Module '{module_name}' (type: {mod_type}) already exists in section {section_id}. Using existing ID: {existing_module.id}"
            )
            return existing_module

        logger.info(
            f"Creating module '{module_name}' (type: {mod_type}) in course {course_id}, section {section_id}"
        )

        try:
            # Get existing section data to include in the update
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )

            section_data = None
            for section in course_contents:
                if section.get("id") == section_id:
                    section_data = section
                    break

            if not section_data:
                logger.error(
                    f"Could not find section ID {section_id} in course {course_id}"
                )
                return None

            # Prepare the module data based on module type (include target section)
            module_data = {
                "modname": mod_type,
                "section": section_id,
                "name": module_name,
            }

            # Add specific parameters based on module type
            if (
                mod_type == "url"
                and instance_params
                and "externalurl" in instance_params
            ):
                module_data["externalurl"] = instance_params["externalurl"]
                if "intro" in instance_params:
                    module_data["intro"] = instance_params["intro"]
                if "display" in instance_params:
                    module_data["display"] = instance_params["display"]
            elif mod_type == "folder":
                if instance_params and "intro" in instance_params:
                    module_data["intro"] = instance_params["intro"]
                else:
                    module_data["intro"] = f"Carpeta para {module_name}"

                if instance_params:
                    for key, value in instance_params.items():
                        if key not in module_data:
                            module_data[key] = value

            # Add common module options if provided
            if common_module_options:
                for option in common_module_options:
                    if "name" in option and "value" in option:
                        module_data[option["name"]] = option["value"]
            # Prepare payload for module creation via sections WS
            update_payload = {
                "courseid": course_id,
                "modules": [module_data],
            }
            # Send update to create module
            self._make_request("local_wsmanagesections_update_sections", update_payload)
            # Retrieve and return created module
            return self.get_course_module_by_name(
                course_id, section_id, module_name, mod_type
            )
        except MoodleAPIError as e:
            logger.error(f"API Error adding module '{module_name}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error adding module '{module_name}': {e}")
            return None

    def create_folder_in_section(
        self, course_id: int, section_id: int, folder_name: str, intro: str = ""
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Ensuring folder '{folder_name}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "intro": intro or f"Carpeta para {folder_name}",
            "introformat": 1,
            "display": 0,
            "showexpanded": 1,
        }
        return self.create_module_in_section(
            course_id,
            section_id,
            folder_name,
            "folder",
            instance_params,
            [{"name": "visible", "value": "1"}],
        )

    def create_url_in_section(
        self,
        course_id: int,
        section_id: int,
        url_name: str,
        external_url: str,
        description: str = "",
        display_mode: int = 0,
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Ensuring URL '{url_name}' -> '{external_url}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "externalurl": external_url,
            "intro": description or f"Enlace a {url_name}",
            "introformat": 1,
            "display": display_mode,
        }
        return self.create_module_in_section(
            course_id,
            section_id,
            url_name,
            "url",
            instance_params,
            [{"name": "visible", "value": "1"}],
        )

    def get_course_module_by_name(
        self,
        course_id: int,
        target_section_id: int,
        target_module_name: str,
        target_mod_type: Optional[str] = None,
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Searching for module '{target_module_name}' (type: {target_mod_type or 'any'}) in course {course_id}, section {target_section_id}"
        )
        try:
            course_contents = self._make_request(
                "core_course_get_contents", {"courseid": course_id}
            )
            if not isinstance(course_contents, list):
                return None
            for section_data in course_contents:
                if section_data.get("id") == target_section_id:
                    for module_data in section_data.get("modules", []):
                        name_match = module_data.get("name") == target_module_name
                        type_match = (
                            target_mod_type is None
                            or module_data.get("modname") == target_mod_type
                        )
                        if name_match and type_match:
                            logger.info(
                                f"Found module '{target_module_name}' (ID: {module_data.get('id')})"
                            )
                            return MoodleModule(**module_data)
                    logger.info(
                        f"Module '{target_module_name}' not found in section {target_section_id}."
                    )
                    return None
            logger.info(f"Section {target_section_id} not found in course {course_id}.")
            return None
        except MoodleAPIError as e:
            logger.error(f"API Error searching for module '{target_module_name}': {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error searching for module '{target_module_name}': {e}"
            )
            return None

    def get_folder_files(self, folder_cmid: int) -> List[MoodleFile]:
        logger.info(f"Fetching files for folder module ID (cmid): {folder_cmid}")
        try:
            module_details = self._make_request(
                "core_course_get_course_module", {"cmid": folder_cmid}
            )
            if not module_details or "cm" not in module_details:
                return []
            cm_info = module_details["cm"]
            if cm_info.get("modname") != "folder":
                return []

            files_data = []
            if "contents" in cm_info and isinstance(cm_info["contents"], list):
                for file_info in cm_info["contents"]:
                    if file_info.get("type") == "file" and all(
                        k in file_info
                        for k in (
                            "filename",
                            "filepath",
                            "filesize",
                            "fileurl",
                            "timemodified",
                        )
                    ):
                        files_data.append(MoodleFile(**file_info))
                    else:
                        logger.warning(
                            f"Skipping file due to missing fields in folder {folder_cmid}: {file_info}"
                        )
            return files_data
        except MoodleAPIError as e:
            logger.error(f"API Error fetching files for folder {folder_cmid}: {e}")
            return []
        except Exception as e:
            logger.exception(
                f"Unexpected error fetching files for folder {folder_cmid}: {e}"
            )
            return []

    def download_file(self, file_url: str, download_dir: Path, filename: str) -> Path:
        if not self.config.token:
            raise MoodleAPIError("Moodle token not configured.")
        download_dir.mkdir(parents=True, exist_ok=True)
        local_filepath = download_dir / filename
        logger.info(f"Downloading Moodle file from {file_url} to {local_filepath}")
        try:
            params = (
                {"wstoken": self.config.token} if "wstoken" not in file_url else None
            )
            with requests.get(file_url, params=params, stream=True) as r:
                r.raise_for_status()
                with open(local_filepath, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
            logger.info(f"Successfully downloaded {filename}")
            return local_filepath
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error downloading {filename}: {http_err}")
            raise MoodleAPIError(
                f"Failed to download file '{filename}': {http_err}"
            ) from http_err
        except Exception as e:
            logger.exception(f"Error downloading file {filename}: {e}")
            raise MoodleAPIError(
                f"Unexpected error downloading file '{filename}': {e}"
            ) from e

    # get_all_courses and __main__ block remain unchanged from previous version.
    # For brevity, they are omitted here but should be part of the final file.
    def get_all_courses(self) -> List[MoodleCourse]:
        logger.info("Fetching all available courses from Moodle")
        try:
            courses_data = self._make_request("core_course_get_courses")
            if not isinstance(courses_data, list):
                if (
                    isinstance(courses_data, dict)
                    and "courses" in courses_data
                    and isinstance(courses_data["courses"], list)
                ):
                    courses_data = courses_data["courses"]
                else:
                    raise MoodleAPIError(
                        "Courses data not in expected list format.",
                        response_data=courses_data,
                    )
            return [MoodleCourse(**cd) for cd in courses_data]
        except MoodleAPIError as e:
            logger.error(f"Failed to get all courses: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred in get_all_courses: {e}")
            raise MoodleAPIError(f"Unexpected error fetching all courses: {e}")


if __name__ == "__main__":
    from src.entrenai.config import moodle_config

    if not moodle_config.url or not moodle_config.token:
        print("MOODLE_URL and MOODLE_TOKEN must be set in .env for this test.")
    else:
        client = MoodleClient(config=moodle_config)
        test_user_id = moodle_config.default_teacher_id or 2
        print(f"\nAttempting to get courses for user ID: {test_user_id}...")
        try:
            courses = client.get_courses_by_user(test_user_id)
            if courses:
                print(f"Successfully retrieved {len(courses)} courses:")
                for course in courses:
                    print(
                        f"  - ID: {course.id}, Name: {course.fullname} (Shortname: {course.shortname})"
                    )

                # Test section and module creation on the first course found
                if courses:
                    test_course_id = courses[0].id
                    print(f"\n--- Testing on Course ID: {test_course_id} ---")

                    # Test get_section_by_name (non-existent)
                    print(
                        "Searching for non-existent section 'Test Section NonExistent'..."
                    )
                    non_existent_section = client.get_section_by_name(
                        test_course_id, "Test Section NonExistent"
                    )
                    print(f"Result: {non_existent_section}")

                    # Test create_course_section (idempotent)
                    section_name_to_create = "Entrenai Test Section"
                    print(f"Ensuring section '{section_name_to_create}'...")
                    created_section = client.create_course_section(
                        test_course_id, section_name_to_create, position=2
                    )
                    if created_section:
                        print(
                            f"Section ensured: ID {created_section.id}, Name '{created_section.name}'"
                        )

                        # Test get_section_by_name (existent)
                        print(
                            f"Searching for existing section '{section_name_to_create}'..."
                        )
                        found_section = client.get_section_by_name(
                            test_course_id, section_name_to_create
                        )
                        print(f"Result: {found_section}")

                        # Test create_folder_in_section (idempotent)
                        folder_name_to_create = "Test Auto Folder"
                        print(
                            f"Ensuring folder '{folder_name_to_create}' in section {created_section.id}..."
                        )
                        created_folder = client.create_folder_in_section(
                            test_course_id,
                            created_section.id,
                            folder_name_to_create,
                            "Test folder intro.",
                        )
                        if created_folder:
                            print(
                                f"Folder ensured: ID {created_folder.id}, Name '{created_folder.name}'"
                            )
                        else:
                            print(f"Failed to ensure folder '{folder_name_to_create}'.")

                        # Test create_url_in_section (idempotent)
                        url_name_to_create = "Test Auto URL"
                        print(
                            f"Ensuring URL '{url_name_to_create}' in section {created_section.id}..."
                        )
                        created_url = client.create_url_in_section(
                            test_course_id,
                            created_section.id,
                            url_name_to_create,
                            "http://example.com/test-url",
                            "Test URL description.",
                        )
                        if created_url:
                            print(
                                f"URL ensured: ID {created_url.id}, Name '{created_url.name}'"
                            )
                        else:
                            print(f"Failed to ensure URL '{url_name_to_create}'.")

                        # Test get_folder_files (on a potentially empty folder)
                        if created_folder and created_folder.id is not None:
                            print(
                                f"Getting files from folder cmid: {created_folder.id}..."
                            )
                            folder_files = client.get_folder_files(created_folder.id)
                            print(
                                f"Found {len(folder_files)} files in '{created_folder.name}'."
                            )
                            for f in folder_files:
                                print(f"  - {f.filename} (URL: {f.fileurl})")
                        else:
                            print(
                                "Skipping get_folder_files test as folder was not created/retrieved."
                            )

                    else:
                        print(f"Failed to ensure section '{section_name_to_create}'.")

            else:
                print(
                    f"No courses found for user ID: {test_user_id} or an error occurred."
                )
        except MoodleAPIError as e:
            print(f"Moodle API Error during testing: {e}")
        except Exception as e:
            print(f"Generic error during testing: {e}")
