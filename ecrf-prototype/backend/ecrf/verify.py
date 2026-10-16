"""Stage 3. The grounding check.

Every field's quote must be found in the protocol text or the field is
dropped. No model is involved, which is the point: this step cannot be
talked round, and it kills the primary failure mode where the model
produces a plausible field with a plausible-looking citation.

Two tiers, because exact matching alone is too strict. Models paraphrase
while believing they are quoting, dropping a comma or writing "5" for
"five". The quote is substantively right and a string comparison says no.

THE THRESHOLD IS A PLACEHOLDER. 90 is a starting guess. It must be tuned
against the answer key: too strict rejects good fields, too loose lets a
fabrication built from real protocol vocabulary through.
"""

import re

from rapidfuzz import fuzz

from ecrf.ingest import Document
from ecrf.schema import FieldDef, Rejection, Verdict


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def locate(quote: str, text: str) -> tuple[Verdict, float, int]:
    """Return (verdict, score, offset). Offset is -1 when not found.

    The score is always MEASURED, never asserted. An earlier version
    short-circuited a verbatim hit to a hardcoded 100.0, which made the
    number on screen a claim by this function rather than the result of a
    comparison. A reviewer cannot tell those apart, and a hardcoded number
    cannot be wrong in a way anyone would notice.

    So the similarity is computed for every quote. A verbatim hit still
    scores 100, because that is what comparing a string to itself returns,
    and `verdict` records HOW it matched while `score` records how well.
    """
    q = _norm(quote)
    t = _norm(text)

    # rapidfuzz partial_ratio_alignment finds the best matching window.
    al = fuzz.partial_ratio_alignment(q, t)
    if al is None:
        return "rejected", 0.0, -1
    score = float(al.score)

    i = t.find(q)
    if i >= 0:
        return "exact", score, i
    return "approximate", score, al.dest_start


def section_contains(doc: Document, section_number: str, offset: int) -> bool | None:
    """Does the quote's offset fall inside the claimed section? None if the
    section number is unknown to us."""
    if offset < 0 or not section_number:
        return None
    # offsets from _norm'd text differ slightly from raw; use proportional
    # mapping, which is good enough to place a quote in a section.
    ratio = len(doc.text) / max(1, len(_norm(doc.text)))
    raw_off = int(offset * ratio)
    for s in doc.sections:
        if s.number == section_number:
            return s.start - 50 <= raw_off <= s.end + 50
    # Try parent section, e.g. 7.3.2 claimed, 7.3 exists
    parent = section_number.rsplit(".", 1)[0] if "." in section_number else ""
    for s in doc.sections:
        if parent and s.number == parent:
            return s.start - 50 <= raw_off <= s.end + 50
    return None


def check_field(field: FieldDef, doc: Document, threshold: int) -> FieldDef:
    verdict, score, off = locate(field.source.quote, doc.text)
    # The threshold applies to every field, however it matched. Exempting
    # verbatim hits would mean the one route that skips the check is also
    # the one nobody looks at.
    if score < threshold:
        verdict = "rejected"
    field.verdict = verdict
    field.match_score = round(score, 1)
    field.section_ok = section_contains(doc, field.source.section, off) if verdict != "rejected" else None
    if verdict == "rejected":
        field.status = "rejected"
    elif field.issue != "none":
        field.status = "flagged"
    return field


def filter_fields(
    visit: str, fields: list[FieldDef], doc: Document, threshold: int
) -> tuple[list[FieldDef], list[Rejection]]:
    """Return (kept, rejections). Rejected fields are logged with their
    quote. That log is evidence the fabrication check fires on real input,
    and the data used to tune the threshold. Never discard silently."""
    kept: list[FieldDef] = []
    rejected: list[Rejection] = []
    for f in fields:
        f = check_field(f, doc, threshold)
        if f.verdict == "rejected":
            rejected.append(Rejection(
                visit=visit, name=f.name, quote=f.source.quote,
                section=f.source.section, score=f.match_score or 0.0,
                reason="quote not found in protocol text",
            ))
        else:
            kept.append(f)
    return kept, rejected
