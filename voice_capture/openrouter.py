import base64
import time

import httpx

from pydantic import ValidationError

from voice_capture import config
from voice_capture.constants import (
    HIGH_NO_SPEECH_PROBABILITY,
    LOW_CONFIDENCE_AVG_LOGPROB,
    MAX_REQUEST_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    RETRYABLE_STATUS_CODES,
)
from voice_capture.enums import RejectionReason
from voice_capture.exceptions import CaptureConfigurationError, InputRejected
from voice_capture.prompts import build_messages
from voice_capture.schema import ExtractionReport, Transcription


def post_to_openrouter(path, payload, failure_reason):
    if not config.OPENROUTER_API_KEY:
        raise CaptureConfigurationError("OPENROUTER_API_KEY is not set. Add it to .env.")

    body, error, attempts, retryable = None, "", 0, True
    while body is None and retryable and attempts < MAX_REQUEST_ATTEMPTS:
        attempts += 1
        try:
            response = httpx.post(
                f"{config.OPENROUTER_BASE_URL}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
                timeout=config.OPENROUTER_TIMEOUT_SECONDS,
            )

        except httpx.TransportError as exc:
            error = f"The AI service was unavailable ({type(exc).__name__})."

        else:
            body = response.json() if response.is_success else None
            error = f"The AI service returned HTTP {response.status_code}."
            retryable = response.status_code in RETRYABLE_STATUS_CODES

        if body is None and retryable and attempts < MAX_REQUEST_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    if body is None:
        raise InputRejected(failure_reason, error)

    return body


def transcribe_audio(audio, audio_format):
    payload = {
        "model": config.TRANSCRIPTION_MODEL,
        "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": audio_format},
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment"],
        "temperature": 0,
    }

    body = post_to_openrouter("/audio/transcriptions", payload, RejectionReason.TRANSCRIPTION_UNAVAILABLE)
    text = (body.get("text") or "").strip()
    if not text:
        raise InputRejected(RejectionReason.NO_SPEECH, "No speech was detected in the audio.")

    return Transcription(text=text, low_confidence=is_low_confidence(body.get("segments") or []))


def is_low_confidence(segments):
    """None when Whisper returned no confidence signals at all."""
    scored_segments = [segment for segment in segments if "avg_logprob" in segment or "no_speech_prob" in segment]
    any_weak_segment = any(
        segment.get("avg_logprob", 0.0) < LOW_CONFIDENCE_AVG_LOGPROB
        or segment.get("no_speech_prob", 0.0) > HIGH_NO_SPEECH_PROBABILITY
        for segment in scored_segments
    )

    return any_weak_segment if scored_segments else None


def extract_report(transcript):
    payload = {
        "model": config.EXTRACTION_MODEL,
        "temperature": 0,
        "messages": build_messages(transcript),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "quarterly_update_report", "strict": True, "schema": ExtractionReport.model_json_schema()},
        },
        "provider": {"require_parameters": True},
    }

    body = post_to_openrouter("/chat/completions", payload, RejectionReason.EXTRACTION_UNAVAILABLE)
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}

    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        reason = message.get("refusal") or "content filter"
        raise InputRejected(RejectionReason.EXTRACTION_REFUSED, f"The model declined to extract: {reason}.")

    if choice.get("finish_reason") == "length":
        raise InputRejected(RejectionReason.EXTRACTION_INVALID, "The model's output was cut off before it was complete.")

    try:
        report = ExtractionReport.model_validate_json(message.get("content") or "")
    except ValidationError as exc:
        raise InputRejected(RejectionReason.EXTRACTION_INVALID, "The model's output did not match the report schema.") from exc

    return report
