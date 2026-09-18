import math
import re
import unicodedata

from rapidfuzz import fuzz

from voice_capture.constants import (
    COLOUR_WORDS,
    FILLER_WORDS,
    GROUNDING_MIN_SCORE,
    NARRATIVE_MAX_CHARS,
    PROGRESS_MAX,
    PROGRESS_MIN,
    QUARTER_PATTERN,
    REQUIRED_FIELDS,
    SUGGESTED_COLOUR_WORDS,
)
from voice_capture.enums import FieldStatus, FlagCode, ReportedStatus, SchemaField
from voice_capture.schema import FieldResult, Flag


def decide_field(schema_field, report, transcript):
    not_stated = Flag(
        code=FlagCode.NOT_STATED, message=f"{schema_field.label} was not stated by the speaker.", blocking=schema_field in REQUIRED_FIELDS
    )
    result = FIELD_DECIDERS[schema_field](report) or FieldResult(status=FieldStatus.MISSING, flags=[not_stated])
    result.evidence_quote = report.evidence_quote
    if result.status == FieldStatus.EXTRACTED and report.self_corrected_from:
        message = f'The speaker corrected themselves; the earlier value was "{report.self_corrected_from}".'
        result.flags.append(Flag(code=FlagCode.SELF_CORRECTED, message=message))

    original_text = (getattr(report, "original_language_text", None) or "").strip()
    if original_text and result.status != FieldStatus.EXPLICITLY_NONE:
        result.original_text = original_text
        message = "Translated to English by the AI; verify it against the speaker's original words."
        result.flags.append(Flag(code=FlagCode.MACHINE_TRANSLATED, message=message))

    quote_should_be_grounded = result.status in (FieldStatus.EXTRACTED, FieldStatus.EXPLICITLY_NONE)
    if quote_should_be_grounded and not is_quote_in_transcript(report.evidence_quote, transcript):
        message = "The AI's supporting quote could not be found in the transcript. Check this field against the transcript."
        not_found = Flag(code=FlagCode.EVIDENCE_NOT_FOUND, message=message, blocking=True)
        candidates = [result.value] if result.value is not None else result.candidates
        result = result.model_copy(
            update={"status": FieldStatus.AMBIGUOUS, "value": None, "candidates": candidates, "flags": [*result.flags, not_found]}
        )

    return result


def is_quote_in_transcript(quote, transcript):
    normalised_quote, normalised_transcript = _normalise_text(quote), _normalise_text(transcript)
    transcript_without_fillers = " ".join(word for word in normalised_transcript.split() if word not in FILLER_WORDS)

    is_found = bool(normalised_quote and normalised_transcript) and (
        normalised_quote in normalised_transcript
        or normalised_quote in transcript_without_fillers
        or fuzz.partial_ratio(normalised_quote, normalised_transcript) >= GROUNDING_MIN_SCORE
    )

    return is_found


def _decide_quarter(report):
    spoken_quarter = _to_valid_quarter(f"Q{report.quarter_number} {report.year or ''}")

    if report.status == ReportedStatus.UNRESOLVED:
        result = _unresolved_result([quarter for quarter in map(_to_valid_quarter, report.candidates) if quarter])
    elif report.status != ReportedStatus.STATED or report.quarter_number is None:
        result = None
    elif spoken_quarter is None:
        invalid = Flag(code=FlagCode.INVALID_QUARTER, message=f'"{report.raw_phrase}" is not a valid quarter.', blocking=True)
        result = FieldResult(status=FieldStatus.AMBIGUOUS, flags=[invalid])
    else:
        no_year = Flag(code=FlagCode.YEAR_NOT_STATED, message="No year was stated; confirm the year before approval.")
        result = FieldResult(status=FieldStatus.EXTRACTED, value=spoken_quarter, flags=[] if report.year else [no_year])

    return result


def _to_valid_quarter(text):
    normalised = " ".join(str(text).upper().split())

    return normalised if re.fullmatch(QUARTER_PATTERN, normalised) else None


def _decide_traffic_light(report):
    colour_word = _normalise_text(report.spoken_colour_word)
    traffic_light = COLOUR_WORDS.get(colour_word)

    if report.status == ReportedStatus.UNRESOLVED:
        candidate_lights = (COLOUR_WORDS.get(_normalise_text(word)) for word in report.candidate_colour_words)
        result = _unresolved_result(list(dict.fromkeys(light for light in candidate_lights if light)))

    elif report.status != ReportedStatus.STATED or not report.spoken_colour_word:
        result = None

    elif traffic_light is None:
        message = f'"{report.spoken_colour_word}" is not one of Red, Amber, Green or Blue.'
        result = FieldResult(status=FieldStatus.AMBIGUOUS, flags=[Flag(code=FlagCode.VOCAB_UNMAPPABLE, message=message, blocking=True)])

    else:
        message = (
            f'The speaker said "{report.spoken_colour_word}", which is not in the controlled vocabulary. '
            f"{traffic_light} is only a suggestion; confirm or change it."
        )
        suggestion = Flag(code=FlagCode.VOCAB_NORMALISED, message=message, blocking=True)
        flags = [suggestion] if colour_word in SUGGESTED_COLOUR_WORDS else []
        result = FieldResult(status=FieldStatus.EXTRACTED, value=traffic_light, flags=flags)

    return result


