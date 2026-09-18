import re

from voice_capture.enums import SchemaField


REQUIRED_FIELDS = frozenset({SchemaField.QUARTER, SchemaField.TRAFFIC_LIGHT, SchemaField.PROGRESS_PERCENT})
NARRATIVE_FIELDS = frozenset({SchemaField.KEY_SUCCESS, SchemaField.KEY_CHALLENGE, SchemaField.SUPPORT_NEEDED})

QUARTER_PATTERN = r"^Q[1-4]( 20\d{2})?$"
NARRATIVE_MAX_CHARS = 200
PROGRESS_MIN = 0
PROGRESS_MAX = 100
NOT_AN_UPDATE_MISSING_FIELDS = 5

MIN_TRANSCRIPT_WORDS = 5
MAX_TRANSCRIPT_CHARS = 20_000
MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_FORMATS = frozenset({"mp3", "wav", "m4a", "webm", "ogg", "flac", "aac"})

MAX_REQUEST_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
LOW_CONFIDENCE_AVG_LOGPROB = -1.0
HIGH_NO_SPEECH_PROBABILITY = 0.6

# Spoken colour words (English, French, Spanish, Swahili); keys are normalised text.
COLOUR_WORDS = {
    "red": "Red", "rouge": "Red", "rojo": "Red", "nyekundu": "Red",
    "amber": "Amber", "ambre": "Amber", "ambar": "Amber",
    "green": "Green", "vert": "Green", "verde": "Green", "kijani": "Green",
    "blue": "Blue", "bleu": "Blue", "azul": "Blue", "bluu": "Blue",
    "yellow": "Amber", "orange": "Amber", "jaune": "Amber",
    "amarillo": "Amber", "naranja": "Amber", "njano": "Amber",
}
SUGGESTED_COLOUR_WORDS = frozenset({"yellow", "orange", "jaune", "amarillo", "naranja", "njano"})

FILLER_WORDS = frozenset({"um", "uh", "erm", "hmm", "ah"})
GROUNDING_MIN_SCORE = 90

INJECTION_PATTERN = re.compile(
    r"\bignore\b.{0,40}\b(instructions?|prompts?|rules?)\b"
    r"|\b(system|developer)\s+prompt\b"
    r"|\b(disregard|override|bypass)\b.{0,40}\b(instructions?|rules?|guardrails?|validation)\b"
    r"|\byou are now\b"
    r"|\bset (all|every|each) (of )?(the )?fields?\b",
    re.IGNORECASE,
)
