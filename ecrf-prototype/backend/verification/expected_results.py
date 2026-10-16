"""Independently computed expected results.

DO NOT import anything from ecrf/. Different code path on purpose. Reads
the observation table with raw SQL and computes by hand.

Run directly:  python verification/expected_results.py [protocol_id]
Imported by:   ecrf/api/dashboard.py, which compares these against the app.
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def _connect(database_url: str):
    if not database_url.startswith("sqlite"):
        raise RuntimeError("verification script supports sqlite only for now")
    path = database_url.replace("sqlite:///", "")
    return sqlite3.connect(path)


def mean_change_systolic(database_url: str, protocol_id: int) -> float:
    con = _connect(database_url)
    rows = con.execute(
        "SELECT subject_id, visit, value_num FROM observation "
        "WHERE protocol_id=? AND field_name='Systolic Blood Pressure' AND value_num IS NOT NULL",
        (protocol_id,),
    ).fetchall()
    con.close()

    # subject -> visit -> list of readings
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for subj, visit, val in rows:
        acc[subj][visit].append(val)

    diffs = []
    for subj, visits in acc.items():
        if "Day 1" in visits and "Week 12" in visits:
            b = sum(visits["Day 1"]) / len(visits["Day 1"])
            e = sum(visits["Week 12"]) / len(visits["Week 12"])
            diffs.append(e - b)
    # Subjects with no Week 12 are simply not in diffs. That is the rule.
    return sum(diffs) / len(diffs) if diffs else float("nan")


def subjects_per_visit(database_url: str, protocol_id: int) -> dict[str, int]:
    con = _connect(database_url)
    rows = con.execute(
        "SELECT visit, COUNT(DISTINCT subject_id) FROM observation "
        "WHERE protocol_id=? GROUP BY visit", (protocol_id,),
    ).fetchall()
    con.close()
    return {v: n for v, n in rows}


def percent_missing(database_url: str, protocol_id: int) -> float:
    con = _connect(database_url)
    rows = con.execute(
        "SELECT DISTINCT subject_id, visit, field_name FROM observation "
        "WHERE protocol_id=? AND (value_num IS NOT NULL OR value_text IS NOT NULL)",
        (protocol_id,),
    ).fetchall()
    con.close()
    subjects = {r[0] for r in rows}
    fields_by_visit: dict[str, set] = defaultdict(set)
    for _, v, f in rows:
        fields_by_visit[v].add(f)
    expected = sum(len(fs) for fs in fields_by_visit.values()) * len(subjects)
    present = len(rows)
    return round(100.0 * (expected - present) / expected, 1) if expected else 0.0


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    url = f"sqlite:///{Path(__file__).resolve().parent.parent / 'ecrf.db'}"
    print("mean_change_systolic", round(mean_change_systolic(url, pid), 3))
    print("subjects_per_visit  ", subjects_per_visit(url, pid))
    print("percent_missing     ", percent_missing(url, pid))
