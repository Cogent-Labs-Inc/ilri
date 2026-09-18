import json
import uuid

from datetime import datetime, timezone

from voice_capture import config
from voice_capture.enums import FieldStatus, SchemaField, Verdict
from voice_capture.exceptions import ApprovalNotPermitted
from voice_capture.schema import ApprovedRecord, QuarterlyUpdate


def approve_draft(draft, reviewed_values, confirmed_fields=()):
    """The only path to the system of record. Raises ValueError (incl. pydantic ValidationError) on any problem."""
    if draft.verdict == Verdict.REJECTED:
        raise ApprovalNotPermitted("A rejected input cannot be approved; submit a new update.")

    quarterly_update = QuarterlyUpdate.model_validate(reviewed_values)
    unconfirmed_fields = [
        schema_field
        for schema_field, ai_result in draft.fields.items()
        if ai_result.is_blocked and getattr(quarterly_update, schema_field) == ai_result.value and schema_field not in confirmed_fields
    ]
    if unconfirmed_fields:
        raise ApprovalNotPermitted(f"Flagged values must be confirmed or changed: {', '.join(unconfirmed_fields)}.")

    record = ApprovedRecord(
        **quarterly_update.model_dump(),
        field_statuses={
            schema_field: final_field_status(getattr(quarterly_update, schema_field), draft.fields[schema_field].status)
            for schema_field in SchemaField
        },
        ai_values={schema_field: draft.fields[schema_field].value for schema_field in SchemaField},
        approved_at=datetime.now(timezone.utc),
    )
    record.sharepoint_path = write_to_sharepoint(record)

    return record


def final_field_status(approved_value, ai_status):
    if approved_value is not None:
        status = "PROVIDED"
    elif ai_status == FieldStatus.EXPLICITLY_NONE:
        status = "EXPLICITLY_NONE"
    else:
        status = "LEFT_BLANK"

    return status


def write_to_sharepoint(record):
    """The list-item write holds only the six schema fields, matching what a real SharePoint list
    write would contain. ai_values/field_statuses/approved_at are audit metadata, not list columns -
    they go in a separate companion record instead of extra fields on the item."""
    config.MOCK_SHAREPOINT_DIR.mkdir(parents=True, exist_ok=True)
    item_id = uuid.uuid4().hex[:12]

    list_item_path = config.MOCK_SHAREPOINT_DIR / f"quarterly_update_{item_id}.json"
    list_item = QuarterlyUpdate(**record.model_dump()).model_dump(mode="json")
    list_item_path.write_text(json.dumps(list_item, indent=2, ensure_ascii=False), encoding="utf-8")

    audit_path = config.MOCK_SHAREPOINT_DIR / f"quarterly_update_{item_id}_audit.json"
    audit_record = record.model_dump(mode="json", include={"ai_values", "field_statuses", "approved_at"})
    audit_record["quarterly_update_id"] = item_id
    audit_path.write_text(json.dumps(audit_record, indent=2, ensure_ascii=False), encoding="utf-8")

    return str(list_item_path)
