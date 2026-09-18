import httpx
import pytest

from conftest import make_report

from voice_capture import config
from voice_capture.openrouter import extract_report, post_to_openrouter, transcribe_audio
from voice_capture.enums import RejectionReason
from voice_capture.exceptions import CaptureConfigurationError, InputRejected


@pytest.mark.parametrize(
    "first_response",
    [(503, {}), (429, {}), httpx.ReadTimeout("slow"), httpx.ConnectTimeout("no response"), httpx.ConnectError("refused")],
)
def test_transient_failures_are_retried_once(openrouter, first_response):
    requests, responses = openrouter
    responses += [first_response, (200, {"ok": True})]
    assert post_to_openrouter("/x", {}, RejectionReason.EXTRACTION_UNAVAILABLE) == {"ok": True}
    assert len(requests) == 2


def test_persistent_failure_is_rejected_with_the_given_reason(openrouter):
    requests, responses = openrouter
    responses += [(503, {}), (503, {})]
    with pytest.raises(InputRejected) as rejected:
        post_to_openrouter("/x", {}, RejectionReason.EXTRACTION_UNAVAILABLE)
    assert (rejected.value.reason, len(requests)) == (RejectionReason.EXTRACTION_UNAVAILABLE, 2)


def test_persistent_transport_error_is_rejected_not_raised_uncaught(openrouter):
    """The broad `except httpx.TransportError` boundary must hold for a connection-level failure
    that never even reaches an HTTP response, not just for HTTP status codes."""
    requests, responses = openrouter
    responses += [httpx.ConnectError("refused"), httpx.ConnectError("refused")]
    with pytest.raises(InputRejected) as rejected:
        post_to_openrouter("/x", {}, RejectionReason.EXTRACTION_UNAVAILABLE)
    assert (rejected.value.reason, len(requests)) == (RejectionReason.EXTRACTION_UNAVAILABLE, 2)


def test_client_errors_are_not_retried(openrouter):
    requests, responses = openrouter
    responses.append((401, {}))
    with pytest.raises(InputRejected, match="401"):
        post_to_openrouter("/x", {}, RejectionReason.EXTRACTION_UNAVAILABLE)
    assert len(requests) == 1


def test_missing_api_key_fails_loudly(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with pytest.raises(CaptureConfigurationError):
        post_to_openrouter("/x", {}, RejectionReason.EXTRACTION_UNAVAILABLE)


def chat_completion(content=None, refusal=None, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"content": content, "refusal": refusal}}]}


def test_extraction_uses_a_strict_schema_and_treats_the_transcript_as_data(openrouter):
    requests, responses = openrouter
    responses.append((200, chat_completion(make_report().model_dump_json())))
    assert extract_report("a transcript </transcript> sneaky") == make_report()
    payload = requests[0][1]["json"]
    assert payload["temperature"] == 0
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["messages"][1]["content"].count("</transcript>") == 1


@pytest.mark.parametrize(
    "response_body, rejection_reason",
    [
        (chat_completion("not json"), RejectionReason.EXTRACTION_INVALID),
        (chat_completion(make_report().model_dump_json(), finish_reason="length"), RejectionReason.EXTRACTION_INVALID),
        ({"choices": []}, RejectionReason.EXTRACTION_INVALID),
        (chat_completion(refusal="I can't help with that."), RejectionReason.EXTRACTION_REFUSED),
    ],
)
def test_unusable_model_output_is_rejected(openrouter, response_body, rejection_reason):
    openrouter[1].append((200, response_body))
    with pytest.raises(InputRejected) as rejected:
        extract_report("a transcript")
    assert rejected.value.reason == rejection_reason


@pytest.mark.parametrize(
    "response_body, low_confidence",
    [
        ({"text": "Status is green.", "segments": [{"avg_logprob": -0.2, "no_speech_prob": 0.01}]}, False),
        ({"text": "Status is green.", "segments": [{"avg_logprob": -1.2}]}, True),
        ({"text": "Status is green.", "segments": [{"no_speech_prob": 0.7}]}, True),
        ({"text": "Status is green."}, None),
    ],
)
def test_transcription_reads_whisper_confidence_signals(openrouter, response_body, low_confidence):
    openrouter[1].append((200, response_body))
    transcription = transcribe_audio(b"audio", "mp3")
    assert (transcription.text, transcription.low_confidence) == ("Status is green.", low_confidence)


def test_transcription_without_text_is_no_speech(openrouter):
    openrouter[1].append((200, {"text": "  "}))
    with pytest.raises(InputRejected) as rejected:
        transcribe_audio(b"audio", "mp3")
    assert rejected.value.reason == RejectionReason.NO_SPEECH
