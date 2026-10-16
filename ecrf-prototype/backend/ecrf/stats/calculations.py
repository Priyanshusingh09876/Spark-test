"""The approved calculations.

Each docstring records the clinical decisions behind it. "Mean change from
baseline" is vaguer than it sounds, and the edge cases are the client's
call. Writing them down here stops the next person re-guessing.

PLACEHOLDER SET. The client has not confirmed which calculations the MVP
supports. The decisions below are taken from the sample protocol's own
section 9.1 so the demo is at least internally consistent.
"""

import pandas as pd

BASELINE_VISIT = "Day 1"
ENDPOINT_VISIT = "Week 12"
ENDPOINT_FIELD = "Systolic Blood Pressure"


def _visit_means(df: pd.DataFrame, field: str) -> pd.DataFrame:
    """Average the repeats within a visit first (protocol 9.1)."""
    d = df[(df.field_name == field) & df.value_num.notna()]
    return d.groupby(["subject_id", "visit"], as_index=False).value_num.mean()


def mean_change_from_baseline(df: pd.DataFrame) -> float:
    """Mean change in systolic BP from Day 1 to Week 12.

    Decisions (from sample protocol section 9.1, to be confirmed by client):
      - Baseline is Day 1, not Screening.
      - Average the triplicate readings within a visit FIRST, then
        difference.
      - Subjects without a post-baseline value are EXCLUDED, not treated as
        zero change. Counting them is the dropout bug: with four completers
        at -18, -12, -20, -4 the correct answer is -13.5 and dividing by
        five gives -10.8, which looks entirely plausible and is wrong.
    """
    m = _visit_means(df, ENDPOINT_FIELD)
    base = m[m.visit == BASELINE_VISIT].set_index("subject_id").value_num
    end = m[m.visit == ENDPOINT_VISIT].set_index("subject_id").value_num
    both = base.index.intersection(end.index)
    if len(both) == 0:
        return float("nan")
    return float((end[both] - base[both]).mean())


def subjects_per_visit(df: pd.DataFrame) -> dict[str, int]:
    """Number of subjects with at least one recorded value at each visit."""
    return df.groupby("visit").subject_id.nunique().to_dict()


def percent_missing(df: pd.DataFrame, expected_visits: list[str] | None = None) -> float:
    """Percentage of expected (subject, visit, field) slots with no value.

    Expected slots = every subject x every visit they were due x every
    numeric field seen for that visit. A subject who dropped out counts as
    missing at later visits; that is the point of the metric.
    """
    numeric = df[df.value_num.notna() | df.value_text.notna()]
    subjects = numeric.subject_id.unique()
    visits = expected_visits or sorted(numeric.visit.unique())
    fields_by_visit = numeric.groupby("visit").field_name.unique().to_dict()
    expected = sum(len(fields_by_visit.get(v, [])) for v in visits) * len(subjects)
    present = numeric.drop_duplicates(["subject_id", "visit", "field_name"]).shape[0]
    if expected == 0:
        return 0.0
    return round(100.0 * (expected - present) / expected, 1)
