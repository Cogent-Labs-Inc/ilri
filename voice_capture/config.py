from pathlib import Path

from decouple import config as env


OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
OPENROUTER_TIMEOUT_SECONDS = env("OPENROUTER_TIMEOUT_SECONDS", default=60.0, cast=float)
EXTRACTION_MODEL = env("EXTRACTION_MODEL", default="openai/gpt-5.4-mini")
TRANSCRIPTION_MODEL = env("TRANSCRIPTION_MODEL", default="openai/whisper-1")
MOCK_SHAREPOINT_DIR = Path(env("MOCK_SHAREPOINT_DIR", default="var/mock_sharepoint"))
