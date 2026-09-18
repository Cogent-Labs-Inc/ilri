import pytest

from conftest import TRANSCRIPT, make_draft

from voice_capture.enums import FieldStatus, FlagCode, Verdict
from voice_capture.field_decisions import is_quote_in_transcript


def test_clean_report_is_ready_for_review_with_every_value():
    draft = make_draft()
    assert draft.verdict == Verdict.READY_FOR_REVIEW
    assert {field: result.value for field, result in draft.fields.items()} == {
        "quarter": "Q2 2026",
        "traffic_light": "Green",
        "progress_percent": 55,
        "key_success": "Launched the regional training programme.",
        "key_challenge": "Late delivery of field equipment.",
        "support_needed": "Finance to release the second budget tranche.",
    }


def test_year_is_never_added_and_a_missing_year_is_only_a_warning():
    transcript = f"This is the update for quarter two. {TRANSCRIPT}"
    draft = make_draft(transcript, quarter={"year": None, "evidence_quote": "update for quarter two"})
    assert (draft.fields["quarter"].value, draft.fields["quarter"].flag_codes) == ("Q2", {FlagCode.YEAR_NOT_STATED})
    assert draft.verdict == Verdict.READY_FOR_REVIEW


def test_invalid_quarter_is_ambiguous():
    result = make_draft(quarter={"quarter_number": 5}).fields["quarter"]
    assert (result.status, result.value, result.flag_codes) == (FieldStatus.AMBIGUOUS, None, {FlagCode.INVALID_QUARTER})


def test_unresolved_quarter_keeps_only_valid_candidates():
    result = make_draft(quarter={"status": "UNRESOLVED", "quarter_number": None, "candidates": ["q1", "Q2 2026", "Q7"]}).fields["quarter"]
    assert (result.status, result.candidates, result.flag_codes) == (FieldStatus.AMBIGUOUS, ["Q1", "Q2 2026"], {FlagCode.UNRESOLVED_CONFLICT})


@pytest.mark.parametrize(
    "spoken_word, traffic_light, flag_codes",
    [
        ("red", "Red", set()),
        ("amber", "Amber", set()),
        ("green", "Green", set()),
        ("blue", "Blue", set()),
        ("VERT", "Green", set()),
        ("Ámbar", "Amber", set()),
        ("ambar", "Amber", set()),
        ("kijani", "Green", set()),
        ("yellow", "Amber", {FlagCode.VOCAB_NORMALISED}),
        ("njano", "Amber", {FlagCode.VOCAB_NORMALISED}),
        ("on track", None, {FlagCode.VOCAB_UNMAPPABLE}),
        # Every remaining word in COLOUR_WORDS (voice_capture/constants.py), across all four covered
        # languages (English, French, Spanish, Swahili) - not just the subset exercised above.
        ("rouge", "Red", set()),
        ("rojo", "Red", set()),
        ("nyekundu", "Red", set()),
        ("ambre", "Amber", set()),
        ("verde", "Green", set()),
        ("bleu", "Blue", set()),
        ("azul", "Blue", set()),
        ("bluu", "Blue", set()),
        ("orange", "Amber", {FlagCode.VOCAB_NORMALISED}),
        ("jaune", "Amber", {FlagCode.VOCAB_NORMALISED}),
        ("amarillo", "Amber", {FlagCode.VOCAB_NORMALISED}),
        ("naranja", "Amber", {FlagCode.VOCAB_NORMALISED}),
    ],
)
def test_traffic_light_vocabulary(spoken_word, traffic_light, flag_codes):
    transcript = f"Overall status is {spoken_word}. {TRANSCRIPT}"
    report = {"spoken_colour_word": spoken_word, "evidence_quote": f"Overall status is {spoken_word}"}
    result = make_draft(transcript, traffic_light=report).fields["traffic_light"]
    assert (result.value, result.flag_codes) == (traffic_light, flag_codes)


