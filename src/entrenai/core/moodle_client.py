import requests
import json  # Added import for json.dumps
import shutil  # For download_file
from pathlib import Path  # For download_file and type hinting
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import MoodleConfig
from src.entrenai.core.models import (
    MoodleCourse,
    MoodleSection,
    MoodleModule,
    MoodleFile,  # Added MoodleFile
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
    """
    Client for interacting with the Moodle Web Services API.
    """

    def __init__(
        self, config: MoodleConfig, session: Optional[requests.Session] = None
    ):
        self.config = config
        if (
            not config.url
        ):  # Token can be optional for some public calls, but URL is essential
            logger.error(
                "Moodle URL is not configured. MoodleClient will not be functional."
            )
            self.base_url: Optional[str] = None
        else:
            # Ensure URL ends with /webservice/rest/server.php
            if not config.url.endswith("/"):
                clean_url = config.url + "/"
            else:
                clean_url = config.url

            self.base_url = urljoin(clean_url, "webservice/rest/server.php")

        self.session = session or requests.Session()
        # Initialize session with default params directly
        if self.config.token:  # Only set params if token exists
            self.session.params = {
                "wstoken": self.config.token,
                "moodlewsrestformat": "json",
            }

        if self.base_url:
            logger.info(
                f"MoodleClient initialized for URL: {self.base_url.rsplit('/', 1)[0]}"
            )  # Log base Moodle URL
        else:
            logger.warning("MoodleClient initialized without a valid base URL.")

    def _format_moodle_params(
        self, in_args: Any, prefix: str = "", out_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transforms dictionary/array structure to a flat dictionary for Moodle API.
        Example: {'courses':[{'id':1,'name': 'course1'}]} -> {'courses[0][id]':1, 'courses[0][name]':'course1'}
        """
        if out_dict is None:
            out_dict = {}

        if not isinstance(in_args, (list, dict)):
            out_dict[prefix] = in_args
            return out_dict

        if isinstance(in_args, list):
            for idx, item in enumerate(in_args):
                new_prefix = f"{prefix}[{idx}]"
                self._format_moodle_params(item, new_prefix, out_dict)
        elif isinstance(in_args, dict):
            for key, item in in_args.items():
                new_prefix = f"{prefix}[{key}]" if prefix else key
                self._format_moodle_params(item, new_prefix, out_dict)
        return out_dict

    def _make_request(
        self,
        wsfunction: str,
        payload_params: Optional[Dict[str, Any]] = None,
        http_method: str = "POST",
    ) -> Any:
        if not self.base_url:
            logger.error("Cannot make request: base_url is not set")
            raise MoodleAPIError("Moodle base URL is not configured")

        request_url = self.base_url

        # Core Moodle webservice query parameters that go into the URL
        query_params_for_url = {
            "wstoken": self.config.token,
            "moodlewsrestformat": "json",
            "wsfunction": wsfunction,  # Ensure wsfunction is part of the query
        }

        # Prepare the main payload (e.g., for POST body or complex GET params)
        formatted_api_payload = (
            self._format_moodle_params(payload_params) if payload_params else {}
        )

        response: Optional[requests.Response] = None

        try:
            logger.debug(
                f"Calling Moodle API function '{wsfunction}' with method {http_method.upper()}."
            )
            logger.debug(f"  URL: {request_url}")
            logger.debug(f"  Query Params for URL: {query_params_for_url}")

            if http_method.upper() == "POST":
                logger.debug(f"  POST Data: {formatted_api_payload}")
                response = self.session.post(
                    request_url, params=query_params_for_url, data=formatted_api_payload
                )
            elif http_method.upper() == "GET":
                all_get_params = query_params_for_url.copy()
                if formatted_api_payload:  # Assuming formatted_api_payload is a dict
                    all_get_params.update(formatted_api_payload)
                logger.debug(f"  GET Params: {all_get_params}")
                response = self.session.get(request_url, params=all_get_params)
            else:
                logger.error(f"Unsupported HTTP method specified: {http_method}")
                raise MoodleAPIError(f"Unsupported HTTP method: {http_method}")

            response.raise_for_status()  # Check for HTTP errors (4xx or 5xx)

            json_data = (
                response.json()
            )  # Can raise ValueError if response is not valid JSON

            # Check for Moodle specific error structure in the JSON response
            if isinstance(json_data, dict) and "exception" in json_data:
                logger.error(
                    f"Moodle API returned an exception for function '{wsfunction}': "
                    f"Type: {json_data.get('exception')}, "
                    f"ErrorCode: {json_data.get('errorcode')}, "
                    f"Message: {json_data.get('message')}"
                )
                raise MoodleAPIError(
                    message=json_data.get("message", "Unknown Moodle error"),
                    status_code=None,  # No HTTP status code for Moodle application errors
                    response_data=json_data,
                )

            return json_data

        except requests.exceptions.HTTPError as http_err:
            # Log more details including the response body if available
            response_text = (
                http_err.response.text
                if http_err.response is not None
                else "No response text available"
            )
            actual_url_called = http_err.request.url if http_err.request else "N/A"
            logger.error(
                f"HTTP error occurred while calling Moodle function '{wsfunction}': {http_err} (URL: {actual_url_called}) - Response: {response_text}"
            )
            raise MoodleAPIError(
                message=f"HTTP error: {http_err.response.status_code if http_err.response is not None else 'Unknown status'} for {actual_url_called}",
                status_code=http_err.response.status_code
                if http_err.response is not None
                else None,
                response_data=response_text,
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(
                f"Request exception occurred while calling Moodle function '{wsfunction}': {req_err}"
            )
            raise MoodleAPIError(message=str(req_err)) from req_err
        except ValueError as json_err:
            err_msg = (
                f"JSON decode error for Moodle function '{wsfunction}': {json_err}"
            )
            resp_text = (
                response.text if response is not None else "No response text available"
            )
            logger.error(f"{err_msg} - Response: {resp_text}")
            raise MoodleAPIError(
                message=f"Failed to decode JSON response: {json_err}",
                response_data=resp_text,
            ) from json_err

    def get_courses_by_user(self, user_id: int) -> List[MoodleCourse]:
        # Validate user ID
        if user_id <= 0:
            logger.error(f"Invalid user_id: {user_id}. User ID must be greater than 0.")
            raise ValueError(
                f"Invalid user_id: {user_id}. User ID must be greater than 0."
            )

        logger.info(f"Fetching courses for user_id: {user_id}")
        payload = {"userid": user_id}
        try:
            courses_data = self._make_request(
                "core_enrol_get_users_courses", payload_params=payload
            )
            if not isinstance(courses_data, list):
                logger.error(
                    f"Unexpected response type for get_courses_by_user: {type(courses_data)}. Expected list. Data: {courses_data}"
                )
                if (
                    isinstance(courses_data, dict)
                    and "courses" in courses_data
                    and isinstance(courses_data["courses"], list)
                ):
                    courses_data = courses_data["courses"]
                else:
                    raise MoodleAPIError(
                        "Courses data is not in expected list format.",
                        response_data=courses_data,
                    )
            courses = [MoodleCourse(**course_data) for course_data in courses_data]
            logger.info(f"Found {len(courses)} courses for user_id: {user_id}")
            return courses
        except MoodleAPIError as e:
            logger.error(f"Failed to get courses for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred in get_courses_by_user for user {user_id}: {e}"
            )
            raise MoodleAPIError(f"Unexpected error fetching courses: {e}")

    def get_all_courses(self) -> List[MoodleCourse]:
        """
        Retrieves all courses available in the Moodle site using core_course_get_courses API.

        Returns:
            List[MoodleCourse]: A list of MoodleCourse objects for all available courses.
        """
        logger.info("Fetching all available courses from Moodle")
        try:
            courses_data = self._make_request("core_course_get_courses")

            if not isinstance(courses_data, list):
                logger.error(
                    f"Unexpected response type for get_all_courses: {type(courses_data)}. Expected list. Data: {courses_data}"
                )
                if (
                    isinstance(courses_data, dict)
                    and "courses" in courses_data
                    and isinstance(courses_data["courses"], list)
                ):
                    courses_data = courses_data["courses"]
                else:
                    raise MoodleAPIError(
                        "Courses data is not in expected list format.",
                        response_data=courses_data,
                    )

            courses = [MoodleCourse(**course_data) for course_data in courses_data]
            logger.info(f"Found {len(courses)} courses in total")
            return courses

        except MoodleAPIError as e:
            logger.error(f"Failed to get all courses: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred in get_all_courses: {e}")
            raise MoodleAPIError(f"Unexpected error fetching all courses: {e}")

    def create_module_in_section(
        self,
        course_id: int,
        section_id: int,
        module_name: str,
        mod_type: str,
        instance_params: Optional[Dict[str, Any]] = None,
        common_module_options: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Attempting to add module '{module_name}' (type: {mod_type}) to course {course_id}, section {section_id}"
        )
        module_data: Dict[str, Any] = {
            "modname": mod_type,
            "name": module_name,
            "section": section_id,
        }
        options_list: List[Dict[str, Any]] = common_module_options or []
        if instance_params:
            for key, value in instance_params.items():
                options_list.append({"name": key, "value": str(value)})
        if options_list:
            module_data["options"] = options_list
        payload = {"courseid": course_id, "modules": [module_data]}
        try:
            response_data = self._make_request(
                "core_course_add_module", payload_params=payload
            )
            if not isinstance(response_data, list) or not response_data:
                logger.error(
                    f"Failed to add module or unexpected response: {response_data}"
                )
                return None
            added_module_info = response_data[0]
            if "id" not in added_module_info or "instance" not in added_module_info:
                logger.error(
                    f"Response from core_course_add_module missing 'id' or 'instance': {added_module_info}"
                )
                if "warnings" in added_module_info and added_module_info["warnings"]:
                    logger.warning(
                        f"Moodle warnings while adding module: {added_module_info['warnings']}"
                    )
                return None
            cmid = added_module_info["id"]
            instance_id = added_module_info["instance"]
            logger.info(
                f"Module '{module_name}' (type: {mod_type}) added with cmid: {cmid}, instanceid: {instance_id}."
            )
            return MoodleModule(
                id=cmid, name=module_name, modname=mod_type, instance=instance_id
            )
        except MoodleAPIError as e:
            logger.error(f"Moodle API Error while adding module '{module_name}': {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error while adding module '{module_name}': {e}"
            )
            return None

    def create_folder_in_section(
        self,
        course_id: int,
        section_id: int,
        folder_name: str,
        intro: Optional[str] = "",
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Creating folder '{folder_name}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "intro": intro or f"Carpeta para {folder_name}",
            "introformat": 1,
            "display": 0,
            "showexpanded": 1,
        }
        common_opts = [{"name": "visible", "value": "1"}]
        return self.create_module_in_section(
            course_id=course_id,
            section_id=section_id,
            module_name=folder_name,
            mod_type="folder",
            instance_params=instance_params,
            common_module_options=common_opts,
        )

    def create_url_in_section(
        self,
        course_id: int,
        section_id: int,
        url_name: str,
        external_url: str,
        description: Optional[str] = "",
        display_mode: int = 0,
    ) -> Optional[MoodleModule]:
        logger.info(
            f"Creating URL '{url_name}' -> '{external_url}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "externalurl": external_url,
            "intro": description or f"Enlace a {url_name}",
            "introformat": 1,
            "display": display_mode,
        }
        common_opts = [{"name": "visible", "value": "1"}]
        return self.create_module_in_section(
            course_id=course_id,
            section_id=section_id,
            module_name=url_name,
            mod_type="url",
            instance_params=instance_params,
            common_module_options=common_opts,
        )

    def create_course_section(
        self, course_id: int, section_name: str, position: int = 0
    ) -> Optional[MoodleSection]:
        logger.info(
            f"Attempting to create section '{section_name}' in course {course_id} at position {position}"
        )
        try:
            create_payload = {"courseid": course_id, "position": position, "number": 1}
            created_sections_data = self._make_request(
                "local_wsmanagesections_create_sections", payload_params=create_payload
            )
            if not isinstance(created_sections_data, list) or not created_sections_data:
                logger.error(
                    f"Failed to create section structure or unexpected response: {created_sections_data}"
                )
                return None
            new_section_info = created_sections_data[0]
            new_section_id = new_section_info.get("id")
            new_section_number = new_section_info.get("section")
            if new_section_id is None:
                logger.error(
                    f"Created section data does not contain an 'id': {new_section_info}"
                )
                return None
            logger.info(
                f"Section structure created with ID: {new_section_id}, Number: {new_section_number}. Now updating name."
            )
            update_payload = {
                "courseid": course_id,
                "sections": [
                    {"id": new_section_id, "name": section_name, "visible": 1}
                ],
            }
            update_response = self._make_request(
                "local_wsmanagesections_update_sections", payload_params=update_payload
            )
            logger.info(
                f"Update request for section ID {new_section_id} sent. Response: {update_response}"
            )
            get_section_payload = {
                "courseid": course_id,
                "sectionids": [new_section_id],
            }
            updated_section_data_list = self._make_request(
                "local_wsmanagesections_get_sections",
                payload_params=get_section_payload,
            )
            if (
                not isinstance(updated_section_data_list, list)
                or not updated_section_data_list
            ):
                logger.error(
                    f"Failed to retrieve updated section details for ID {new_section_id}."
                )
                return MoodleSection(
                    id=new_section_id,
                    name=section_name,
                    section=new_section_number
                    if new_section_number is not None
                    else position,
                )
            final_section_data = updated_section_data_list[0]
            if final_section_data.get("name") != section_name:
                logger.warning(
                    f"Section name after update ('{final_section_data.get('name')}') differs from target ('{section_name}'). Using actual name."
                )
            logger.info(
                f"Successfully created and named section: ID {final_section_data.get('id')}, Name '{final_section_data.get('name')}'"
            )
            return MoodleSection(**final_section_data)
        except MoodleAPIError as e:
            logger.error(
                f"Moodle API Error while creating section '{section_name}' for course {course_id}: {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error while creating section '{section_name}' for course {course_id}: {e}"
            )
            return None

    def get_course_module_by_name(
        self,
        course_id: int,
        target_section_id: int,
        target_module_name: str,
        target_mod_type: Optional[str] = None,
    ) -> Optional[MoodleModule]:
        """Finds a specific module by name within a specific section of a course."""
        logger.info(
            f"Searching for module '{target_module_name}' (type: {target_mod_type or 'any'}) in course {course_id}, section {target_section_id}"
        )
        try:
            # core_course_get_contents can get sections and their modules.
            course_contents = self._make_request(
                "core_course_get_contents", payload_params={"courseid": course_id}
            )
            if not isinstance(course_contents, list):
                logger.error(
                    f"Expected list of sections from core_course_get_contents, got {type(course_contents)}"
                )
                return None

            for section_data in course_contents:
                if section_data.get("id") == target_section_id:
                    modules_in_section = section_data.get("modules", [])
                    for module_data in modules_in_section:
                        name_match = module_data.get("name") == target_module_name
                        type_match = (
                            target_mod_type is None
                            or module_data.get("modname") == target_mod_type
                        )
                        if name_match and type_match:
                            logger.info(
                                f"Found module '{target_module_name}' (ID: {module_data.get('id')}) in section {target_section_id}."
                            )
                            return MoodleModule(**module_data)
                    logger.warning(
                        f"Module '{target_module_name}' not found in section {target_section_id}."
                    )
                    return None  # Module not found in the target section

            logger.warning(
                f"Section {target_section_id} not found in course {course_id}."
            )
            return None  # Target section not found
        except MoodleAPIError as e:
            logger.error(
                f"Moodle API Error while searching for module '{target_module_name}': {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error while searching for module '{target_module_name}': {e}"
            )
            return None

    def get_folder_files(self, folder_cmid: int) -> List[MoodleFile]:
        """Retrieves a list of files within a specific folder module."""
        logger.info(f"Fetching files for folder module ID (cmid): {folder_cmid}")
        try:
            # mod_folder_get_folders_by_courses expects 'courseids' but can work with a single cmid
            # if the web service is set up to allow it or if we wrap it.
            # A common way is to get course contents and filter.
            # However, if we have cmid, core_course_get_course_module might give some info,
            # but not directly file list.
            # The most reliable is often core_course_get_contents for the module itself if it's detailed enough,
            # or a specific mod_folder function.
            # Let's assume `core_course_get_module` (if it exists and gives file info) or parse `core_course_get_contents`.

            # Using core_course_get_contents for the specific module:
            # This requires knowing the section the module is in, or getting all course contents.
            # A more direct approach if available:
            # payload = {"cmids": [folder_cmid]} # For functions that accept cmids
            # For `mod_folder_get_folders_by_courses`, it expects course IDs, not cmids directly.
            # It returns all folders in given courses. We'd need to filter.

            # Let's try to get the module by its cmid first to confirm it's a folder
            # then use its instance id with a folder-specific function if one exists,
            # or parse its contents if available from a general get_contents call.

            # This is a simplification: core_course_get_course_module by itself doesn't list files.
            # We typically need to use core_course_get_contents and look for the module, then its files.
            # Or, if a folder's files are listed under its 'contents' in core_course_get_module response.

            # A robust way:
            # 1. Get module details using core_course_get_course_module(cmid) to get its instance id and section.
            # 2. Get section contents using core_course_get_contents(courseid, options={'sectionid': section.id})
            # 3. Find the module in the section contents and extract files from its 'contents' or 'contentsinfo'.
            # This is complex.

            # Simpler attempt: Assume `core_course_get_course_module` might have 'contents' for folders.
            # This is often true for Moodle's mobile format additions.
            module_details = self._make_request(
                "core_course_get_course_module", payload_params={"cmid": folder_cmid}
            )

            if not module_details or "cm" not in module_details:
                logger.error(f"Could not retrieve details for module ID {folder_cmid}")
                return []

            cm_info = module_details["cm"]
            if cm_info.get("modname") != "folder":
                logger.warning(
                    f"Module ID {folder_cmid} is not a folder, it's a '{cm_info.get('modname')}'."
                )
                return []

            files_data = []
            if "contents" in cm_info and isinstance(cm_info["contents"], list):
                for file_info in cm_info["contents"]:
                    if file_info.get("type") == "file":
                        # Ensure all required fields for MoodleFile are present
                        if all(
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

            if not files_data:
                logger.info(
                    f"No files found directly in 'contents' of module {folder_cmid}. This might mean the folder is empty or files are nested deeper (not supported by this simple fetch)."
                )

            logger.info(
                f"Found {len(files_data)} files in folder module ID {folder_cmid}."
            )
            return files_data

        except MoodleAPIError as e:
            logger.error(
                f"Moodle API Error while fetching files for folder {folder_cmid}: {e}"
            )
            return []
        except Exception as e:
            logger.exception(
                f"Unexpected error while fetching files for folder {folder_cmid}: {e}"
            )
            return []

    def download_file(self, file_url: str, download_dir: Path, filename: str) -> Path:
        """Downloads a file from a Moodle file URL to a local directory."""
        if not self.config.token:  # File URLs from Moodle often require the token
            raise MoodleAPIError(
                "Moodle token not configured, cannot download files securely."
            )

        # Ensure download_dir exists (though BaseConfig should handle its root)
        download_dir.mkdir(parents=True, exist_ok=True)
        local_filepath = download_dir / filename

        logger.info(f"Downloading Moodle file from {file_url} to {local_filepath}")

        try:
            # Moodle file URLs might already include the token if generated by API,
            # or sometimes they need it appended. If self.session has the token in params,
            # it might be automatically used. For direct URL download, it's safer to ensure
            # the URL itself is complete or the session handles auth.
            # The `fileurl` from Moodle usually includes `?token=...`

            # Use a new session for download if params on self.session interfere,
            # or ensure self.session is suitable. For now, use self.session.
            # If file_url already has token, session token might be redundant or conflict.
            # Let's assume file_url is directly usable.

            # Create a direct request without using session params to avoid wsfunction
            with requests.get(
                file_url,
                params={"wstoken": self.config.token}
                if "wstoken" not in file_url
                else None,
                stream=True,
            ) as r:
                r.raise_for_status()
                with open(local_filepath, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
            logger.info(f"Successfully downloaded {filename} to {local_filepath}")
            return local_filepath
        except requests.exceptions.HTTPError as http_err:
            logger.error(
                f"HTTP error downloading {filename}: {http_err} (URL: {file_url})"
            )
            raise MoodleAPIError(
                f"Failed to download file '{filename}': {http_err}"
            ) from http_err
        except Exception as e:
            logger.exception(f"Error downloading file {filename} from {file_url}: {e}")
            raise MoodleAPIError(
                f"Unexpected error downloading file '{filename}': {e}"
            ) from e


if __name__ == "__main__":
    # This is for basic testing and requires a .env file with Moodle credentials
    # and a running Moodle instance.
    # Ensure MOODLE_URL and MOODLE_TOKEN are set in your .env file.
    from src.entrenai.config import moodle_config  # Local import for testing

    if not moodle_config.url or not moodle_config.token:
        print("MOODLE_URL and MOODLE_TOKEN must be set in .env for this test.")
    else:
        client = MoodleClient(config=moodle_config)

        test_user_id = 2
        print(f"\nAttempting to get courses for user ID: {test_user_id}...")
        # ... (rest of the __main__ block remains the same) ...
        try:
            courses = client.get_courses_by_user(test_user_id)
            if courses:
                print(f"Successfully retrieved {len(courses)} courses:")
                for course in courses:
                    print(
                        f"  - ID: {course.id}, Name: {course.fullname} (Shortname: {course.shortname})"
                    )
            else:
                print(
                    f"No courses found for user ID: {test_user_id} or an error occurred."
                )
        except MoodleAPIError as e:
            print(f"Moodle API Error during testing get_courses_by_user: {e}")
        except Exception as e:
            print(f"Generic error during testing get_courses_by_user: {e}")

        print("\nAttempting to get all courses...")
        try:
            all_courses = client.get_all_courses()
            if all_courses:
                print(f"Successfully retrieved {len(all_courses)} total courses:")
                for i, course in enumerate(
                    all_courses[:5]
                ):  # Show only first 5 courses
                    print(
                        f"  - ID: {course.id}, Name: {course.fullname} (Shortname: {course.shortname})"
                    )
                if len(all_courses) > 5:
                    print(f"  ... and {len(all_courses) - 5} more courses.")
            else:
                print("No courses found or an error occurred.")
        except MoodleAPIError as e:
            print(f"Moodle API Error during testing get_all_courses: {e}")
        except Exception as e:
            print(f"Generic error during testing get_all_courses: {e}")

        print("\nAttempting to get site info...")
        try:
            site_info = client._make_request("core_webservice_get_site_info")
            print("Site Info (raw):")
            print(json.dumps(site_info, indent=2))
            print("\nParsed Site Info:")
            print(f"  Sitename: {site_info.get('sitename')}")
            print(f"  User ID: {site_info.get('userid')}")
            print(f"  Fullname: {site_info.get('fullname')}")
        except MoodleAPIError as e:
            print(f"Moodle API Error during testing _make_request (get_site_info): {e}")
        except Exception as e:
            print(f"Generic error during testing _make_request (get_site_info): {e}")

# General Note:
# The Moodle Web Services API can be inconsistent. Functions might be disabled,
# or return data in slightly different formats than expected.
# Thorough testing against a real Moodle instance is crucial.
