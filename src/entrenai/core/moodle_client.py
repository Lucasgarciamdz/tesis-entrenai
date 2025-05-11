import requests
import json  # Added import for json.dumps
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import MoodleConfig
from src.entrenai.core.models import (
    MoodleCourse,
    MoodleSection,
    MoodleModule,
)  # Add more as needed
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
            self.base_url = urljoin(config.url, "/webservice/rest/server.php")

        self.session = session or requests.Session()
        if self.config.token:  # Only update params if token exists
            self.session.params.update(
                {  # type: ignore
                    "wstoken": self.config.token,
                    "moodlewsrestformat": "json",
                }
            )

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

        # Determine the new prefix format based on whether the current prefix is empty or not
        # This logic ensures correct formatting like 'keyname' for the first level dict,
        # then 'keyname[subkey]' or 'keyname[0]'
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
        self, wsfunction: str, payload_params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Helper method to make requests to the Moodle API using POST with form data.
        """
        if not self.base_url:
            logger.error(
                f"MoodleClient is not configured with a base URL. Cannot make request for '{wsfunction}'."
            )
            raise MoodleAPIError("MoodleClient not configured with base URL.")
        if not self.config.token:
            logger.error(
                f"Moodle token not configured. Cannot make authenticated request for '{wsfunction}'."
            )
            raise MoodleAPIError("Moodle token not configured.")

        # Prepare base data for the POST request body
        request_data: Dict[str, Any] = {
            "wsfunction": wsfunction,
            "wstoken": self.config.token,
            "moodlewsrestformat": "json",
        }

        if payload_params:
            # Format complex parameters if any, and merge them into request_data
            # The _format_moodle_params expects a dict where keys are the top-level param names
            # e.g. if Moodle expects 'courses[0][id]', payload_params should be {'courses': [{'id': ...}]}
            formatted_payload = self._format_moodle_params(payload_params)
            request_data.update(formatted_payload)

        response: Optional[requests.Response] = None  # Initialize response

        try:
            # Using data= for application/x-www-form-urlencoded
            response = self.session.post(self.base_url, data=request_data)
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)

            data = response.json()

            # Moodle API specific error checking (some errors return 200 OK but contain an error message)
            if isinstance(data, dict) and data.get("exception"):
                logger.error(f"Moodle API error for function '{wsfunction}': {data}")
                raise MoodleAPIError(
                    message=f"Moodle API Exception: {data.get('message', 'Unknown Moodle error')}",
                    response_data=data,
                )
            if (
                isinstance(data, list)
                and data
                and isinstance(data[0], dict)
                and data[0].get("exception")
            ):  # some functions return a list of errors
                logger.error(f"Moodle API error for function '{wsfunction}': {data[0]}")
                raise MoodleAPIError(
                    message=f"Moodle API Exception: {data[0].get('message', 'Unknown Moodle error')}",
                    response_data=data[0],
                )
            return data
        except requests.exceptions.HTTPError as http_err:
            err_msg = f"HTTP error occurred while calling Moodle function '{wsfunction}': {http_err}"
            resp_text = (
                response.text if response is not None else "No response text available"
            )
            status = response.status_code if response is not None else None
            logger.error(f"{err_msg} - Response: {resp_text}")
            raise MoodleAPIError(
                message=str(http_err), status_code=status, response_data=resp_text
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(
                f"Request exception occurred while calling Moodle function '{wsfunction}': {req_err}"
            )
            raise MoodleAPIError(message=str(req_err)) from req_err
        except ValueError as json_err:  # Includes JSONDecodeError
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
        """
        Retrieves courses for a specific user.
        Uses `core_enrol_get_users_courses` typically.
        """
        logger.info(f"Fetching courses for user_id: {user_id}")
        payload = {"userid": user_id}
        try:
            # Parameters for core_enrol_get_users_courses are simple, no complex formatting needed here by _format_moodle_params
            # but _make_request will handle adding wsfunction, token etc.
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

    # Placeholder for other methods to be implemented in Fase 2.1:
    # def create_folder_in_section(self, course_id: int, section_id: int, folder_name: str) -> MoodleFolder: ...
    # def create_url_in_section(self, course_id: int, section_id: int, url_name: str, external_url: str, description: Optional[str] = None) -> MoodleUrl: ...
    # def get_folder_contents(self, folder_id: int) -> List[MoodleFile]: ... # folder_id is usually the course module id (cmid)
    # def download_file(self, file_url: str, local_path: str) -> None: ...

    def create_module_in_section(
        self,
        course_id: int,
        section_id: int,  # This is the Moodle section ID (pk from course_sections table)
        module_name: str,
        mod_type: str,  # e.g., "folder", "url", "resource" (for file uploads)
        instance_params: Optional[Dict[str, Any]] = None,  # Specific to the mod_type
        common_module_options: Optional[
            List[Dict[str, Any]]
        ] = None,  # e.g., visible, idnumber
    ) -> Optional[MoodleModule]:
        """
        Adds a new module (like a folder or URL) to a specific course section.
        Uses 'core_course_add_module'.
        Note: 'section_id' here is the actual ID of the course section, not its number/order.
              'core_course_add_module' expects 'sectionreturn' to get module details back.
        """
        logger.info(
            f"Attempting to add module '{module_name}' (type: {mod_type}) to course {course_id}, section {section_id}"
        )

        # Construct the 'modules' payload structure for core_course_add_module
        # This function expects a list of modules to add, even if it's just one.
        module_data: Dict[str, Any] = {
            "modname": mod_type,
            "name": module_name,  # Name of the folder or URL resource
            "section": section_id,  # The ID of the course_sections record
            # "visible": 1, # Default to visible, can be overridden by common_module_options
            # "groupmode": 0, # Default group mode
            # "groupingid": 0, # Default grouping ID
        }

        # Add instance-specific parameters (these are usually flat key-values for the module type)
        # For 'url', this would be {'externalurl': 'http://...', 'display': 0}
        # For 'folder', this might include 'intro', 'display', 'showexpanded'
        # These are typically passed as options with name/value pairs.
        # The Moodle API for core_course_add_module is a bit tricky with how it handles
        # module-specific settings. Often, they are passed within an 'options' array.
        # Let's structure instance_params to be part of these options.

        options_list: List[Dict[str, Any]] = common_module_options or []

        if instance_params:
            for key, value in instance_params.items():
                options_list.append(
                    {"name": key, "value": str(value)}
                )  # Values often need to be strings

        if options_list:
            module_data["options"] = options_list

        # The wsfunction expects a list of modules under the 'modules' key
        payload = {"courseid": course_id, "modules": [module_data]}

        try:
            # core_course_add_module returns a list of module IDs and potentially warnings.
            # To get full module details, we might need another call or ensure 'sectionreturn' is handled.
            # The 'sectionreturn' parameter in core_course_add_module can specify which section's
            # content to return, which would include the new module.
            # However, it's often simpler to just get the cmid (course module id) back.

            # The response structure is typically like:
            # [{'id': cmid, 'instance': instanceid, 'name': 'My Folder', 'visible': 1, ...}]
            # Or it might be just warnings if something went slightly wrong but it still created.
            # Or an error object.

            # Let's try to get the module details back by asking for the sectionreturn.
            # This might not always work or might be too verbose.
            # A simpler response is just the cmid.
            # For now, let's assume it returns enough info to populate MoodleModule.
            # The function `core_course_add_module` does not directly return the module details in a rich format.
            # It returns a list of `cmid` (course module id) and `instanceid`.
            # Example response: `[{"id": cm_id, "instance": instance_id, "warnings": []}]`

            response_data = self._make_request(
                "core_course_add_module", payload_params=payload
            )

            if not isinstance(response_data, list) or not response_data:
                logger.error(
                    f"Failed to add module or unexpected response: {response_data}"
                )
                return None

            # Assuming the first item in the list corresponds to our added module
            added_module_info = response_data[0]

            if "id" not in added_module_info or "instance" not in added_module_info:
                logger.error(
                    f"Response from core_course_add_module missing 'id' or 'instance': {added_module_info}"
                )
                # Check for warnings, as Moodle sometimes returns warnings instead of errors
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

            # Construct a MoodleModule object. We might not have all details from this call.
            # A follow-up call to core_course_get_course_module (cmid) or
            # core_course_get_contents (for the section) would be needed for full details.
            # For now, return what we have.
            return MoodleModule(
                id=cmid,
                name=module_name,  # Name we intended
                modname=mod_type,
                instance=instance_id,
                # Other fields like 'visible', 'url' (for URL module) would need another fetch.
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
        """Creates a folder in the specified course section."""
        logger.info(
            f"Creating folder '{folder_name}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "intro": intro or f"Carpeta para {folder_name}",  # Summary for the folder
            "introformat": 1,  # HTML format for intro
            "display": 0,  # 0 = Display folder contents on a separate page
            "showexpanded": 1,  # 1 = Show subfolders expanded by default
        }
        # Common module options like visibility can be passed here if needed
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
        display_mode: int = 0,  # 0=auto, 1=embed, 2=open, 3=popup
    ) -> Optional[MoodleModule]:
        """Creates a URL resource in the specified course section."""
        logger.info(
            f"Creating URL '{url_name}' -> '{external_url}' in course {course_id}, section {section_id}"
        )
        instance_params = {
            "externalurl": external_url,
            "intro": description or f"Enlace a {url_name}",
            "introformat": 1,  # HTML format
            "display": display_mode,
        }
        # Common module options like visibility can be passed here if needed
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
        """
        Creates a new course section using the local_wsmanagesections plugin.
        First creates the section structure, then updates its name.
        Position 0 is typically the first section after "General".
        """
        logger.info(
            f"Attempting to create section '{section_name}' in course {course_id} at position {position}"
        )
        try:
            # Step 1: Create the section structure
            create_payload = {
                "courseid": course_id,
                "position": position,  # Position where the new section(s) should be created.
                "number": 1,  # Number of sections to create.
            }
            # Response from local_wsmanagesections_create_sections is expected to be a list of created sections.
            # Example: [{'id': 123, 'section': 1, 'name': 'New Section Name from Update', ...}]
            created_sections_data = self._make_request(
                "local_wsmanagesections_create_sections", payload_params=create_payload
            )

            if not isinstance(created_sections_data, list) or not created_sections_data:
                logger.error(
                    f"Failed to create section structure or unexpected response: {created_sections_data}"
                )
                return None

            # Assuming the first element in the list is our newly created section
            # and it contains an 'id' or 'section' (number) that we can use.
            # The plugin docs/examples should clarify the exact response structure.
            # Let's assume it returns at least an 'id'.
            new_section_info = created_sections_data[0]
            new_section_id = new_section_info.get("id")
            new_section_number = new_section_info.get(
                "section"
            )  # This is the Moodle section number (0, 1, 2...)

            if new_section_id is None:
                logger.error(
                    f"Created section data does not contain an 'id': {new_section_info}"
                )
                return None

            logger.info(
                f"Section structure created with ID: {new_section_id}, Number: {new_section_number}. Now updating name."
            )

            # Step 2: Update the newly created section's name (and other properties if needed)
            update_payload = {
                "courseid": course_id,
                "sections": [  # This needs to be a list of section objects to update
                    {
                        "id": new_section_id,  # Use the ID of the newly created section
                        "name": section_name,
                        "visible": 1,  # Make it visible
                        # Add other parameters like 'summary', 'summaryformat' as needed
                        # "summary": f"Contenido para {section_name}",
                        # "summaryformat": 1, # 1 = HTML
                    }
                ],
            }
            # local_wsmanagesections_update_sections usually returns a status or the updated sections.
            # The example shows `print(sec.updatesections)`, implying it returns something.
            update_response = self._make_request(
                "local_wsmanagesections_update_sections", payload_params=update_payload
            )

            # We need to confirm the structure of update_response.
            # Assuming it returns a list of updated sections, or a status.
            # For now, let's try to re-fetch the section to get its final state.
            logger.info(
                f"Update request for section ID {new_section_id} sent. Response: {update_response}"
            )

            # Step 3: Get the updated section details to return
            # local_wsmanagesections_get_sections can take sectionids
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
                # Fallback: construct a MoodleSection with what we know if retrieval fails
                return MoodleSection(
                    id=new_section_id,
                    name=section_name,
                    section=new_section_number
                    if new_section_number is not None
                    else position,
                )

            final_section_data = updated_section_data_list[0]
            # Ensure the name matches, though it should if update was successful
            if final_section_data.get("name") != section_name:
                logger.warning(
                    f"Section name after update ('{final_section_data.get('name')}') "
                    f"differs from target ('{section_name}'). Using actual name."
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

    # ensure_course_section method was here, it's removed as create_course_section with plugin is more direct.
    # If ensure logic is still needed, it would use local_wsmanagesections_get_sections and then create/update.


if __name__ == "__main__":
    # This is for basic testing and requires a .env file with Moodle credentials
    # and a running Moodle instance.
    # Ensure MOODLE_URL and MOODLE_TOKEN are set in your .env file.
    from src.entrenai.config import moodle_config  # Local import for testing

    if not moodle_config.url or not moodle_config.token:
        print("MOODLE_URL and MOODLE_TOKEN must be set in .env for this test.")
    else:
        client = MoodleClient(config=moodle_config)

        # Replace with a valid user ID from your Moodle instance
        # Often, admin user ID is 2, but check your Moodle.
        test_user_id = 2
        print(f"\nAttempting to get courses for user ID: {test_user_id}...")
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

        # Example: Test _make_request with a generic Moodle function like 'core_webservice_get_site_info'
        # This function takes no specific payload parameters beyond the standard ones.
        print("\nAttempting to get site info...")
        try:
            site_info = client._make_request(
                "core_webservice_get_site_info"
            )  # No payload_params needed
            print("Site Info (raw):")
            print(json.dumps(site_info, indent=2))  # Pretty print the JSON
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
# The `core_enrol_get_users_courses` function, for example, might require specific
# capabilities for the user associated with the token.
# An alternative for getting courses might be `core_course_get_courses` and then filtering,
# or `core_course_get_enrolled_courses_by_timeline_classification` with classification 'all'.
