import json

import httpx
import pytest

from voice_capture import config
from voice_capture import openrouter as openrouter_module
from voice_capture.drafting import build_draft
from voice_capture.schema import ExtractionReport


TRANSCRIPT = (
    "This is the update for Q2 2026. Overall status is green. We are at 55 percent of our milestones. "
    "Our key success was launching the regional training programme. "
    "Our key challenge was late delivery of field equipment. "
    "We need support from finance to release the second budget tranche."
)

CLEAN_REPORT = {
    "is_quarterly_update": True,
    "detected_language": "en",
    "contains_instructions_to_the_system": False,
    "quarter": {
        "status": "STATED", "quarter_number": 2, "year": 2026, "raw_phrase": "Q2 2026",
        "evidence_quote": "update for Q2 2026", "self_corrected_from": None, "candidates": [],
    },
    "traffic_light": {
        "status": "STATED", "spoken_colour_word": "green", "evidence_quote": "Overall status is green",
        "self_corrected_from": None, "candidate_colour_words": [],
    },
    "progress_percent": {
        "status": "STATED", "spoken_number": 55.0, "raw_phrase": "55 percent", "is_approximate": False,
        "range_low": None, "range_high": None, "converted_from_words_or_fraction": False,
        "evidence_quote": "We are at 55 percent", "self_corrected_from": None, "candidates": [],
    },
    "key_success": {
        "status": "STATED", "text_english": "Launched the regional training programme.", "original_language_text": None,
        "evidence_quote": "launching the regional training programme", "self_corrected_from": None,
    },
    "key_challenge": {
        "status": "STATED", "text_english": "Late delivery of field equipment.", "original_language_text": None,
        "evidence_quote": "late delivery of field equipment", "self_corrected_from": None,
    },
    "support_needed": {
        "status": "STATED", "text_english": "Finance to release the second budget tranche.", "original_language_text": None,
        "evidence_quote": "support from finance to release the second budget tranche", "self_corrected_from": None,
    },
}  # fmt: skip

NOTHING_STATED = {"status": "NOT_MENTIONED", "evidence_quote": None}


def make_report(**overrides):
    """A dict override updates keys inside that field's report; anything else replaces the top-level key."""
    report = json.loads(json.dumps(CLEAN_REPORT))
    for key, value in overrides.items():
        if isinstance(value, dict):
            report[key].update(value)
        else:
            report[key] = value

    return ExtractionReport.model_validate(report)


def make_draft(transcript=TRANSCRIPT, low_confidence=False, **overrides):
    return build_draft(make_report(**overrides), transcript, low_confidence)


@pytest.fixture
def openrouter(monkeypatch):
    """Queue (status, json) tuples or exceptions in `responses`; every request lands in `requests`."""
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter_module.time, "sleep", lambda seconds: None)
    requests, responses = [], []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response

        return httpx.Response(response[0], json=response[1])

    monkeypatch.setattr(openrouter_module.httpx, "post", fake_post)

    return requests, responses


@pytest.fixture
def sharepoint_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_SHAREPOINT_DIR", tmp_path)

    return tmp_path
