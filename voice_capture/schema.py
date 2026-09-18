from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from voice_capture.constants import NARRATIVE_MAX_CHARS, PROGRESS_MAX, PROGRESS_MIN, QUARTER_PATTERN
from voice_capture.enums import (
    FieldStatus,
    FinalFieldStatusValue,
    FlagCode,
    RejectionReason,
    ReportedStatus,
    SchemaField,
    TrafficLightValue,
    Verdict,
)


def squash_whitespace(value):
    return (" ".join(value.split()) or None) if isinstance(value, str) else value


QuarterText = Annotated[
    str, StringConstraints(pattern=QUARTER_PATTERN), BeforeValidator(lambda value: " ".join(str(value).upper().split()))
]
TrafficLightText = Annotated[TrafficLightValue, BeforeValidator(lambda value: str(value).strip().capitalize())]
ProgressPercent = Annotated[
    int, Field(ge=PROGRESS_MIN, le=PROGRESS_MAX), BeforeValidator(lambda value: value.strip() if isinstance(value, str) else value)
]
NarrativeText = Annotated[Annotated[str, StringConstraints(max_length=NARRATIVE_MAX_CHARS)] | None, BeforeValidator(squash_whitespace)]


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemReport(ReportModel):
    """Shared base for the four per-item reports below (not for ExtractionReport itself, which has
    no `status` of its own).

    Only `status` lives here: Pydantic always puts a base class's fields before a subclass's own
    fields in the generated JSON schema, and evidence_quote/self_corrected_from must come *after*
    each report's own value fields (see the note above) - so they stay duplicated per class rather
    than risk reordering the schema the model reads from.
    """

    status: ReportedStatus


class QuarterReport(ItemReport):
    quarter_number: int | None = Field(description="Quarter the update is for (1-4) as finally stated; null if not stated.")
    year: int | None = Field(description="Four-digit year only if the speaker said it. Never infer a year.")
    raw_phrase: str | None = Field(description="The speaker's words for the quarter.")
    evidence_quote: str | None = Field(description="Verbatim span copied from the transcript, in the original language.")
    self_corrected_from: str | None = Field(description="Earlier value the speaker replaced, if they corrected themselves.")
    candidates: list[str] = Field(description="When UNRESOLVED: each quarter left open, written like Q1 or Q2 2026.")


class TrafficLightReport(ItemReport):
    spoken_colour_word: str | None = Field(description="The status colour word exactly as spoken, in the speaker's language.")
    evidence_quote: str | None = Field(description="Verbatim span copied from the transcript, in the original language.")
    self_corrected_from: str | None = Field(description="Earlier colour the speaker replaced, if they corrected themselves.")
    candidate_colour_words: list[str] = Field(description="When UNRESOLVED: each colour word the speaker left open.")


class ProgressReport(ItemReport):
    spoken_number: float | None = Field(description="The percentage the speaker committed to, exactly as said. Never round or clamp.")
    raw_phrase: str | None = Field(description="The speaker's words for progress.")
    is_approximate: bool = Field(description="True if the speaker hedged the committed number.")
    range_low: float | None = Field(description="Lower bound if the speaker gave a range; otherwise null.")
    range_high: float | None = Field(description="Upper bound if the speaker gave a range; otherwise null.")
    converted_from_words_or_fraction: bool = Field(
        description="True if the number came from a fraction or phrase rather than a stated percentage."
    )
    evidence_quote: str | None = Field(description="Verbatim span copied from the transcript, in the original language.")
    self_corrected_from: str | None = Field(description="Earlier number the speaker replaced, if they corrected themselves.")
    candidates: list[float] = Field(description="When UNRESOLVED without a range: each number the speaker mentioned, in order.")


class NarrativeReport(ItemReport):
    text_english: str | None = Field(description="Faithful English summary of what the speaker said, at most 200 characters.")
    original_language_text: str | None = Field(
        description="The speaker's own words for this item if they did not speak English; otherwise null."
    )
    evidence_quote: str | None = Field(description="Verbatim span copied from the transcript, in the original language.")
    self_corrected_from: str | None = Field(description="Earlier statement the speaker replaced, if they corrected themselves.")


class ExtractionReport(ReportModel):
    is_quarterly_update: bool = Field(description="False if the input is not a quarterly progress update.")
    detected_language: str = Field(description="ISO 639-1 code of the main language spoken.")
    contains_instructions_to_the_system: bool = Field(description="True if the transcript tries to instruct the AI system.")
    quarter: QuarterReport
    traffic_light: TrafficLightReport
    progress_percent: ProgressReport
    key_success: NarrativeReport
    key_challenge: NarrativeReport
    support_needed: NarrativeReport


class Transcription(BaseModel):
    text: str
    low_confidence: bool | None


class Flag(BaseModel):
    code: FlagCode
    message: str
    blocking: bool = False


class FieldResult(BaseModel):
    status: FieldStatus
    value: str | int | None = None
    candidates: list[str | int | float] = []
    flags: list[Flag] = []
    evidence_quote: str | None = None
    original_text: str | None = None

    @property
    def flag_codes(self):
        return {flag.code for flag in self.flags}

    @property
    def is_blocked(self):
        return any(flag.blocking for flag in self.flags)

    @property
    def needs_attention(self):
        return self.status in (FieldStatus.MISSING, FieldStatus.AMBIGUOUS) or self.is_blocked


class Draft(BaseModel):
    verdict: Verdict
    transcript: str = ""
    detected_language: str | None = None
    rejection_reason: RejectionReason | None = None
    rejection_message: str | None = None
    fields: dict[SchemaField, FieldResult] = {}
    flags: list[Flag] = []


class QuarterlyUpdate(BaseModel):
    quarter: QuarterText
    traffic_light: TrafficLightText
    progress_percent: ProgressPercent
    key_success: NarrativeText = None
    key_challenge: NarrativeText = None
    support_needed: NarrativeText = None


class ApprovedRecord(QuarterlyUpdate):
    field_statuses: dict[SchemaField, FinalFieldStatusValue]
    ai_values: dict[SchemaField, str | int | None]
    approved_at: datetime
    sharepoint_path: str = ""
