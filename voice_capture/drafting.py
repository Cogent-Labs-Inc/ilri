from voice_capture.constants import INJECTION_PATTERN, NOT_AN_UPDATE_MISSING_FIELDS
from voice_capture.enums import FieldStatus, FlagCode, RejectionReason, SchemaField, Verdict
from voice_capture.exceptions import InputRejected
from voice_capture.field_decisions import decide_field
from voice_capture.openrouter import extract_report, transcribe_audio
from voice_capture.schema import Draft, Flag
from voice_capture.validation import validate_audio, validate_transcript


def create_draft(transcript="", audio=None, audio_filename=""):
    """Transcript text or audio bytes -> Draft. Unusable input becomes a REJECTED draft, never a crash."""
    low_confidence = False
    try:
        if audio is not None:
            transcription = transcribe_audio(audio, validate_audio(audio, audio_filename))
            transcript, low_confidence = transcription.text, transcription.low_confidence

        transcript = validate_transcript(transcript)
        draft = build_draft(extract_report(transcript), transcript, low_confidence)
    except InputRejected as exc:
        draft = Draft(verdict=Verdict.REJECTED, transcript=transcript or "", rejection_reason=exc.reason, rejection_message=str(exc))

    return draft


def build_draft(report, transcript, low_confidence=False):
    """low_confidence is False for typed transcripts; True or None (no signal) from speech-to-text."""
    fields = {schema_field: decide_field(schema_field, getattr(report, schema_field), transcript) for schema_field in SchemaField}
    missing_fields = sum(result.status == FieldStatus.MISSING for result in fields.values())
    if not report.is_quarterly_update and missing_fields >= NOT_AN_UPDATE_MISSING_FIELDS:
        draft = Draft(
            verdict=Verdict.REJECTED,
            transcript=transcript,
            detected_language=report.detected_language,
            rejection_reason=RejectionReason.NOT_A_QUARTERLY_UPDATE,
            rejection_message="The input does not appear to be a quarterly update, so no draft was prepared.",
        )
    else:
        draft_flags = collect_draft_flags(report, transcript, low_confidence)
        needs_attention = any(flag.blocking for flag in draft_flags) or any(result.needs_attention for result in fields.values())
        draft = Draft(
            verdict=Verdict.NEEDS_ATTENTION if needs_attention else Verdict.READY_FOR_REVIEW,
            transcript=transcript,
            detected_language=report.detected_language,
            fields=fields,
            flags=draft_flags,
        )

    return draft


def collect_draft_flags(report, transcript, low_confidence):
    draft_flags = []
    if report.contains_instructions_to_the_system or INJECTION_PATTERN.search(transcript):
        message = "The transcript contains text that looks like instructions to the AI. Check every value against the transcript."
        draft_flags.append(Flag(code=FlagCode.POSSIBLE_INJECTION, message=message, blocking=True))

    if low_confidence:
        message = "Speech-to-text reported low confidence for part of the audio; check the transcript."
        draft_flags.append(Flag(code=FlagCode.LOW_TRANSCRIPT_CONFIDENCE, message=message))
    elif low_confidence is None:
        message = "Speech-to-text gave no confidence signals; the transcript is unverified."
        draft_flags.append(Flag(code=FlagCode.TRANSCRIPT_QUALITY_UNAVAILABLE, message=message))

    return draft_flags
