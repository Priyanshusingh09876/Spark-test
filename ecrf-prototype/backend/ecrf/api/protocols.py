"""Protocol upload, extraction, draft review, approval."""

import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import cdash, ingest, pipeline
from ecrf.config import config
from ecrf.schema import DraftECRF, Status
from ecrf.storage import db
from ecrf.storage.models import ECRFVersion, Protocol

router = APIRouter(prefix="/api/protocols", tags=["protocols"])

UPLOAD_DIR = config.data_dir / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _user(x_user: str | None) -> str:
    """Stand-in for Phoenix auth. The architecture draft notes the backend
    must know who uploaded, edited or approved. For the prototype the
    frontend sends an X-User header."""
    return x_user or "demo-user"


def _doc_from_protocol(p: Protocol) -> ingest.Document:
    """Rebuild a Document from stored text + sections, no re-parse.

    Each section's body is sliced back out of the stored normalised text
    using the offsets recorded at upload. Leaving it empty (as an earlier
    version did) silently breaks ECRF_CONTEXT=sections: section selection
    scores sections by their body, so with empty bodies it either picks a
    section on its title alone and sends the model a heading with no
    content, or finds nothing and falls back to the whole document. Both
    look like success from outside.
    """
    doc = ingest.Document(text=p.normalised, pages=p.pages, hash=p.text_hash,
                          tokens_estimate=p.tokens_estimate)
    doc.sections = [ingest.Section(s["number"], s["title"], s["page"],
                                   p.normalised[s["start"]:s["end"]],
                                   s["start"], s["end"]) for s in p.sections]
    return doc


# ----------------------------------------------------------------- list

@router.get("")
def list_protocols(s: Session = Depends(db.get_session)):
    rows = s.scalars(select(Protocol).order_by(Protocol.uploaded_at.desc())).all()
    out = []
    for p in rows:
        v = db.latest_version(s, p.id)
        out.append({
            "id": p.id, "name": p.name, "filename": p.filename, "pages": p.pages,
            "tokens_estimate": p.tokens_estimate, "uploaded_by": p.uploaded_by,
            "uploaded_at": p.uploaded_at.isoformat(),
            "latest_version": v.version if v else None,
            "summary": (v.content.get("summary") if v else None),
        })
    return out


# --------------------------------------------------------------- upload

@router.post("/upload")
async def upload(file: UploadFile = File(...), x_user: str | None = Header(None),
                 s: Session = Depends(db.get_session)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF protocols are supported in the prototype")
    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        doc = ingest.load(str(dest))
    except ingest.ScannedPDFError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e))

    name = Path(file.filename).stem.replace("_", " ")
    p = Protocol(
        name=name, filename=file.filename, text_hash=doc.hash, normalised=doc.text,
        sections=[{"number": x.number, "title": x.title, "page": x.page_start,
                   "start": x.start, "end": x.end} for x in doc.sections],
        pages=doc.pages, tokens_estimate=doc.tokens_estimate, uploaded_by=_user(x_user),
    )
    s.add(p)
    s.commit()
    return {"id": p.id, "name": p.name, "pages": p.pages,
            "tokens_estimate": p.tokens_estimate, "sections": len(doc.sections),
            "tables": len(doc.tables)}


@router.post("/sample")
def load_sample(x_user: str | None = Header(None), s: Session = Depends(db.get_session)):
    """Load the bundled synthetic protocol without a file picker."""
    src = config.data_dir / "sample" / "PHX-401-201_protocol.pdf"
    if not src.exists():
        raise HTTPException(500, "sample protocol missing; run data/sample/make_sample_protocol.py")
    existing = s.scalars(select(Protocol).where(Protocol.filename == src.name)).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "already_loaded": True}
    doc = ingest.load(str(src))
    p = Protocol(
        name="PHX-401-201 (synthetic sample)", filename=src.name, text_hash=doc.hash,
        normalised=doc.text,
        sections=[{"number": x.number, "title": x.title, "page": x.page_start,
                   "start": x.start, "end": x.end} for x in doc.sections],
        pages=doc.pages, tokens_estimate=doc.tokens_estimate, uploaded_by=_user(x_user),
    )
    s.add(p)
    s.commit()
    return {"id": p.id, "name": p.name, "already_loaded": False}


# ------------------------------------------------------------- extract

