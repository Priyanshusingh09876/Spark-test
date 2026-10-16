"""Section selection: send the model only the parts of the protocol that
matter for one visit, instead of all of it.

Plain keyword scoring, no embeddings. The schedule of activities table and
any section naming the visit always go in; sections mentioning common
assessment words get a lower score and fill up to the budget.

Why this exists: on a self-hosted GPU, context is paid for in VRAM. Sending
three sections instead of 88 pages drops the KV cache from ~13GB to ~1GB,
which is the difference between needing an A100 and a 24GB card.
"""

import re

from ecrf.ingest import Document, Section

_SCHEDULE_WORDS = ("schedule of activities", "schedule of events",
                   "schedule of assessments", "study schedule", "visit schedule")
_ASSESS_WORDS = ("blood pressure", "vital sign", "weight", "height", "ecg",
                 "electrocardiogram", "laboratory", "lab test", "adverse event",
                 "concomitant", "questionnaire", "temperature", "heart rate",
                 "pulse", "respiratory", "assessment", "measurement", "sample")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def score_section(sec: Section, visit: str) -> float:
    body = _norm(sec.text)
    title = _norm(sec.title)
    score = 0.0
    if any(w in title or w in body[:400] for w in _SCHEDULE_WORDS):
        score += 100
    v = _norm(visit)
    score += 20 * body.count(v)
    if v in title:
        score += 30
    score += sum(2 for w in _ASSESS_WORDS if w in body)
    return score


def select(doc: Document, visit: str, token_budget: int = 12000) -> str:
    """Return a trimmed protocol text for one visit, within token_budget."""
    ranked = sorted(doc.sections, key=lambda s: score_section(s, visit), reverse=True)
    chosen: list[Section] = []
    used = 0
    for sec in ranked:
        if score_section(sec, visit) <= 0:
            break
        t = len(sec.text) // 4
        if used + t > token_budget and chosen:
            continue
        chosen.append(sec)
        used += t
    chosen.sort(key=lambda s: s.start)  # keep document order
    if not chosen:
        return doc.text[: token_budget * 4]
    return "\n\n".join(
        (f"[Section {s.number}] {s.title}\n{s.text}" if s.number else s.text)
        for s in chosen
    )