def _decide_progress(report):
    number = report.spoken_number
    has_range = report.range_low is not None and report.range_high is not None

    if report.status == ReportedStatus.UNRESOLVED and has_range:
        bounds = [int(bound) if bound.is_integer() else bound for bound in (report.range_low, report.range_high)]
        uncommitted = Flag(code=FlagCode.RANGE_UNCOMMITTED, message="A range was given without committing to one number.", blocking=True)
        result = FieldResult(status=FieldStatus.AMBIGUOUS, candidates=bounds, flags=[uncommitted])

    elif report.status == ReportedStatus.UNRESOLVED:
        candidates = [int(value) if value.is_integer() else value for value in report.candidates]
        result = _unresolved_result(candidates)

    elif report.status != ReportedStatus.STATED:
        result = None

    elif number is None:
        no_number = Flag(code=FlagCode.NO_NUMERIC_VALUE, message="Progress was described without a number.", blocking=True)
        result = FieldResult(status=FieldStatus.MISSING, flags=[no_number])

    elif not PROGRESS_MIN <= number <= PROGRESS_MAX:
        message = f"{number:g} is outside {PROGRESS_MIN}-{PROGRESS_MAX}."
        result = FieldResult(status=FieldStatus.AMBIGUOUS, flags=[Flag(code=FlagCode.OUT_OF_RANGE, message=message, blocking=True)])

    elif not number.is_integer():
        message = f"{number:g} is not a whole number; choose the intended value."
        non_integer = Flag(code=FlagCode.NON_INTEGER, message=message, blocking=True)
        result = FieldResult(status=FieldStatus.AMBIGUOUS, candidates=[math.floor(number), math.ceil(number)], flags=[non_integer])

    else:
        qualifiers = (
            (report.is_approximate, FlagCode.APPROXIMATE, "The speaker described this figure as approximate."),
            (has_range, FlagCode.RANGE_GIVEN, "The speaker gave a range before committing to this figure."),
            (report.converted_from_words_or_fraction, FlagCode.CONVERTED_FROM_WORDS, f'Converted from "{report.raw_phrase}" to a percentage.'),
        )
        flags = [Flag(code=code, message=message) for applies, code, message in qualifiers if applies]
        result = FieldResult(status=FieldStatus.EXTRACTED, value=int(number), flags=flags)

    return result


def _decide_narrative(report):
    text = (report.text_english or "").strip()
    if report.status == ReportedStatus.UNRESOLVED:
        result = _unresolved_result([text] if text else [])
    elif report.status == ReportedStatus.EXPLICITLY_NONE:
        result = FieldResult(status=FieldStatus.EXPLICITLY_NONE)
    elif report.status != ReportedStatus.STATED or not text:
        result = None
    elif len(text) > NARRATIVE_MAX_CHARS:
        message = f"{len(text)} characters exceeds the {NARRATIVE_MAX_CHARS}-character limit; shorten it."
        too_long = Flag(code=FlagCode.TOO_LONG, message=message, blocking=True)
        result = FieldResult(status=FieldStatus.AMBIGUOUS, candidates=[text], flags=[too_long])
    else:
        result = FieldResult(status=FieldStatus.EXTRACTED, value=text)

    return result


FIELD_DECIDERS = {
    SchemaField.QUARTER: _decide_quarter,
    SchemaField.TRAFFIC_LIGHT: _decide_traffic_light,
    SchemaField.PROGRESS_PERCENT: _decide_progress,
    SchemaField.KEY_SUCCESS: _decide_narrative,
    SchemaField.KEY_CHALLENGE: _decide_narrative,
    SchemaField.SUPPORT_NEEDED: _decide_narrative,
}


def _normalise_text(text):
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))

    return " ".join(re.sub(r"[\W_]+", " ", without_accents.casefold()).split())


def _unresolved_result(candidates):
    conflict = Flag(code=FlagCode.UNRESOLVED_CONFLICT, message="The speaker did not settle on one value.", blocking=True)

    return FieldResult(status=FieldStatus.AMBIGUOUS, candidates=candidates, flags=[conflict])
