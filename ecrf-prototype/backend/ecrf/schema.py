"""The output contract.

One definition. It produces the JSON schema sent to the model AND the
validation the API applies, so the two cannot drift apart.
"""

from typing import Literal

from pydantic import BaseModel, Field

FieldType = Literal["integer", "decimal", "text", "date", "choice", "boolean"]
Issue = Literal["none", "missing", "conflicting", "ambiguous", "unsupported"]
Status = Literal["draft", "approved", "flagged", "rejected"]
Verdict = Literal["exact", "approximate", "rejected", "unchecked"]


class Source(BaseModel):
    """Where a generated field came from. Verified in stage 3."""

    section: str = Field(description="Protocol section number, e.g. '7.3.2'")
    quote: str = Field(
        min_length=20,
        description=(
            "Verbatim fragment from the protocol, at least 20 characters. "
            "It will be searched for in the protocol text; if not found the "
            "field is discarded."
        ),
    )


class FieldDef(BaseModel):
    """One box on one form."""

    name: str
    type: FieldType
    required: bool = True
    unit: str | None = None
    repeats: int = 1
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    source: Source
    issue: Issue = "none"
    issue_note: str | None = None

    # Filled by the pipeline, never by the model.
    status: Status = "draft"
    verdict: Verdict = "unchecked"
    match_score: float | None = None
    section_ok: bool | None = None
    cdash: str | None = None
    domain: str | None = None


class VisitForm(BaseModel):
    visit: str
    form: str = "Assessments"
    fields: list[FieldDef]


class VisitList(BaseModel):
    """Output of extraction pass one."""

    visits: list[str]


class Rejection(BaseModel):
    visit: str
    name: str
    quote: str
    section: str
    score: float
    reason: str


class DraftECRF(BaseModel):
    protocol_id: int
    protocol_hash: str
    version: int = 1
    backend: str
    model: str
    forms: list[VisitForm]
    rejections: list[Rejection] = []
    summary: dict = {}


# Schemas handed to the model. Only the model-facing fields.
def model_field_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "visit": {"type": "string"},
            "form": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string",
                                 "enum": list(FieldType.__args__)},
                        "required": {"type": "boolean"},
                        "unit": {"type": ["string", "null"]},
                        "repeats": {"type": "integer"},
                        "choices": {"type": ["array", "null"],
                                    "items": {"type": "string"}},
                        "min": {"type": ["number", "null"]},
                        "max": {"type": ["number", "null"]},
                        "source": {
                            "type": "object",
                            "properties": {
                                "section": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["section", "quote"],
                        },
                        "issue": {"type": "string",
                                  "enum": list(Issue.__args__)},
                        "issue_note": {"type": ["string", "null"]},
                    },
                    "required": ["name", "type", "required", "source", "issue"],
                },
            },
        },
        "required": ["visit", "fields"],
    }


def model_visits_schema() -> dict:
    return {
        "type": "object",
        "properties": {"visits": {"type": "array", "items": {"type": "string"}}},
        "required": ["visits"],
    }
