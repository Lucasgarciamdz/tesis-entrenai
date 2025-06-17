from dotenv import load_dotenv

load_dotenv()


class MoodleConfig:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token

    def get_base_url(self):
        return self.base_url

    def get_token(self):
        return self.token