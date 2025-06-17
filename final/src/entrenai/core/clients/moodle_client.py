



class MoodleClient:
    def __init__(self, config: MoodleConfig):
        self.config = config

    def get_courses(self):
        pass

    def get_course_sections(self, course_id: int):
        pass

    def get_course_modules(self, course_id: int):
        pass

    def create_entrenai_section(self, course_id: int):
        pass

    def _make_request(self, method: str, url: str, data: dict = None):
        pass