@router.post("/{protocol_id}/extract")
def extract(protocol_id: int, backend: str | None = None,
            x_user: str | None = Header(None), s: Session = Depends(db.get_session)):
    p = s.get(Protocol, protocol_id)
    if not p:
        raise HTTPException(404, "protocol not found")
    doc = _doc_from_protocol(p)
    pdf_path = UPLOAD_DIR / p.filename
    if not pdf_path.exists():
        pdf_path = config.data_dir / "sample" / p.filename
    try:
        draft = pipeline.run(str(pdf_path), protocol_id, backend=backend, doc=doc, log=lambda *_: None)
    except Exception as e:  # surface provider errors plainly
        raise HTTPException(502, f"extraction failed: {type(e).__name__}: {e}")
    v = db.save_version(s, p, draft.model_dump(), _user(x_user), note="initial extraction")
    s.commit()
    return {"version": v.version, "summary": draft.summary}


# --------------------------------------------------------------- draft

@router.get("/{protocol_id}/draft")
def get_draft(protocol_id: int, s: Session = Depends(db.get_session)):
    p = s.get(Protocol, protocol_id)
    if not p:
        raise HTTPException(404, "protocol not found")
    v = db.latest_version(s, protocol_id)
    if not v:
        return {"protocol": {"id": p.id, "name": p.name}, "version": None, "draft": None}
    draft = DraftECRF.model_validate(v.content)
    sugg = {f.visit: cdash.suggestions(f) for f in draft.forms}
    return {
        "protocol": {"id": p.id, "name": p.name, "pages": p.pages,
                     "tokens_estimate": p.tokens_estimate, "hash": p.text_hash[:12]},
        "version": v.version, "created_by": v.created_by, "created_at": v.created_at.isoformat(),
        "note": v.note, "draft": draft.model_dump(), "library_suggestions": sugg,
    }


@router.get("/{protocol_id}/versions")
def versions(protocol_id: int, s: Session = Depends(db.get_session)):
    rows = s.scalars(select(ECRFVersion).where(ECRFVersion.protocol_id == protocol_id)
                     .order_by(ECRFVersion.version)).all()
    return [{"version": r.version, "created_by": r.created_by,
             "created_at": r.created_at.isoformat(), "note": r.note,
             "summary": r.content.get("summary")} for r in rows]


@router.get("/{protocol_id}/section/{number}")
def section_text(protocol_id: int, number: str, s: Session = Depends(db.get_session)):
    """Lets the reviewer read the cited section without opening the PDF."""
    p = s.get(Protocol, protocol_id)
    if not p:
        raise HTTPException(404, "protocol not found")
    for sec in p.sections:
        if sec["number"] == number:
            return {"number": number, "title": sec["title"], "page": sec["page"],
                    "text": p.normalised[sec["start"]:sec["end"]]}
    raise HTTPException(404, "section not found")


# ------------------------------------------------------------- approve

class FieldChange(BaseModel):
    visit: str
    name: str
    status: Status | None = None
    min: float | None = None
    max: float | None = None
    required: bool | None = None
    repeats: int | None = None
    reviewer_note: str | None = None


class ReviewRequest(BaseModel):
    changes: list[FieldChange]
    note: str | None = None
    action: Literal["save", "approve_all_remaining"] = "save"


@router.post("/{protocol_id}/review")
def review(protocol_id: int, body: ReviewRequest, x_user: str | None = Header(None),
           s: Session = Depends(db.get_session)):
    """Apply reviewer edits and write a NEW version. Never updates in place."""
    p = s.get(Protocol, protocol_id)
    v = db.latest_version(s, protocol_id)
    if not p or not v:
        raise HTTPException(404, "no draft to review")
    draft = DraftECRF.model_validate(v.content)

    by_key = {(f.visit, fld.name): fld for f in draft.forms for fld in f.fields}
    applied = 0
    for ch in body.changes:
        fld = by_key.get((ch.visit, ch.name))
        if not fld:
            continue
        for attr in ("status", "min", "max", "required", "repeats"):
            val = getattr(ch, attr)
            if val is not None:
                setattr(fld, attr, val)
        if ch.status == "approved":
            fld.issue = "none"
        applied += 1

    if body.action == "approve_all_remaining":
        for fld in by_key.values():
            if fld.status == "draft":
                fld.status = "approved"

    draft.version = v.version + 1
    nv = db.save_version(s, p, draft.model_dump(), _user(x_user), note=body.note or f"review: {applied} change(s)")
    s.commit()
    return {"version": nv.version, "applied": applied}
