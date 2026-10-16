"""Test data entry with validation against the approved field definitions.

Validation runs here AND in the browser, on purpose. The browser check is
for immediate feedback; this one is the guarantee. Both read the same
approved field definition, so there is one source of truth.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.schema import DraftECRF, FieldDef
from ecrf.stats import seed as seed_mod
from ecrf.storage import db
from ecrf.storage.models import Observation, Protocol

router = APIRouter(prefix="/api/data", tags=["data"])


class Reading(BaseModel):
    field_name: str
    repeat_num: int = 1
    value: str | float | int | bool | None


class EntryRequest(BaseModel):
    protocol_id: int
    subject_id: str
    visit: str
    readings: list[Reading]


def _approved_fields(s: Session, protocol_id: int, visit: str) -> dict[str, FieldDef]:
    v = db.latest_version(s, protocol_id)
    if not v:
        raise HTTPException(404, "no eCRF version for this protocol")
    draft = DraftECRF.model_validate(v.content)
    for form in draft.forms:
        if form.visit == visit:
            return {f.name: f for f in form.fields if f.status in ("approved", "draft")}
    raise HTTPException(404, f"visit '{visit}' not in eCRF")


def validate(field: FieldDef, value) -> str | None:
    """Return an error message, or None if valid."""
    if value is None or value == "":
        return "required" if field.required else None
    if field.type in ("integer", "decimal"):
        try:
            x = float(value)
        except (TypeError, ValueError):
            return "must be a number"
        if field.type == "integer" and x != int(x):
            return "must be a whole number"
        if field.min is not None and x < field.min:
            return f"below minimum {field.min}"
        if field.max is not None and x > field.max:
            return f"above maximum {field.max}"
    if field.type == "choice" and field.choices and str(value) not in field.choices:
        return f"must be one of: {', '.join(field.choices)}"
    if field.type == "boolean" and str(value).lower() not in ("true", "false", "yes", "no", "1", "0"):
        return "must be yes or no"
    return None


@router.post("/validate")
def validate_only(body: EntryRequest, s: Session = Depends(db.get_session)):
    fields = _approved_fields(s, body.protocol_id, body.visit)
    errors = {}
    for r in body.readings:
        f = fields.get(r.field_name)
        if not f:
            errors[f"{r.field_name}#{r.repeat_num}"] = "unknown field for this visit"
            continue
        err = validate(f, r.value)
        if err:
            errors[f"{r.field_name}#{r.repeat_num}"] = err
    return {"ok": not errors, "errors": errors}


@router.post("/enter")
def enter(body: EntryRequest, x_user: str | None = Header(None),
          s: Session = Depends(db.get_session)):
    check = validate_only(body, s)
    if not check["ok"]:
        raise HTTPException(422, {"errors": check["errors"]})
    fields = _approved_fields(s, body.protocol_id, body.visit)
    saved = 0
    for r in body.readings:
        f = fields[r.field_name]
        num = float(r.value) if f.type in ("integer", "decimal") and r.value not in (None, "") else None
        text = None if num is not None else (str(r.value) if r.value not in (None, "") else None)
        # upsert by unique key
        existing = s.scalars(select(Observation).where(
            Observation.protocol_id == body.protocol_id, Observation.subject_id == body.subject_id,
            Observation.visit == body.visit, Observation.field_name == r.field_name,
            Observation.repeat_num == r.repeat_num)).first()
        if existing:
            existing.value_num, existing.value_text = num, text
        else:
            s.add(Observation(protocol_id=body.protocol_id, subject_id=body.subject_id,
                              visit=body.visit, field_name=r.field_name, repeat_num=r.repeat_num,
                              value_num=num, value_text=text, synthetic=True,
                              entered_by=x_user or "demo-user"))
        saved += 1
    s.commit()
    return {"saved": saved}


@router.post("/seed/{protocol_id}")
def seed(protocol_id: int, s: Session = Depends(db.get_session)):
    """Load synthetic observations for the dashboard demo."""
    if not s.get(Protocol, protocol_id):
        raise HTTPException(404, "protocol not found")
    existing = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id)).first()
    if existing:
        return {"seeded": 0, "already": True}
    n = seed_mod.seed(s, protocol_id)
    s.commit()
    return {"seeded": n, "already": False}


@router.get("/{protocol_id}/subjects")
def subjects(protocol_id: int, s: Session = Depends(db.get_session)):
    rows = s.execute(
        select(Observation.subject_id, Observation.visit)
        .where(Observation.protocol_id == protocol_id).distinct()
    ).all()
    out: dict[str, list[str]] = {}
    for subj, visit in rows:
        out.setdefault(subj, []).append(visit)
    return [{"subject_id": k, "visits": v} for k, v in sorted(out.items())]
