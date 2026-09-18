"""
Throwaway demo UI. Vibe-coded, not reviewed.

This file exists only to click through the pipeline (submit -> review -> approve) during the
exercise. The reviewed, tested logic lives in voice_capture/. Nothing here persists past the
browser session (drafts live in st.session_state, in memory only).

tests/test_streamlit_app.py has two offline smoke tests (renders, and the happy path end to
end) so a broken import or a crash on the basic flow is caught - not full UI coverage, which is
out of scope for a throwaway demo in a 4-hour exercise.
"""

import streamlit as st

from pydantic import ValidationError

from voice_capture.approval import approve_draft
from voice_capture.constants import ALLOWED_AUDIO_FORMATS
from voice_capture.enums import SchemaField, Verdict
from voice_capture.drafting import create_draft
from voice_capture.exceptions import CaptureConfigurationError


def submit_tab():
    mode = st.radio("Input", ["Transcript text", "Audio recording"], horizontal=True)
    if mode == "Transcript text":
        text = st.text_area("Transcript", height=250, placeholder="Paste the transcript of the spoken update.")
        request = {"transcript": text} if st.button("Create draft", type="primary") else None
    else:
        audio = st.file_uploader(f"Audio recording ({', '.join(sorted(ALLOWED_AUDIO_FORMATS))}, up to 25 MB)")
        clicked = st.button("Create draft", type="primary", disabled=audio is None)
        request = {"audio": audio.getvalue(), "audio_filename": audio.name} if clicked and audio else None

    if request:
        with st.spinner("Transcribing and extracting..."):
            try:
                draft = create_draft(**request)
            except CaptureConfigurationError as exc:
                st.error(str(exc))
                return
        st.session_state.entries.append({"draft": draft, "state": "open", "record": None})
        if draft.verdict == Verdict.REJECTED:
            st.warning(draft.rejection_message)
        else:
            st.success(f"Draft #{len(st.session_state.entries)} created: {draft.verdict}. Review it in the next tab.")


def show_flag(flag):
    (st.error if flag.blocking else st.warning)(f"{flag.code}: {flag.message}")


def review_tab():
    open_entries = {f"#{i + 1} {e['draft'].verdict}": e for i, e in enumerate(st.session_state.entries) if e["state"] == "open"}
    if not open_entries:
        st.info("No open drafts. Submit an update first.")
        return
    entry = open_entries[st.selectbox("Open draft", list(open_entries))]
    draft = entry["draft"]
    with st.expander("Transcript"):
        st.text(draft.transcript)

    if draft.verdict == Verdict.REJECTED:
        st.warning(draft.rejection_message)
    else:
        for flag in draft.flags:
            show_flag(flag)
        reviewed_values, confirmed_fields = {}, set()
        for schema_field in SchemaField:
            result = draft.fields[schema_field]
            st.markdown(f"**{schema_field.label}** · `{result.status}`")
            for flag in result.flags:
                show_flag(flag)
            if result.candidates:
                st.caption(f"Candidates: {result.candidates}")
            default = "" if result.value is None else str(result.value)
            reviewed_values[schema_field] = st.text_input(schema_field.label, default, key=f"{id(draft)}{schema_field}")
            if result.is_blocked and st.checkbox("Confirm despite the flag", key=f"{id(draft)}{schema_field}confirm"):
                confirmed_fields.add(schema_field)

        if st.button("Approve", type="primary"):
            try:
                entry["record"] = approve_draft(draft, reviewed_values, confirmed_fields)
            except ValidationError as exc:
                for error in exc.errors():
                    st.error(f"{error['loc'][0]}: {error['msg']}")
            except ValueError as exc:
                st.error(str(exc))
            else:
                entry["state"] = "approved"
                st.rerun()

    if st.button("Discard"):
        entry["state"] = "discarded"
        st.rerun()


def approved_tab():
    records = [entry["record"] for entry in st.session_state.entries if entry["state"] == "approved"]
    if not records:
        st.info("No approved records yet.")
    for record in records:
        st.json(record.model_dump(mode="json"))


st.set_page_config(page_title="Voice Capture")
st.title("Quarterly update: voice capture")
st.session_state.setdefault("entries", [])
submit, review, approved = st.tabs(["Submit", "Review drafts", "Approved"])
with submit:
    submit_tab()
with review:
    review_tab()
with approved:
    approved_tab()
