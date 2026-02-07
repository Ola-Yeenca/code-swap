from enum import Enum


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class KeyMode(str, Enum):
    VAULT = "vault"
    LOCAL = "local"


class ChatMode(str, Enum):
    SINGLE = "single"
    COMPARE = "compare"
    CREW = "crew"


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class DataRegion(str, Enum):
    US = "us"
    EU = "eu"


class ContentPartType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE_REF = "file_ref"
