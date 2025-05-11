import requests
import json  # Added import for json.dumps
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from src.entrenai.config import MoodleConfig
from src.entrenai.core.models import MoodleCourse  # Add more as needed
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

    def _make_request(
        self, wsfunction: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Helper method to make requests to the Moodle API.
        """
        if not self.base_url:
            logger.error(
                f"MoodleClient is not configured with a base URL. Cannot make request for '{wsfunction}'."
            )
            raise MoodleAPIError("MoodleClient not configured with base URL.")

        if params is None:
            params = {}

        all_params = {"wsfunction": wsfunction, **params}
        response: Optional[requests.Response] = None  # Initialize response

        try:
            response = self.session.post(self.base_url, params=all_params)
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
        params = {"userid": user_id}
        try:
            courses_data = self._make_request("core_enrol_get_users_courses", params)

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
    # def create_course_section(self, course_id: int, section_name: str) -> MoodleSection: ...
    # def create_folder_in_section(self, course_id: int, section_id: int, folder_name: str) -> MoodleFolder: ...
    # def create_url_in_section(self, course_id: int, section_id: int, url_name: str, external_url: str, description: Optional[str] = None) -> MoodleUrl: ...
    # def get_folder_contents(self, folder_id: int) -> List[MoodleFile]: ... # folder_id is usually the course module id (cmid)
    # def download_file(self, file_url: str, local_path: str) -> None: ...


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
        print("\nAttempting to get site info...")
        try:
            site_info = client._make_request("core_webservice_get_site_info")
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
