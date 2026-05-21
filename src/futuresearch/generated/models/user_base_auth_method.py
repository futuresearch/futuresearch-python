from enum import Enum


class UserBaseAuthMethod(str, Enum):
    API_KEY = "api_key"
    JWT = "jwt"

    def __str__(self) -> str:
        return str(self.value)
