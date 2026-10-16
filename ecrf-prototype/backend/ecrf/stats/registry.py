"""A fixed registry of client-approved calculations.

There is no general query path. The dashboard is built from
CALCULATIONS.keys(), so an unapproved analysis is not an option the
interface can offer. The absence of a free-text input IS the enforcement.
"""

from collections.abc import Callable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.stats import calculations
from ecrf.storage.models import Observation


class UnsupportedAnalysis(Exception):
    """Raised for anything not in the registry. Never approximate."""


CALCULATIONS: dict[str, dict] = {
    "mean_change_systolic": {
        "label": "Mean change in systolic BP, Day 1 to Week 12",
        "unit": "mmHg",
        "fn": calculations.mean_change_from_baseline,
        "kind": "scalar",
    },
    "subjects_per_visit": {
        "label": "Subjects with data at each visit",
        "unit": "subjects",
        "fn": calculations.subjects_per_visit,
        "kind": "by_visit",
    },
    "percent_missing": {
        "label": "Missing values across expected slots",
        "unit": "%",
        "fn": calculations.percent_missing,
        "kind": "scalar",
    },
}


def available() -> list[dict]:
    return [{"name": k, "label": v["label"], "unit": v["unit"], "kind": v["kind"]}
            for k, v in CALCULATIONS.items()]


def load_frame(s: Session, protocol_id: int) -> pd.DataFrame:
    rows = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id)).all()
    return pd.DataFrame([{
        "subject_id": r.subject_id, "visit": r.visit, "field_name": r.field_name,
        "repeat_num": r.repeat_num, "value_num": r.value_num, "value_text": r.value_text,
    } for r in rows])


def run(name: str, df: pd.DataFrame):
    if name not in CALCULATIONS:
        raise UnsupportedAnalysis(name)
    fn: Callable = CALCULATIONS[name]["fn"]
    return fn(df)
