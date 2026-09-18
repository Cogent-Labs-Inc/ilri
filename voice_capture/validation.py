from pathlib import PurePath

from voice_capture.constants import ALLOWED_AUDIO_FORMATS, MAX_AUDIO_BYTES, MAX_TRANSCRIPT_CHARS, MIN_TRANSCRIPT_WORDS
from voice_capture.enums import RejectionReason
from voice_capture.exceptions import InputRejected


def validate_transcript(transcript):
    cleaned_transcript = (transcript or "").strip()
    if not cleaned_transcript:
        raise InputRejected(RejectionReason.EMPTY_INPUT, "No transcript text was provided.")

    if len(cleaned_transcript) > MAX_TRANSCRIPT_CHARS:
        raise InputRejected(RejectionReason.INPUT_TOO_LARGE, f"The transcript exceeds {MAX_TRANSCRIPT_CHARS} characters.")

    if len(cleaned_transcript.split()) < MIN_TRANSCRIPT_WORDS:
        message = f"The transcript has fewer than {MIN_TRANSCRIPT_WORDS} words, too little to be a quarterly update."
        raise InputRejected(RejectionReason.TOO_SHORT, message)

    return cleaned_transcript


def validate_audio(audio, filename):
    audio_format = PurePath(filename or "").suffix.lower().lstrip(".")
    if audio_format not in ALLOWED_AUDIO_FORMATS:
        allowed = ", ".join(sorted(ALLOWED_AUDIO_FORMATS))
        raise InputRejected(RejectionReason.UNSUPPORTED_AUDIO_FORMAT, f"Unsupported audio format. Allowed: {allowed}.")

    if not audio:
        raise InputRejected(RejectionReason.EMPTY_INPUT, "The audio file is empty.")

    if len(audio) > MAX_AUDIO_BYTES:
        raise InputRejected(RejectionReason.INPUT_TOO_LARGE, "The audio file is larger than 25 MB.")

    return audio_format
