"""Dashboard numbers. Every scalar statistic is returned alongside the
independently computed value and a pass/fail marker. A number that only
checks itself proves nothing."""

import math
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ecrf.config import config
from ecrf.schema import DraftECRF
from ecrf.stats import registry
from ecrf.storage import db
from ecrf.storage.models import Protocol

# The verification package deliberately lives outside ecrf/ and imports
# nothing from it. We import it here only to compare.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verification import expected_results as independent

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
TOLERANCE = 0.01


def _close(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a == b
    try:
        if math.isnan(a) and math.isnan(b):
            return True
        return abs(float(a) - float(b)) < TOLERANCE
    except (TypeError, ValueError):
        return False


@router.get("/calculations")
def calculations():
    return registry.available()


@router.get("/{protocol_id}")
def dashboard(protocol_id: int, s: Session = Depends(db.get_session)):
    p = s.get(Protocol, protocol_id)
    if not p:
        raise HTTPException(404, "protocol not found")

    # --- extraction summary from the latest version (real data) ---
    v = db.latest_version(s, protocol_id)
    extraction = None
    if v:
        draft = DraftECRF.model_validate(v.content)
        per_visit = [{"visit": f.visit, "fields": len(f.fields),
                      "flagged": sum(1 for x in f.fields if x.issue != "none"),
                      "approved": sum(1 for x in f.fields if x.status == "approved")}
                     for f in draft.forms]
        extraction = {"version": v.version, "summary": draft.summary,
                      "per_visit": per_visit, "rejections": len(draft.rejections),
                      "backend": draft.backend, "model": draft.model}

    # --- statistics over observation data ---
    df = registry.load_frame(s, protocol_id)
    stats = []
    if not df.empty:
        for name, meta in registry.CALCULATIONS.items():
            app_val = registry.run(name, df)
            ind_fn = getattr(independent, {"mean_change_systolic": "mean_change_systolic",
                                           "subjects_per_visit": "subjects_per_visit",
                                           "percent_missing": "percent_missing"}[name])
            ind_val = ind_fn(config.database_url, protocol_id)
            stats.append({
                "name": name, "label": meta["label"], "unit": meta["unit"], "kind": meta["kind"],
                "app": app_val, "independent": ind_val, "pass": _close(app_val, ind_val),
            })
        subjects = int(df.subject_id.nunique())
        readings = len(df)
    else:
        subjects, readings = 0, 0

    return {"protocol": {"id": p.id, "name": p.name}, "extraction": extraction,
            "data": {"subjects": subjects, "readings": readings}, "stats": stats}


@router.post("/{protocol_id}/unsupported")
def unsupported(protocol_id: int, name: str):
    """Exists only to demonstrate the refusal. Anything not in the
    registry is rejected, never approximated."""
    try:
        registry.run(name, registry.load_frame(next(db.get_session()), protocol_id))
    except registry.UnsupportedAnalysis as e:
        raise HTTPException(
            403, f"'{name}' is not an approved calculation. The approved set is: "
                 f"{', '.join(registry.CALCULATIONS)}. Adding one means writing, testing "
                 f"and independently verifying it first.") from e
    return {"error": "should not reach here"}
