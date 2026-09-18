import json

import pytest

from conftest import TRANSCRIPT, make_draft
from pydantic import ValidationError

from voice_capture.approval import approve_draft
from voice_capture.drafting import create_draft
from voice_capture.exceptions import ApprovalNotPermitted
from voice_capture.schema import QuarterlyUpdate


REVIEWED_VALUES = {"quarter": " q2  2026 ", "traffic_light": "amber", "progress_percent": " 60 ", "key_success": "  Finished   the survey. "}


def test_schema_normalises_valid_values():
    assert QuarterlyUpdate.model_validate(REVIEWED_VALUES).model_dump(mode="json") == {
        "quarter": "Q2 2026",
        "traffic_light": "Amber",
        "progress_percent": 60,
        "key_success": "Finished the survey.",
        "key_challenge": None,
        "support_needed": None,
    }


@pytest.mark.parametrize(
    "invalid_value",
    [
        {"quarter": "Q5"},
        {"quarter": "second quarter"},
        {"quarter": ""},
        {"traffic_light": "Yellow"},
        {"progress_percent": "101"},
        {"progress_percent": "-1"},
        {"progress_percent": "65.5"},
        {"progress_percent": "\xb2"},
        {"key_challenge": "w" * 201},
    ],
)
def test_schema_rejects_invalid_values(invalid_value):
    with pytest.raises(ValidationError):
        QuarterlyUpdate.model_validate({**REVIEWED_VALUES, **invalid_value})


def ai_values_as_typed(draft):
    return {field: "" if result.value is None else str(result.value) for field, result in draft.fields.items()}


def test_approval_writes_final_values_next_to_ai_values(sharepoint_dir):
    draft = make_draft(support_needed={"status": "EXPLICITLY_NONE", "text_english": None, "evidence_quote": "We need support from finance"})
    record = approve_draft(draft, {**ai_values_as_typed(draft), "progress_percent": "58", "key_challenge": ""})

    files = list(sharepoint_dir.iterdir())
    list_item_path = next(f for f in files if not f.name.endswith("_audit.json"))
    audit_path = next(f for f in files if f.name.endswith("_audit.json"))

    list_item = json.loads(list_item_path.read_text())
    assert set(list_item) == {"quarter", "traffic_light", "progress_percent", "key_success", "key_challenge", "support_needed"}
    assert list_item["progress_percent"] == 58

    audit = json.loads(audit_path.read_text())
    assert audit["ai_values"]["progress_percent"] == 55
    assert audit["field_statuses"]["support_needed"] == "EXPLICITLY_NONE"
    assert audit["field_statuses"]["key_challenge"] == "LEFT_BLANK"

    assert record.sharepoint_path == str(list_item_path)


def test_flagged_value_must_be_confirmed_or_changed(sharepoint_dir):
    transcript = f"Overall status is yellow. {TRANSCRIPT}"
    draft = make_draft(transcript, traffic_light={"spoken_colour_word": "yellow", "evidence_quote": "Overall status is yellow"})
    with pytest.raises(ApprovalNotPermitted, match="traffic_light"):
        approve_draft(draft, ai_values_as_typed(draft))
    assert list(sharepoint_dir.iterdir()) == []
    assert approve_draft(draft, ai_values_as_typed(draft), confirmed_fields={"traffic_light"}).traffic_light == "Amber"
    assert approve_draft(draft, {**ai_values_as_typed(draft), "traffic_light": "Red"}).traffic_light == "Red"


def test_rejected_draft_cannot_be_approved(sharepoint_dir):
    with pytest.raises(ApprovalNotPermitted):
        approve_draft(create_draft("Um, hello?"), REVIEWED_VALUES)
