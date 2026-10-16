"""Synthetic observation data for the dashboard demo.

Twenty made-up subjects, a plausible blood pressure drop, and three
dropouts so the mean-change calculation has something to get wrong. The
numbers are deterministic (fixed seed) so the independent verification
script can be compared against them.
"""

import random

from sqlalchemy.orm import Session

from ecrf.storage.models import Observation

VISITS = ["Screening", "Day 1", "Week 4", "Week 12"]
DROPOUTS = {"PHX-007", "PHX-013", "PHX-018"}   # no Week 12
LATE_DROPOUT = {"PHX-004"}                       # no Week 4 or Week 12


def generate(protocol_id: int, n: int = 20, seed: int = 401) -> list[Observation]:
    rng = random.Random(seed)
    rows: list[Observation] = []

    def add(subj, visit, field, rep=1, num=None, text=None):
        rows.append(Observation(protocol_id=protocol_id, subject_id=subj, visit=visit,
                                field_name=field, repeat_num=rep, value_num=num,
                                value_text=text, synthetic=True, entered_by="seed"))

    for i in range(1, n + 1):
        subj = f"PHX-{i:03d}"
        base_sys = rng.randint(142, 158)
        base_dia = rng.randint(88, 98)
        weight = round(rng.uniform(62, 96), 1)
        drop_total = rng.uniform(8, 22)       # total fall by week 12
        add(subj, "Screening", "Sex", text=rng.choice(["Male", "Female"]))
        add(subj, "Screening", "Height", num=round(rng.uniform(155, 188), 1))

        for visit in VISITS:
            if visit == "Week 12" and subj in DROPOUTS | LATE_DROPOUT:
                continue
            if visit == "Week 4" and subj in LATE_DROPOUT:
                continue
            frac = {"Screening": 0.0, "Day 1": 0.0, "Week 4": 0.55, "Week 12": 1.0}[visit]
            sys_mean = base_sys - drop_total * frac
            dia_mean = base_dia - (drop_total * 0.45) * frac
            for rep in (1, 2, 3):
                add(subj, visit, "Systolic Blood Pressure", rep, round(sys_mean + rng.uniform(-3, 3)))
                add(subj, visit, "Diastolic Blood Pressure", rep, round(dia_mean + rng.uniform(-2, 2)))
            add(subj, visit, "Position", text="Seated")
            if visit in ("Screening", "Day 1", "Week 12"):
                add(subj, visit, "Weight", num=round(weight + rng.uniform(-0.8, 0.8), 1))
            if visit in ("Screening", "Week 4", "Week 12"):
                add(subj, visit, "HbA1c", num=round(rng.uniform(5.2, 6.4), 1))
                add(subj, visit, "Fasting Plasma Glucose", num=round(rng.uniform(4.6, 6.8), 1))
    return rows


def seed(s: Session, protocol_id: int) -> int:
    rows = generate(protocol_id)
    s.add_all(rows)
    s.flush()
    return len(rows)