@pytest.mark.parametrize(
    "progress_report, status, candidates, flag_code",
    [
        ({"spoken_number": 65.5}, FieldStatus.AMBIGUOUS, [65, 66], FlagCode.NON_INTEGER),
        ({"spoken_number": 120.0}, FieldStatus.AMBIGUOUS, [], FlagCode.OUT_OF_RANGE),
        ({"spoken_number": None}, FieldStatus.MISSING, [], FlagCode.NO_NUMERIC_VALUE),
        (
            {"status": "UNRESOLVED", "spoken_number": None, "range_low": 40.0, "range_high": 50.0},
            FieldStatus.AMBIGUOUS,
            [40, 50],
            FlagCode.RANGE_UNCOMMITTED,
        ),
        (
            {"status": "UNRESOLVED", "spoken_number": None, "candidates": [70.0, 72.0]},
            FieldStatus.AMBIGUOUS,
            [70, 72],
            FlagCode.UNRESOLVED_CONFLICT,
        ),
    ],
)
def test_progress_never_guesses_a_number(progress_report, status, candidates, flag_code):
    result = make_draft(progress_percent=progress_report).fields["progress_percent"]
    assert (result.status, result.value, result.candidates) == (status, None, candidates)
    assert flag_code in result.flag_codes


def test_progress_qualifiers_are_warnings_only():
    qualifiers = {"is_approximate": True, "range_low": 50.0, "range_high": 60.0, "converted_from_words_or_fraction": True}
    result = make_draft(progress_percent=qualifiers).fields["progress_percent"]
    assert (result.value, result.flag_codes) == (55, {FlagCode.APPROXIMATE, FlagCode.RANGE_GIVEN, FlagCode.CONVERTED_FROM_WORDS})
    assert not result.is_blocked


def test_narrative_over_the_character_limit_is_ambiguous():
    result = make_draft(key_success={"text_english": "x" * 201}).fields["key_success"]
    assert (result.status, result.flag_codes) == (FieldStatus.AMBIGUOUS, {FlagCode.TOO_LONG})


def test_explicitly_none_narrative_does_not_need_attention():
    draft = make_draft(support_needed={"status": "EXPLICITLY_NONE", "text_english": None, "evidence_quote": "We need support from finance"})
    assert (draft.fields["support_needed"].status, draft.verdict) == (FieldStatus.EXPLICITLY_NONE, Verdict.READY_FOR_REVIEW)


def test_translated_narrative_keeps_the_original_words_and_is_flagged():
    result = make_draft(key_success={"original_language_text": "lancement du programme"}).fields["key_success"]
    assert result.original_text == "lancement du programme"
    assert FlagCode.MACHINE_TRANSLATED in result.flag_codes


def test_not_stated_blocks_required_fields_but_only_warns_for_narratives():
    draft = make_draft(
        traffic_light={"status": "NOT_MENTIONED", "spoken_colour_word": None, "evidence_quote": None},
        key_challenge={"status": "NOT_MENTIONED", "text_english": None, "evidence_quote": None},
    )
    assert draft.fields["traffic_light"].status == draft.fields["key_challenge"].status == FieldStatus.MISSING
    assert (draft.fields["traffic_light"].is_blocked, draft.fields["key_challenge"].is_blocked) == (True, False)
    assert draft.verdict == Verdict.NEEDS_ATTENTION


def test_self_correction_is_flagged():
    assert FlagCode.SELF_CORRECTED in make_draft(quarter={"self_corrected_from": "Q3"}).fields["quarter"].flag_codes


# --- evidence grounding ---------------------------------------------------------------------------------

RAMBLING_TRANSCRIPT = (
    "So, um, yeah - okay so the biggest headache this quarter, honestly, was the vehicle fleet issue, we had two of "
    "our four survey vehicles down for almost a month. Anyway, um, we still managed to sign the co-funding agreement "
    "with the regional livestock policy platform."
)


@pytest.mark.parametrize(
    "quote, is_grounded",
    [
        ("the biggest headache this quarter, honestly, was the vehicle fleet issue", True),
        ("we still managed to sign the co funding agreement", True),
        ("we secured a new grant from the ministry", False),
        ("the vehicle fleet issue was fully resolved within the week", False),
        ("the main challenge was the vehicle fleet issue with two vehicles down", False),
        (None, False),
    ],
)
def test_quote_must_really_appear_in_the_transcript(quote, is_grounded):
    assert is_quote_in_transcript(quote, RAMBLING_TRANSCRIPT) is is_grounded


def test_filler_words_dropped_by_the_model_still_ground():
    assert is_quote_in_transcript("we are sitting at about sixty percent", "we are, um, sitting at, uh, about sixty percent right now")


def test_ungrounded_value_becomes_a_candidate_not_a_value():
    result = make_draft(quarter={"evidence_quote": "report for the fourth quarter of 2031"}).fields["quarter"]
    assert (result.status, result.value, result.candidates) == (FieldStatus.AMBIGUOUS, None, ["Q2 2026"])
    assert FlagCode.EVIDENCE_NOT_FOUND in result.flag_codes
