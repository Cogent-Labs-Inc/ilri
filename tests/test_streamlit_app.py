"""Smoke tests for streamlit_app.py.

streamlit_app.py stays disclosed as throwaway/vibe-coded/not reviewed (see its own docstring) -
these tests exist so a broken import or a crash on the three flows that matter (happy path,
rejection, and the blocked-field confirmation gate) is caught, not to cover every branch of a UI
that's explicitly out of scope for this exercise.
"""

import json

from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import TRANSCRIPT, make_report

from voice_capture import drafting

APP_PATH = str(Path(__file__).parent.parent / "streamlit_app.py")


def test_app_renders_with_no_open_drafts():
    at = AppTest.from_file(APP_PATH).run()
    assert not at.exception


def test_submit_review_approve_happy_path(monkeypatch, sharepoint_dir):
    monkeypatch.setattr(drafting, "extract_report", lambda transcript: make_report())

    at = AppTest.from_file(APP_PATH).run()
    at.tabs[0].text_area[0].set_value(TRANSCRIPT)
    at.tabs[0].button[0].click().run()
    assert not at.exception
    assert "Draft #1 created" in at.tabs[0].success[0].value

    approve_button = next(b for b in at.tabs[1].button if b.label == "Approve")
    approve_button.click().run()
    assert not at.exception
    assert json.loads(at.tabs[2].json[0].value)["traffic_light"] == "Green"


def test_unusable_input_is_rejected_with_a_warning():
    at = AppTest.from_file(APP_PATH).run()
    at.tabs[0].text_area[0].set_value("hi")
    at.tabs[0].button[0].click().run()
    assert not at.exception
    assert at.tabs[0].warning
    assert not at.tabs[0].success


def test_blocked_field_needs_confirmation_before_approval(monkeypatch, sharepoint_dir):
    transcript = TRANSCRIPT.replace("green", "yellow")
    report = make_report(traffic_light={"spoken_colour_word": "yellow", "evidence_quote": "Overall status is yellow"})
    monkeypatch.setattr(drafting, "extract_report", lambda _: report)

    at = AppTest.from_file(APP_PATH).run()
    at.tabs[0].text_area[0].set_value(transcript)
    at.tabs[0].button[0].click().run()
    assert not at.exception

    next(b for b in at.tabs[1].button if b.label == "Approve").click().run()
    assert not at.exception
    assert at.tabs[1].error  # blocked field wasn't confirmed - approval refused
    assert not at.tabs[2].json

    at.tabs[1].checkbox[0].check().run()
    next(b for b in at.tabs[1].button if b.label == "Approve").click().run()
    assert not at.exception
    assert json.loads(at.tabs[2].json[0].value)["traffic_light"] == "Amber"
