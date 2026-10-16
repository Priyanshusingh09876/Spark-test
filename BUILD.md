# BUILD.md — eCRF Builder prototype

> **For Claude Code.** Read this file and execute it end to end in one pass.
>
> 1. Create every file in Parts A, B and C at the exact path given, with the
>    exact contents given. Do not ask between files. Do not "improve" the
>    backend code: it has been run and tested and the tests in Part D assert
>    specific numbers that depend on it.
> 2. Part B also contains a SPEC for the frontend pages and components. Build
>    those files from the spec. Use only `react`, `react-dom` and
>    `react-router-dom`. No UI framework, no icon library, no chart library.
>    Charts are hand-rolled SVG as specified.
> 3. Run Part D and report the output. Fix frontend build errors if any.
>    Do not touch backend files to make frontend code compile.
>
> Everything runs with **no API key, no GPU, no Postgres**. Switching to a
> real model later is three lines in `.env` (Part E).

---

## What this is

BU Spark! Fall 2026 · DS519 · Client: Phoenix Clinical · Project: ECRF
Creator and Real-Time Reporting.

A clinical trial protocol PDF goes in. Draft eCRF forms come out, every
generated field carrying a verbatim protocol quote. Code (not a model)
searches the protocol for that quote and deletes any field whose quote is
not found. A reviewer approves, synthetic data is entered through the
approved forms with validation, and a dashboard shows statistics that have
been independently recomputed by a script that shares no code with the app.

The bundled sample protocol is synthetic and has two things planted so the
safety behaviour is visible on first run: a contradiction (5 vs 10 minute
rest) that gets flagged, and a fabricated heart rate field whose quote does
not exist, which gets deleted with a match score of 57.

```
protocol.pdf → ingest → extract (visits, then per-visit fields) → verify quotes
            → CDASH enrich → version 1 → review → version 2 → data entry
            → stats (fixed registry, independently checked) → dashboard
```

---

## Repository layout

```
ecrf-prototype/
├── README.md
├── run.sh
├── .env.example
├── .gitignore
├── backend/
│   ├── pyproject.toml
│   ├── ecrf/
│   │   ├── __init__.py  config.py  schema.py  ingest.py  sections.py
│   │   ├── cdash.py  verify.py  pipeline.py
│   │   ├── extract/   __init__.py  base.py  prompts.py  openai_compat.py  mock.py
│   │   ├── storage/   __init__.py  models.py  db.py
│   │   ├── stats/     __init__.py  calculations.py  registry.py  seed.py
│   │   └── api/       __init__.py  app.py  protocols.py  data.py  dashboard.py
│   ├── data/
│   │   ├── cdash_library.yaml
│   │   ├── sample/make_sample_protocol.py      (generates the PDF)
│   │   └── recorded/PHX-401-201.json
│   ├── verification/  README.md  expected_results.py
│   ├── scripts/fetch_ctgov_protocol.py
│   └── tests/test_pipeline.py
└── frontend/
    ├── package.json  vite.config.ts  tsconfig.json  index.html
    ├── public/logo.svg
    └── src/
        ├── main.tsx  App.tsx
        ├── api/       types.ts  client.ts
        ├── styles/    tokens.css  global.css
        ├── components/ Layout.tsx  Badge.tsx  FieldCard.tsx  Stat.tsx
        │               charts/BarChart.tsx  charts/DonutChart.tsx
        └── pages/     Protocols.tsx  Review.tsx  DataEntry.tsx  Dashboard.tsx
```

---

# Part A — Backend (verbatim, tested)

Python 3.11+. Every file below is exact. Create the empty directory
`backend/data/uploads/` and `backend/data/protocols/` too.

### `backend/pyproject.toml`

```toml
[project]
name = "ecrf-backend"
version = "0.1.0"
description = "Protocol to draft eCRF pipeline with grounded verification"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "python-multipart>=0.0.12",
    "pydantic>=2.9",
    "sqlalchemy>=2.0",
    "pdfplumber>=0.11",
    "rapidfuzz>=3.10",
    "pandas>=2.2",
    "pyyaml>=6.0",
    "openai>=1.54",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.27", "ruff>=0.7"]
postgres = ["psycopg[binary]>=3.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ecrf"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

### `backend/ecrf/__init__.py`

```python
"""eCRF pipeline: protocol PDF in, verified draft forms out."""

__version__ = "0.1.0"
```

### `backend/ecrf/config.py`

```python
"""Runtime configuration, read from the environment.

The extraction backend is a config value on purpose. Which LLM service is
approved is still an open question with the client, so nothing outside
ecrf/extract/ names a vendor.

Every provider we might use speaks the OpenAI chat-completions format
(OpenAI, vLLM, Groq, OpenRouter, Gemini's compat endpoint), so one backend
covers all of them and the difference is three env vars.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


@dataclass(frozen=True)
class Config:
    # "mock" replays a recorded fixture and needs no key. "openai_compat"
    # talks to whatever LLM_BASE_URL points at.
    backend: str

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float

    # "full" sends the whole protocol, "sections" sends only relevant
    # sections, "auto" picks by size.
    context_mode: str
    context_token_limit: int

    # Fuzzy match threshold for quote grounding. PLACEHOLDER until tuned
    # against the answer key. Single most consequential number here.
    quote_match_threshold: int

    database_url: str
    data_dir: Path


def load() -> Config:
    return Config(
        backend=os.getenv("ECRF_BACKEND", "mock"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        context_mode=os.getenv("ECRF_CONTEXT", "auto"),
        context_token_limit=int(os.getenv("ECRF_CONTEXT_TOKEN_LIMIT", "60000")),
        quote_match_threshold=int(os.getenv("QUOTE_MATCH_THRESHOLD", "90")),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'ecrf.db'}"),
        data_dir=Path(os.getenv("ECRF_DATA_DIR", ROOT / "data")),
    )


config = load()
```

### `backend/ecrf/schema.py`

```python
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
```

### `backend/ecrf/ingest.py`

```python
"""Stage 1. PDF in, structured document + one normalised text string out.

Not AI. A PDF already stores every character with its position and font, so
reading it is a lookup, not interpretation.

Rules that matter downstream:
  1. Tables are extracted separately. extract_text flattens the Schedule of
     Activities and loses which column each mark sat under.
  2. Normalisation happens here and nowhere else. Stage 3 compares model
     output against this exact string; a second, slightly different cleanup
     is how that check silently breaks.
  3. We keep a structured representation (sections with numbers and page
     ranges) alongside the flat text. Section selection and the section
     check in verify.py both use it.
"""

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import pdfplumber


class ScannedPDFError(Exception):
    """Raised when a PDF has no text layer. Out of scope for the MVP."""


@dataclass
class Section:
    number: str          # "7.3.2", or "" for unnumbered
    title: str
    page_start: int
    text: str = ""
    start: int = 0       # char offset into the flat normalised text
    end: int = 0


@dataclass
class Document:
    text: str
    sections: list[Section] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    pages: int = 0
    hash: str = ""
    tokens_estimate: int = 0


# ------------------------------------------------------------------ gate

def has_text_layer(path: str) -> bool:
    """True if pdffonts lists any font. No fonts means the PDF is images.

    Cheap gate. Without it a scanned protocol runs the whole pipeline and
    produces an empty extraction with a confusing error.
    Falls back to pdfplumber if poppler is not installed.
    """
    if shutil.which("pdffonts"):
        out = subprocess.run(["pdffonts", path], capture_output=True, text=True)
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        return len(lines) > 2  # header + separator + at least one font
    with pdfplumber.open(path) as pdf:
        return any((p.extract_text() or "").strip() for p in pdf.pages[:3])


# -------------------------------------------------------- normalisation

_SUBS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
    "•": "-", "ﬁ": "fi", "ﬂ": "fl",
}


def normalise(text: str) -> str:
    """Collapse whitespace, ASCII-fy quotes and dashes, rejoin hyphenated
    line breaks. Called exactly once, from load(). Never anywhere else.
    """
    for k, v in _SUBS.items():
        text = text.replace(k, v)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # hyphen at line end
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_table(rows: list[list[str | None]]) -> str:
    """Pipe-delimited rows so column alignment survives into the prompt."""
    out = []
    for r in rows:
        cells = [(c or "").replace("\n", " ").strip() for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


# ------------------------------------------------------------ sections

_HEADING = re.compile(
    r"^(?:(?:Section|SECTION)\s+)?(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^\n]{2,90})$"
)


def split_sections(text: str, page_of_offset) -> list[Section]:
    """Find numbered headings like '7.3.2 Blood Pressure Measurement' and
    slice the text between them."""
    heads = []
    for m in re.finditer(_HEADING.pattern, text, flags=re.MULTILINE):
        heads.append((m.start(), m.group(1), m.group(2).strip()))

    sections: list[Section] = []
    if not heads:
        return [Section("", "Document", 1, text, 0, len(text))]
    if heads[0][0] > 0:
        sections.append(Section("", "Front matter", 1, text[: heads[0][0]], 0, heads[0][0]))
    for i, (start, num, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        sections.append(Section(num, title, page_of_offset(start), text[start:end], start, end))
    return sections


# ----------------------------------------------------------------- load

def load(path: str) -> Document:
    """Read a protocol PDF into a Document. Raises ScannedPDFError if the
    PDF has no text layer."""
    if not has_text_layer(path):
        raise ScannedPDFError(
            "This PDF has no text layer (it is probably a scan). "
            "OCR is out of scope for the prototype."
        )

    page_chunks: list[str] = []
    tables: list[list[list[str]]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            for t in page.extract_tables():
                if t and any(any(c for c in row) for row in t):
                    tables.append([[(c or "") for c in row] for row in t])
                    txt += "\n\n" + render_table(t) + "\n"
            page_chunks.append(txt)
        pages = len(pdf.pages)

    # Build page offset map on the normalised text.
    normalised_pages = [normalise(c) for c in page_chunks]
    text = "\n\n".join(normalised_pages)
    offsets = []
    pos = 0
    for p in normalised_pages:
        offsets.append(pos)
        pos += len(p) + 2

    def page_of_offset(off: int) -> int:
        for i, o in enumerate(offsets):
            if off < o:
                return i
        return len(offsets)

    doc = Document(text=text, tables=tables, pages=pages)
    doc.sections = split_sections(text, page_of_offset)
    doc.hash = hashlib.sha256(text.encode()).hexdigest()
    doc.tokens_estimate = len(text) // 4
    return doc


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
```

### `backend/ecrf/sections.py`

```python
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
```

### `backend/ecrf/cdash.py`

```python
"""CDASH enrichment. Deterministic, no model.

After extraction and verification, each surviving field is matched against
the library by name (aliases first, then fuzzy). A match attaches the CDASH
code and domain, and fills in type, unit or range the model left blank.

It never adds fields the model did not produce. Anything the library thinks
is missing is returned separately as a suggestion, clearly labelled as not
coming from the protocol, so the grounding guarantee stays honest.
"""

from functools import lru_cache

import yaml
from rapidfuzz import fuzz, process

from ecrf.config import config
from ecrf.schema import FieldDef, VisitForm


@lru_cache(maxsize=1)
def library() -> dict:
    with open(config.data_dir / "cdash_library.yaml") as f:
        return yaml.safe_load(f)["domains"]


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[str, dict]]:
    """lowercase name/alias -> (domain, field entry)"""
    idx: dict[str, tuple[str, dict]] = {}
    for dom, d in library().items():
        for fld in d["fields"]:
            idx[fld["name"].lower()] = (dom, fld)
            for a in fld.get("aliases", []):
                idx[a.lower()] = (dom, fld)
    return idx


def match(name: str, min_score: int = 85) -> tuple[str, dict] | None:
    idx = _index()
    key = name.strip().lower()
    if key in idx:
        return idx[key]
    best = process.extractOne(key, list(idx.keys()), scorer=fuzz.token_set_ratio)
    if best and best[1] >= min_score:
        return idx[best[0]]
    return None


def enrich(field: FieldDef) -> FieldDef:
    hit = match(field.name)
    if not hit:
        return field
    dom, entry = hit
    field.cdash = entry.get("cdash")
    field.domain = dom
    if field.unit is None and entry.get("unit"):
        field.unit = entry["unit"]
    if field.min is None and entry.get("min") is not None:
        field.min = entry["min"]
    if field.max is None and entry.get("max") is not None:
        field.max = entry["max"]
    if field.choices is None and entry.get("choices"):
        field.choices = entry["choices"]
    return field


def suggestions(form: VisitForm) -> list[dict]:
    """Standard fields the library has for the domains present in this form
    that the model did NOT produce. Not grounded in the protocol. Shown to
    the reviewer as 'the library also defines these', nothing more."""
    present = {f.cdash for f in form.fields if f.cdash}
    domains = {f.domain for f in form.fields if f.domain}
    out = []
    for dom in domains:
        for entry in library()[dom]["fields"]:
            if entry["cdash"] not in present:
                out.append({"domain": dom, "name": entry["name"],
                            "cdash": entry["cdash"], "type": entry.get("type"),
                            "unit": entry.get("unit")})
    return out
```

### `backend/ecrf/verify.py`

```python
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
    """Return (verdict, score, offset). Offset is -1 when not found."""
    q = _norm(quote)
    t = _norm(text)
    i = t.find(q)
    if i >= 0:
        return "exact", 100.0, i
    # rapidfuzz partial_ratio_alignment finds the best matching window.
    al = fuzz.partial_ratio_alignment(q, t)
    if al is None:
        return "rejected", 0.0, -1
    return ("approximate", float(al.score), al.dest_start)


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
    if verdict == "approximate" and score < threshold:
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
```

### `backend/ecrf/pipeline.py`

```python
"""End to end orchestration for stages 1 to 3.

    ingest  ->  list visits  ->  per visit: fields  ->  verify quotes
            ->  CDASH enrich ->  save version 1

The visit-list call is sent alone first so it writes the provider's prompt
cache; the per-visit calls then hit it. Running them concurrently before
the first returns would make them all miss.
"""

import time
from dataclasses import asdict

from ecrf import cdash, sections, verify
from ecrf.config import config
from ecrf.extract import get_extractor
from ecrf.ingest import Document, load
from ecrf.schema import DraftECRF, Rejection, VisitForm


def _context_for(doc: Document, visit: str) -> str:
    mode = config.context_mode
    if mode == "sections":
        return sections.select(doc, visit)
    if mode == "full":
        return doc.text
    # auto
    if doc.tokens_estimate > config.context_token_limit:
        return sections.select(doc, visit)
    return doc.text


def run(pdf_path: str, protocol_id: int, backend: str | None = None,
        doc: Document | None = None, log=print) -> DraftECRF:
    t0 = time.time()
    doc = doc or load(pdf_path)
    ex = get_extractor(backend)
    log(f"[pipeline] backend={ex.name} model={ex.model} "
        f"tokens~{doc.tokens_estimate} context={config.context_mode}")

    # Pass one: visits. Full text, this is the backbone.
    visits = ex.list_visits(doc.text).visits
    log(f"[pipeline] visits: {visits}")

    forms: list[VisitForm] = []
    rejections: list[Rejection] = []
    counts = {"exact": 0, "approximate": 0, "rejected": 0, "flagged": 0}

    for v in visits:
        ctx = _context_for(doc, v)
        form = ex.fields_for_visit(ctx, v, visits)
        kept, rej = verify.filter_fields(v, form.fields, doc, config.quote_match_threshold)
        kept = [cdash.enrich(f) for f in kept]
        for f in kept:
            counts[f.verdict] += 1
            if f.issue != "none":
                counts["flagged"] += 1
        counts["rejected"] += len(rej)
        rejections.extend(rej)
        forms.append(VisitForm(visit=v, form=form.form, fields=kept))
        log(f"[pipeline] {v}: kept {len(kept)}, rejected {len(rej)}")

    total = sum(len(f.fields) for f in forms) + len(rejections)
    draft = DraftECRF(
        protocol_id=protocol_id,
        protocol_hash=doc.hash,
        version=1,
        backend=ex.name,
        model=ex.model,
        forms=forms,
        rejections=rejections,
        summary={
            "visits": len(visits),
            "fields_generated": total,
            "fields_kept": total - len(rejections),
            **counts,
            "threshold": config.quote_match_threshold,
            "seconds": round(time.time() - t0, 2),
        },
    )
    return draft
```

### `backend/ecrf/extract/__init__.py`

```python
from ecrf.extract.base import Extractor, get_extractor

__all__ = ["Extractor", "get_extractor"]
```

### `backend/ecrf/extract/base.py`

```python
"""The adapter.

The model is a config value, not a dependency. Switching from a hosted API
to a self-hosted model, or between vendors, is three environment variables
and no code change.
"""

from typing import Protocol

from ecrf.config import config
from ecrf.schema import VisitForm, VisitList


class Extractor(Protocol):
    name: str
    model: str

    def list_visits(self, protocol_text: str) -> VisitList:
        """Pass one. The visit list is the backbone everything loops over,
        so it gets its own call rather than being folded into the first
        visit's request."""
        ...

    def fields_for_visit(self, protocol_text: str, visit: str,
                         visits: list[str]) -> VisitForm:
        """Pass two, once per visit. Prompt order is load bearing for
        caching: stable prefix first, varying question last."""
        ...


def get_extractor(backend: str | None = None) -> Extractor:
    backend = backend or config.backend
    if backend == "mock":
        from ecrf.extract.mock import MockExtractor
        return MockExtractor()
    if backend == "openai_compat":
        from ecrf.extract.openai_compat import OpenAICompatExtractor
        return OpenAICompatExtractor(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.llm_temperature,
        )
    raise ValueError(f"unknown ECRF_BACKEND: {backend}")
```

### `backend/ecrf/extract/prompts.py`

```python
"""Prompt assembly.

ORDER IS LOAD BEARING. Providers discount a repeated prefix by around 90%,
but only when it is byte-identical and at the very start. We send the same
protocol once per visit, so:

    [system instruction]   stable
    [protocol text]        stable, cached
    [visit list]           stable within a run
    [the question]         varies

Never put anything that changes per call above the protocol. A timestamp
or request id in the system instruction kills every cache hit silently.
"""

import json

from ecrf.schema import model_field_schema, model_visits_schema

SYSTEM = """\
You extract electronic case report form (eCRF) field definitions from
clinical trial protocols. You answer ONLY with a JSON object matching the
schema you are given. No prose, no markdown fences.

Rules:
1. Every field MUST carry source.quote: a verbatim fragment copied from the
   protocol, at least 20 characters, exactly as written. The quote will be
   searched for in the protocol text. A quote that is not found causes the
   field to be discarded, so copy precisely rather than paraphrasing.
2. source.section is the section number the quote came from, e.g. "7.3.2".
3. Never state a value the protocol does not give. If a range, unit or
   requirement is not stated, leave it null.
4. If the protocol is unclear, contradictory, or silent on something it
   should specify, keep the field but set issue to one of: missing,
   conflicting, ambiguous, unsupported, and explain in issue_note.
   Flagging beats guessing.
5. Use these standard field names where they apply: Systolic Blood
   Pressure, Diastolic Blood Pressure, Heart Rate, Temperature, Respiratory
   Rate, Position, Weight, Height, ECG Performed, ECG Result, QTcF Interval,
   HbA1c, Fasting Plasma Glucose, Adverse Event Term, AE Start Date,
   AE Severity, Date of Birth, Sex.
6. If a measurement is taken more than once at a visit (e.g. in triplicate),
   set repeats to that count.
"""


def visits_messages(protocol_text: str) -> list[dict]:
    schema = json.dumps(model_visits_schema())
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"PROTOCOL:\n\n{protocol_text}\n\n"
            "TASK: List the study visits in the order they occur, using the "
            "names the protocol uses (e.g. Screening, Day 1, Week 4). "
            f"Respond with JSON matching this schema:\n{schema}"
        )},
    ]


def fields_messages(protocol_text: str, visit: str, visits: list[str]) -> list[dict]:
    schema = json.dumps(model_field_schema())
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"PROTOCOL:\n\n{protocol_text}\n\n"
            f"STUDY VISITS: {', '.join(visits)}\n\n"
            f"TASK: List every data field that must be collected at the "
            f"\"{visit}\" visit only. Include validation ranges, units and "
            f"repeat counts only when the protocol states them. "
            f"Respond with JSON matching this schema:\n{schema}"
        )},
    ]
```

### `backend/ecrf/extract/openai_compat.py`

````python
"""One backend for every provider that speaks the OpenAI chat format.

    OpenAI       LLM_BASE_URL=https://api.openai.com/v1
    vLLM (SCC)   LLM_BASE_URL=http://localhost:8000/v1
    Groq         LLM_BASE_URL=https://api.groq.com/openai/v1
    OpenRouter   LLM_BASE_URL=https://openrouter.ai/api/v1
    Gemini       LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

JSON mode is requested where the provider supports it; the response is
validated with Pydantic either way, and one retry feeds the validation
error back. If the second attempt also fails, the error surfaces rather
than a silent empty result.
"""

import json
import re

from openai import OpenAI
from pydantic import ValidationError

from ecrf.extract import prompts
from ecrf.schema import VisitForm, VisitList

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class OpenAICompatExtractor:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.0):
        if not api_key and "localhost" not in base_url and "127.0.0.1" not in base_url:
            raise RuntimeError("LLM_API_KEY is not set")
        self.client = OpenAI(base_url=base_url, api_key=api_key or "none")
        self.model = model
        self.temperature = temperature

    # ---------------------------------------------------------- internals
    def _chat(self, messages: list[dict]) -> str:
        kwargs = dict(model=self.model, messages=messages, temperature=self.temperature)
        try:
            resp = self.client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs)
        except Exception:
            # Some compat servers reject response_format. Try without.
            resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _json(self, messages: list[dict], model_cls):
        raw = self._chat(messages)
        try:
            return model_cls.model_validate(json.loads(_FENCE.sub("", raw).strip()))
        except (json.JSONDecodeError, ValidationError) as e:
            retry = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"That response was invalid: {e}\n"
                    "Return ONLY a corrected JSON object matching the schema."
                )},
            ]
            raw2 = self._chat(retry)
            return model_cls.model_validate(json.loads(_FENCE.sub("", raw2).strip()))

    # ---------------------------------------------------------- interface
    def list_visits(self, protocol_text: str) -> VisitList:
        return self._json(prompts.visits_messages(protocol_text), VisitList)

    def fields_for_visit(self, protocol_text: str, visit: str, visits: list[str]) -> VisitForm:
        return self._json(prompts.fields_messages(protocol_text, visit, visits), VisitForm)
````

### `backend/ecrf/extract/mock.py`

```python
"""Offline backend. Replays a recorded extraction for the bundled sample
protocol so the whole pipeline runs with no API key and no GPU.

If the uploaded protocol is not the sample, it returns an empty result with
a clear note rather than pretending. Set ECRF_BACKEND=openai_compat for
anything real.
"""

import json

from ecrf.config import config
from ecrf.schema import VisitForm, VisitList

SAMPLE_MARKER = "PHX-401-201"


class MockExtractor:
    name = "mock"
    model = "recorded/PHX-401-201"

    def __init__(self) -> None:
        with open(config.data_dir / "recorded" / "PHX-401-201.json") as f:
            self.fixture = json.load(f)

    def _is_sample(self, text: str) -> bool:
        return SAMPLE_MARKER in text[:2000]

    def list_visits(self, protocol_text: str) -> VisitList:
        if not self._is_sample(protocol_text):
            return VisitList(visits=[])
        return VisitList(visits=self.fixture["visits"])

    def fields_for_visit(self, protocol_text: str, visit: str, visits: list[str]) -> VisitForm:
        if not self._is_sample(protocol_text):
            return VisitForm(visit=visit, fields=[])
        form = self.fixture["forms"].get(visit)
        if not form:
            return VisitForm(visit=visit, fields=[])
        return VisitForm.model_validate(form)
```

### `backend/ecrf/storage/__init__.py`

```python
"""Persistence. JSON for drafts being edited, relational for readings.

SQLite by default so the prototype runs with zero setup. Postgres is a
DATABASE_URL change; SQLAlchemy's JSON type works on both.
"""
```

### `backend/ecrf/storage/models.py`

```python
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Protocol(Base):
    """A protocol document, with the normalised text we extract from."""

    __tablename__ = "protocol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(300))
    text_hash: Mapped[str] = mapped_column(String(64))
    normalised: Mapped[str] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON)       # [{number,title,start,end,page}]
    pages: Mapped[int] = mapped_column(Integer)
    tokens_estimate: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ECRFVersion(Base):
    """Draft and approved eCRFs. APPEND ONLY.

    An approval inserts a new row with version + 1 and never updates in
    place, so this table IS the version history and the audit trail.
    protocol_hash pins each version to the exact document text it came
    from, which is what makes the traceability claim hold after an
    amendment.
    """

    __tablename__ = "ecrf_version"
    __table_args__ = (UniqueConstraint("protocol_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    protocol_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)         # DraftECRF as dict
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Observation(Base):
    """Collected readings. Synthetic or approved de-identified data ONLY.

    repeat_num is what makes triplicate measurements storable without
    three near-identical columns, and what the statistics average over.
    """

    __tablename__ = "observation"
    __table_args__ = (UniqueConstraint("protocol_id", "subject_id", "visit",
                                       "field_name", "repeat_num"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    subject_id: Mapped[str] = mapped_column(String(50))
    visit: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(200))
    repeat_num: Mapped[int] = mapped_column(Integer, default=1)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    entered_by: Mapped[str] = mapped_column(String(100))
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### `backend/ecrf/storage/db.py`

```python
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ecrf.config import config
from ecrf.storage.models import Base, ECRFVersion, Protocol

_engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False} if config.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)


@contextmanager
def session() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI dependency."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def latest_version(s: Session, protocol_id: int) -> ECRFVersion | None:
    return s.scalars(
        select(ECRFVersion)
        .where(ECRFVersion.protocol_id == protocol_id)
        .order_by(ECRFVersion.version.desc())
        .limit(1)
    ).first()


def save_version(s: Session, protocol: Protocol, content: dict, created_by: str,
                 note: str | None = None) -> ECRFVersion:
    """Insert a NEW version row. Never updates an existing one."""
    prev = latest_version(s, protocol.id)
    v = ECRFVersion(
        protocol_id=protocol.id,
        protocol_hash=protocol.text_hash,
        version=(prev.version + 1) if prev else 1,
        content=content,
        created_by=created_by,
        note=note,
    )
    s.add(v)
    s.flush()
    return v
```

### `backend/ecrf/stats/__init__.py`

```python
"""Approved statistics. Anything not in the registry is refused."""
```

### `backend/ecrf/stats/calculations.py`

```python
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
```

### `backend/ecrf/stats/registry.py`

```python
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
```

### `backend/ecrf/stats/seed.py`

```python
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

        for v_idx, visit in enumerate(VISITS):
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
```

### `backend/ecrf/api/__init__.py`

```python

```

### `backend/ecrf/api/app.py`

```python
"""FastAPI application. Run with:  uvicorn ecrf.api.app:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecrf import __version__
from ecrf.api import dashboard, data, protocols
from ecrf.config import config
from ecrf.storage import db

app = FastAPI(title="eCRF Pipeline", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(protocols.router)
app.include_router(data.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "backend": config.backend,
            "model": config.llm_model if config.backend != "mock" else "recorded",
            "context_mode": config.context_mode,
            "quote_match_threshold": config.quote_match_threshold}
```

### `backend/ecrf/api/protocols.py`

```python
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
    """Rebuild a Document from stored text + sections, no re-parse."""
    doc = ingest.Document(text=p.normalised, pages=p.pages, hash=p.text_hash,
                          tokens_estimate=p.tokens_estimate)
    doc.sections = [ingest.Section(s["number"], s["title"], s["page"], "",
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
```

### `backend/ecrf/api/data.py`

```python
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
```

### `backend/ecrf/api/dashboard.py`

```python
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
from verification import expected_results as independent  # noqa: E402

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
        readings = int(len(df))
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
    except registry.UnsupportedAnalysis:
        raise HTTPException(
            403, f"'{name}' is not an approved calculation. The approved set is: "
                 f"{', '.join(registry.CALCULATIONS)}. Adding one means writing, testing "
                 f"and independently verifying it first.")
    return {"error": "should not reach here"}
```

### `backend/verification/README.md`

```markdown
# Independent verification

**This directory must not import from `ecrf/`.**

Every statistic the application reports is recomputed here from the raw
`observation` table, using plain SQL and arithmetic that shares nothing with
the pipeline. The dashboard shows both numbers side by side with a pass or
fail marker.

A shared helper would defeat the whole exercise: a bug inside it appears
identically in both answers, the comparison passes, and both numbers are
wrong. One number that only checks itself proves nothing.

This code may be slow and ugly. It is not production code, it is evidence.

Ideally a different team member writes and maintains this file.
```

### `backend/verification/expected_results.py`

```python
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
```

### `backend/data/cdash_library.yaml`

```yaml
# CDASH-style field library.
#
# Idea credited to the team architecture draft: the model identifies
# concepts, a library defines the standard fields. The model invents less
# when it picks from a known list.
#
# This is a SEED, written from general CDASH knowledge. Phoenix's own
# library replaces it. Member 2 owns this file.
#
# Enrichment is deterministic and never adds fields the model did not
# produce. It attaches cdash codes and fills missing type/unit/range.

domains:
  VS:
    label: Vital Signs
    triggers: [vital signs, blood pressure, heart rate, pulse, temperature,
               respiratory rate, oxygen saturation]
    fields:
      - name: Systolic Blood Pressure
        cdash: VSORRES_SYSBP
        aliases: [Systolic BP, SBP, Systolic]
        type: integer
        unit: mmHg
        min: 60
        max: 250
      - name: Diastolic Blood Pressure
        cdash: VSORRES_DIABP
        aliases: [Diastolic BP, DBP, Diastolic]
        type: integer
        unit: mmHg
        min: 30
        max: 150
      - name: Heart Rate
        cdash: VSORRES_HR
        aliases: [Pulse, Pulse Rate, HR]
        type: integer
        unit: bpm
        min: 30
        max: 220
      - name: Temperature
        cdash: VSORRES_TEMP
        aliases: [Body Temperature, Temp]
        type: decimal
        unit: C
        min: 34
        max: 42
      - name: Respiratory Rate
        cdash: VSORRES_RESP
        aliases: [RR, Breathing Rate]
        type: integer
        unit: breaths/min
        min: 6
        max: 60
      - name: Position
        cdash: VSPOS
        aliases: [Body Position, Posture, Subject Position]
        type: choice
        choices: [Sitting, Supine, Standing]

  BW:
    label: Body Measurements
    triggers: [weight, height, bmi, body mass]
    fields:
      - name: Weight
        cdash: VSORRES_WEIGHT
        aliases: [Body Weight, Wt]
        type: decimal
        unit: kg
        min: 20
        max: 300
      - name: Height
        cdash: VSORRES_HEIGHT
        aliases: [Body Height, Ht]
        type: decimal
        unit: cm
        min: 100
        max: 250

  EG:
    label: ECG
    triggers: [ecg, electrocardiogram, qt interval, qtc]
    fields:
      - name: ECG Performed
        cdash: EGPERF
        aliases: [ECG Done, Electrocardiogram Performed]
        type: boolean
      - name: ECG Result
        cdash: EGORRES
        aliases: [ECG Interpretation, ECG Finding]
        type: choice
        choices: [Normal, Abnormal not clinically significant, Abnormal clinically significant]
      - name: QTcF Interval
        cdash: EGORRES_QTCF
        aliases: [QTc, QTcF, Corrected QT]
        type: integer
        unit: ms
        min: 300
        max: 600

  LB:
    label: Laboratory
    triggers: [laboratory, lab, hba1c, glucose, haemoglobin, hemoglobin,
               creatinine, blood sample]
    fields:
      - name: HbA1c
        cdash: LBORRES_HBA1C
        aliases: [Glycated Haemoglobin, Glycated Hemoglobin, A1c]
        type: decimal
        unit: "%"
        min: 3
        max: 20
      - name: Fasting Plasma Glucose
        cdash: LBORRES_GLUC
        aliases: [FPG, Fasting Glucose, Glucose]
        type: decimal
        unit: mmol/L
        min: 1
        max: 40
      - name: Sample Collected
        cdash: LBPERF
        aliases: [Blood Sample Collected, Lab Sample Taken]
        type: boolean

  AE:
    label: Adverse Events
    triggers: [adverse event, side effect, ae, serious adverse]
    fields:
      - name: Adverse Event Term
        cdash: AETERM
        aliases: [AE Term, Event, Adverse Event]
        type: text
      - name: AE Start Date
        cdash: AESTDAT
        aliases: [Onset Date, Start Date]
        type: date
      - name: AE Severity
        cdash: AESEV
        aliases: [Severity, Grade]
        type: choice
        choices: [Mild, Moderate, Severe]

  DM:
    label: Demographics
    triggers: [demographics, date of birth, sex, age, ethnicity]
    fields:
      - name: Date of Birth
        cdash: BRTHDAT
        aliases: [DOB, Birth Date]
        type: date
      - name: Sex
        cdash: SEX
        aliases: [Gender]
        type: choice
        choices: [Male, Female]
```

### `backend/data/sample/make_sample_protocol.py`

```python
"""Generate the bundled sample protocol, PHX-401-201.

Synthetic. Written to look like a real Phase II protocol so the pipeline
has something realistic to chew on without any confidential material.

Two things are planted on purpose:
  - Section 7.3.2 says 5 minutes of rest; Appendix B says 10 minutes.
    The model should flag this as conflicting rather than pick one.
  - There is NO heart rate requirement anywhere. The mock extractor
    fabricates one, and the grounding check should delete it.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

OUT = Path(__file__).parent / "PHX-401-201_protocol.pdf"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Normal"], fontName="Helvetica-Bold",
                    fontSize=13, spaceBefore=18, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Normal"], fontName="Helvetica-Bold",
                    fontSize=11, spaceBefore=12, spaceAfter=6)
B = ParagraphStyle("B", parent=ss["Normal"], fontName="Times-Roman",
                   fontSize=10, leading=14, spaceAfter=6)
T = ParagraphStyle("T", parent=ss["Normal"], fontName="Helvetica-Bold",
                   fontSize=18, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontName="Helvetica",
                     fontSize=10, textColor=colors.grey, spaceAfter=24)

s = []
p = lambda t, st=B: s.append(Paragraph(t, st))

# ---------------------------------------------------------------- cover
p("Clinical Study Protocol PHX-401-201", T)
p("A Phase II, Randomised, Double-Blind, Placebo-Controlled Study of PHX-401 "
  "in Adults with Stage 1 Hypertension", SUB)
p("Sponsor: Phoenix Clinical (synthetic sample)  |  Protocol version 2.0  |  "
  "This document is a synthetic example generated for software testing and "
  "does not describe a real trial.", SUB)

# ------------------------------------------------------------ section 1
p("1 Study Objectives", H1)
p("1.1 Primary Objective", H2)
p("To evaluate the effect of PHX-401 compared with placebo on the change from "
  "baseline in seated systolic blood pressure at Week 12.")
p("1.2 Secondary Objectives", H2)
p("To evaluate the change from baseline in seated diastolic blood pressure at "
  "Week 4 and Week 12, and to characterise the safety and tolerability of "
  "PHX-401 over 12 weeks of treatment.")

# ------------------------------------------------------------ section 2
p("2 Study Design", H1)
p("This is a multicentre, randomised, double-blind, placebo-controlled, "
  "parallel-group study. Approximately 120 subjects will be randomised 1:1 "
  "to PHX-401 10 mg once daily or matching placebo for 12 weeks. The study "
  "consists of a Screening period of up to 14 days, a 12-week double-blind "
  "Treatment period, and a safety follow-up contact.")

# ------------------------------------------------------------ section 5
p("5 Study Population", H1)
p("5.1 Inclusion Criteria", H2)
p("Subjects aged 18 to 75 years inclusive with a seated systolic blood "
  "pressure of 140 to 159 mmHg at Screening, who provide written informed "
  "consent.")

# ------------------------------------------------------------ section 6
p("6 Schedule of Activities", H1)
p("The assessments to be performed at each study visit are summarised in "
  "Table 6-1. Visit windows are +/- 3 days for Week 4 and Week 12.")

rows = [
    ["Assessment", "Screening\n(Day -14 to -1)", "Day 1\n(Baseline)", "Week 4", "Week 12", "Early\nTermination"],
    ["Informed consent", "X", "", "", "", ""],
    ["Demographics", "X", "", "", "", ""],
    ["Seated blood pressure", "X", "X", "X", "X", "X"],
    ["Body weight", "X", "X", "", "X", "X"],
    ["Height", "X", "", "", "", ""],
    ["12-lead ECG", "X", "", "", "X", "X"],
    ["Clinical laboratory tests", "X", "", "X", "X", "X"],
    ["Adverse event review", "", "X", "X", "X", "X"],
    ["Study drug dispensing", "", "X", "X", "", ""],
]
t = Table(rows, colWidths=[1.9 * inch, 1.05 * inch, 0.95 * inch, 0.8 * inch, 0.8 * inch, 0.95 * inch])
t.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
s.append(Spacer(1, 6))
s.append(t)
s.append(Spacer(1, 6))
p("Table 6-1. Schedule of Activities. X indicates the assessment is performed "
  "at that visit.", SUB)

s.append(PageBreak())

# ------------------------------------------------------------ section 7
p("7 Study Assessments and Procedures", H1)

p("7.1 Demographics", H2)
p("Date of birth and sex will be recorded at Screening. Age will be derived "
  "from date of birth at the time of informed consent.")

p("7.2 Body Measurements", H2)
p("Body weight will be recorded in kilograms to one decimal place at each "
  "visit where it is scheduled, with the subject in light indoor clothing and "
  "without shoes. Height will be measured in centimetres at Screening only.")

p("7.3 Vital Signs", H2)
p("7.3.1 General", H2)
p("Vital signs will be assessed at every study visit as indicated in the "
  "Schedule of Activities. All measurements must be recorded on the "
  "electronic case report form on the day they are taken.")

p("7.3.2 Blood Pressure Measurement", H2)
p("Seated systolic and diastolic blood pressure will be measured in triplicate "
  "using a calibrated automated device, after the subject has rested in the "
  "seated position for 5 minutes. The three readings will be taken at "
  "intervals of 1 to 2 minutes and each reading recorded individually. "
  "Systolic values outside 60 to 250 mmHg and diastolic values outside 30 to "
  "150 mmHg must be re-confirmed before the visit is closed. The position of "
  "the subject during measurement must be recorded as seated or supine.")

p("7.4 Electrocardiogram", H2)
p("A standard 12-lead ECG will be performed at Screening, Week 12 and Early "
  "Termination after the subject has rested supine for at least 5 minutes. "
  "The investigator will record whether the ECG was performed, the overall "
  "interpretation as normal, abnormal not clinically significant, or abnormal "
  "clinically significant, and the QTcF interval in milliseconds.")

p("7.5 Clinical Laboratory Tests", H2)
p("Blood samples for haematology and clinical chemistry will be collected at "
  "the visits specified in the Schedule of Activities. Fasting plasma glucose "
  "will be measured in mmol/L and HbA1c as a percentage. Samples should be "
  "collected after an overnight fast of at least 8 hours where feasible, and "
  "the date and time of collection recorded.")

p("7.6 Adverse Events", H2)
p("Adverse events will be collected from the time of first dose of study drug "
  "until the final study contact. For each adverse event the investigator "
  "will record the event term, the start date, and the severity graded as "
  "mild, moderate or severe.")

# ------------------------------------------------------------ section 9
p("9 Statistical Considerations", H1)
p("9.1 Primary Analysis", H2)
p("The primary endpoint is the change from baseline in seated systolic blood "
  "pressure at Week 12. Baseline is defined as the Day 1 pre-dose measurement. "
  "The mean of the triplicate readings at each visit will be used as the "
  "visit value. Subjects with no post-baseline measurement will be excluded "
  "from the primary analysis.")

s.append(PageBreak())

# ------------------------------------------------------------ appendix
p("Appendix B Blood Pressure Measurement Procedure", H1)
p("Site staff should ensure the subject is seated comfortably with back "
  "supported and feet flat on the floor. The subject should rest quietly for "
  "10 minutes before the first reading is taken. The arm should be supported "
  "at heart level. Use the same arm for all measurements throughout the study.")

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.9 * inch,
                        rightMargin=0.9 * inch, topMargin=0.9 * inch,
                        bottomMargin=0.9 * inch,
                        title="PHX-401-201 Clinical Study Protocol (synthetic)")
doc.build(s)
print(f"wrote {OUT}")
```

### `backend/data/recorded/PHX-401-201.json`

```json
{
  "_comment": "Recorded extraction for the bundled sample protocol. Used by ECRF_BACKEND=mock so the demo runs with no API key. Three things are planted: a FABRICATED Heart Rate field at Week 4 whose quote is not in the protocol (grounding check should delete it), a PARAPHRASED quote on Week 4 Diastolic ('five minutes' vs '5 minutes', should pass tier 2 as approximate), and a CONFLICTING flag on Week 4 Systolic (5 vs 10 minute rest).",
  "visits": ["Screening", "Day 1", "Week 4", "Week 12", "Early Termination"],
  "forms": {
    "Screening": {
      "visit": "Screening",
      "form": "Screening Assessments",
      "fields": [
        {"name": "Date of Birth", "type": "date", "required": true,
         "source": {"section": "7.1", "quote": "Date of birth and sex will be recorded at Screening"}, "issue": "none"},
        {"name": "Sex", "type": "choice", "required": true, "choices": ["Male", "Female"],
         "source": {"section": "7.1", "quote": "Date of birth and sex will be recorded at Screening"}, "issue": "none"},
        {"name": "Systolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 60, "max": 250,
         "source": {"section": "7.3.2", "quote": "Systolic values outside 60 to 250 mmHg and diastolic values outside 30 to 150 mmHg must be re-confirmed"}, "issue": "none"},
        {"name": "Diastolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 30, "max": 150,
         "source": {"section": "7.3.2", "quote": "diastolic values outside 30 to 150 mmHg must be re-confirmed before the visit is closed"}, "issue": "none"},
        {"name": "Position", "type": "choice", "required": true, "choices": ["Seated", "Supine"],
         "source": {"section": "7.3.2", "quote": "The position of the subject during measurement must be recorded as seated or supine"}, "issue": "none"},
        {"name": "Weight", "type": "decimal", "required": true, "unit": "kg",
         "source": {"section": "7.2", "quote": "Body weight will be recorded in kilograms to one decimal place"}, "issue": "none"},
        {"name": "Height", "type": "decimal", "required": true, "unit": "cm",
         "source": {"section": "7.2", "quote": "Height will be measured in centimetres at Screening only"}, "issue": "none"},
        {"name": "ECG Performed", "type": "boolean", "required": true,
         "source": {"section": "7.4", "quote": "The investigator will record whether the ECG was performed"}, "issue": "none"},
        {"name": "ECG Result", "type": "choice", "required": true, "choices": ["Normal", "Abnormal not clinically significant", "Abnormal clinically significant"],
         "source": {"section": "7.4", "quote": "the overall interpretation as normal, abnormal not clinically significant, or abnormal clinically significant"}, "issue": "none"},
        {"name": "QTcF Interval", "type": "integer", "required": true, "unit": "ms",
         "source": {"section": "7.4", "quote": "and the QTcF interval in milliseconds"}, "issue": "none"},
        {"name": "Fasting Plasma Glucose", "type": "decimal", "required": true, "unit": "mmol/L",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"},
        {"name": "HbA1c", "type": "decimal", "required": true, "unit": "%",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"}
      ]
    },
    "Day 1": {
      "visit": "Day 1",
      "form": "Baseline Assessments",
      "fields": [
        {"name": "Systolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 60, "max": 250,
         "source": {"section": "7.3.2", "quote": "Seated systolic and diastolic blood pressure will be measured in triplicate using a calibrated automated device"}, "issue": "none"},
        {"name": "Diastolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 30, "max": 150,
         "source": {"section": "7.3.2", "quote": "diastolic values outside 30 to 150 mmHg must be re-confirmed before the visit is closed"}, "issue": "none"},
        {"name": "Position", "type": "choice", "required": true, "choices": ["Seated", "Supine"],
         "source": {"section": "7.3.2", "quote": "The position of the subject during measurement must be recorded as seated or supine"}, "issue": "none"},
        {"name": "Weight", "type": "decimal", "required": true, "unit": "kg",
         "source": {"section": "7.2", "quote": "Body weight will be recorded in kilograms to one decimal place"}, "issue": "none"},
        {"name": "Adverse Event Term", "type": "text", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"},
        {"name": "AE Start Date", "type": "date", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"},
        {"name": "AE Severity", "type": "choice", "required": false, "choices": ["Mild", "Moderate", "Severe"],
         "source": {"section": "7.6", "quote": "the severity graded as mild, moderate or severe"}, "issue": "none"}
      ]
    },
    "Week 4": {
      "visit": "Week 4",
      "form": "Week 4 Assessments",
      "fields": [
        {"name": "Systolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 60, "max": 250,
         "source": {"section": "7.3.2", "quote": "after the subject has rested in the seated position for 5 minutes"},
         "issue": "conflicting",
         "issue_note": "Section 7.3.2 specifies a 5 minute rest before measurement; Appendix B specifies the subject should rest quietly for 10 minutes before the first reading. Reviewer must confirm which applies."},
        {"name": "Diastolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 30, "max": 150,
         "source": {"section": "7.3.2", "quote": "rested in the seated position for five minutes"}, "issue": "none"},
        {"name": "Position", "type": "choice", "required": true, "choices": ["Seated", "Supine"],
         "source": {"section": "7.3.2", "quote": "The position of the subject during measurement must be recorded as seated or supine"}, "issue": "none"},
        {"name": "Heart Rate", "type": "integer", "required": true, "unit": "bpm", "min": 40, "max": 200,
         "source": {"section": "7.3.1", "quote": "heart rate will be recorded at each visit alongside blood pressure"}, "issue": "none"},
        {"name": "Fasting Plasma Glucose", "type": "decimal", "required": true, "unit": "mmol/L",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"},
        {"name": "HbA1c", "type": "decimal", "required": true, "unit": "%",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"},
        {"name": "Adverse Event Term", "type": "text", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"},
        {"name": "AE Start Date", "type": "date", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"},
        {"name": "AE Severity", "type": "choice", "required": false, "choices": ["Mild", "Moderate", "Severe"],
         "source": {"section": "7.6", "quote": "the severity graded as mild, moderate or severe"}, "issue": "none"}
      ]
    },
    "Week 12": {
      "visit": "Week 12",
      "form": "Week 12 Assessments",
      "fields": [
        {"name": "Systolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 60, "max": 250,
         "source": {"section": "7.3.2", "quote": "Seated systolic and diastolic blood pressure will be measured in triplicate using a calibrated automated device"}, "issue": "none"},
        {"name": "Diastolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 30, "max": 150,
         "source": {"section": "7.3.2", "quote": "diastolic values outside 30 to 150 mmHg must be re-confirmed before the visit is closed"}, "issue": "none"},
        {"name": "Position", "type": "choice", "required": true, "choices": ["Seated", "Supine"],
         "source": {"section": "7.3.2", "quote": "The position of the subject during measurement must be recorded as seated or supine"}, "issue": "none"},
        {"name": "Weight", "type": "decimal", "required": true, "unit": "kg",
         "source": {"section": "7.2", "quote": "Body weight will be recorded in kilograms to one decimal place"}, "issue": "none"},
        {"name": "ECG Performed", "type": "boolean", "required": true,
         "source": {"section": "7.4", "quote": "The investigator will record whether the ECG was performed"}, "issue": "none"},
        {"name": "ECG Result", "type": "choice", "required": true, "choices": ["Normal", "Abnormal not clinically significant", "Abnormal clinically significant"],
         "source": {"section": "7.4", "quote": "the overall interpretation as normal, abnormal not clinically significant, or abnormal clinically significant"}, "issue": "none"},
        {"name": "QTcF Interval", "type": "integer", "required": true, "unit": "ms",
         "source": {"section": "7.4", "quote": "and the QTcF interval in milliseconds"}, "issue": "none"},
        {"name": "Fasting Plasma Glucose", "type": "decimal", "required": true, "unit": "mmol/L",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"},
        {"name": "HbA1c", "type": "decimal", "required": true, "unit": "%",
         "source": {"section": "7.5", "quote": "Fasting plasma glucose will be measured in mmol/L and HbA1c as a percentage"}, "issue": "none"},
        {"name": "Adverse Event Term", "type": "text", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"},
        {"name": "AE Severity", "type": "choice", "required": false, "choices": ["Mild", "Moderate", "Severe"],
         "source": {"section": "7.6", "quote": "the severity graded as mild, moderate or severe"}, "issue": "none"}
      ]
    },
    "Early Termination": {
      "visit": "Early Termination",
      "form": "Early Termination Assessments",
      "fields": [
        {"name": "Systolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 60, "max": 250,
         "source": {"section": "7.3.2", "quote": "Seated systolic and diastolic blood pressure will be measured in triplicate using a calibrated automated device"}, "issue": "none"},
        {"name": "Diastolic Blood Pressure", "type": "integer", "required": true, "unit": "mmHg", "repeats": 3, "min": 30, "max": 150,
         "source": {"section": "7.3.2", "quote": "diastolic values outside 30 to 150 mmHg must be re-confirmed before the visit is closed"}, "issue": "none"},
        {"name": "Weight", "type": "decimal", "required": true, "unit": "kg",
         "source": {"section": "7.2", "quote": "Body weight will be recorded in kilograms to one decimal place"}, "issue": "none"},
        {"name": "ECG Performed", "type": "boolean", "required": true,
         "source": {"section": "7.4", "quote": "The investigator will record whether the ECG was performed"}, "issue": "none"},
        {"name": "QTcF Interval", "type": "integer", "required": true, "unit": "ms",
         "source": {"section": "7.4", "quote": "and the QTcF interval in milliseconds"}, "issue": "none"},
        {"name": "Adverse Event Term", "type": "text", "required": false,
         "source": {"section": "7.6", "quote": "the investigator will record the event term, the start date, and the severity"}, "issue": "none"}
      ]
    }
  }
}
```

### `backend/scripts/fetch_ctgov_protocol.py`

```python
"""Download a real, public protocol PDF from ClinicalTrials.gov.

Usage:
    python scripts/fetch_ctgov_protocol.py                 # search + pick first
    python scripts/fetch_ctgov_protocol.py NCT03391466     # a specific study
    python scripts/fetch_ctgov_protocol.py --cond diabetes --n 5   # list candidates

Protocol documents are public and these trials are completed, so there is
nothing confidential here. Saves to data/protocols/<NCT>_<filename>.

NOTE: written without network access, against the documented v2 API.
If the document URL shape has changed, the study page prints the link under
"Study Documents"; download it by hand into data/protocols/.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
CDN = "https://cdn.clinicaltrials.gov/large-docs"
OUT = Path(__file__).resolve().parent.parent / "data" / "protocols"


def search(cond: str, n: int) -> list[dict]:
    params = {
        "query.cond": cond,
        "filter.overallStatus": "COMPLETED",
        "query.term": "AREA[LargeDocHasProtocol]true",
        "fields": "NCTId,BriefTitle,LargeDocs",
        "pageSize": str(n),
        "format": "json",
    }
    url = API + "?" + urllib.parse.urlencode(params, safe="[]")
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r).get("studies", [])


def fetch_study(nct: str) -> dict:
    url = f"{API}/{nct}?fields=NCTId,BriefTitle,LargeDocs&format=json"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def protocol_docs(study: dict) -> list[dict]:
    docs = study.get("documentSection", {}).get("largeDocumentModule", {}).get("largeDocs", [])
    return [d for d in docs if d.get("hasProtocol")]


def download(nct: str, filename: str) -> Path:
    # CDN path uses the last two digits of the NCT number as a shard.
    shard = nct[-2:]
    url = f"{CDN}/{shard}/{nct}/{filename}"
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{nct}_{filename}"
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nct", nargs="?")
    ap.add_argument("--cond", default="hypertension")
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()

    if a.nct:
        studies = [fetch_study(a.nct)]
    else:
        studies = search(a.cond, a.n)

    if not studies:
        print("no studies found"); sys.exit(1)

    for s in studies:
        nct = s["protocolSection"]["identificationModule"]["nctId"]
        title = s["protocolSection"]["identificationModule"]["briefTitle"]
        docs = protocol_docs(s)
        print(f"{nct}  {title[:80]}")
        for d in docs:
            print(f"    {d.get('filename')}  {d.get('size', '?')} bytes")
        if a.n == 1 and docs:
            path = download(nct, docs[0]["filename"])
            print(f"saved to {path}")
            print("upload it through the UI, or: curl -F file=@" + str(path)
                  + " localhost:8000/api/protocols/upload")


if __name__ == "__main__":
    main()
```

### `backend/tests/test_pipeline.py`

```python
"""End to end against the mock backend. No network, no key, no GPU."""

import os

os.environ["ECRF_BACKEND"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from ecrf.api.app import app  # noqa: E402
from ecrf.ingest import load  # noqa: E402
from ecrf.verify import locate  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample", "PHX-401-201_protocol.pdf")


def test_ingest_finds_sections_and_tables():
    doc = load(SAMPLE)
    numbers = {s.number for s in doc.sections}
    assert "7.3.2" in numbers and "6" in numbers
    assert doc.tables, "schedule of activities table should be extracted"
    assert doc.tokens_estimate > 500


def test_exact_and_fuzzy_and_rejected():
    doc = load(SAMPLE)
    assert locate("Systolic values outside 60 to 250 mmHg", doc.text)[0] == "exact"
    v, score, _ = locate("rested in the seated position for five minutes", doc.text)
    assert v == "approximate" and score >= 90
    v, score, _ = locate("heart rate will be recorded at each visit alongside blood pressure", doc.text)
    assert score < 90


def test_full_flow():
    c = TestClient(app)
    with c:
        pid = c.post("/api/protocols/sample").json()["id"]
        summary = c.post(f"/api/protocols/{pid}/extract").json()["summary"]
        assert summary["rejected"] == 1 and summary["approximate"] == 1 and summary["flagged"] == 1

        draft = c.get(f"/api/protocols/{pid}/draft").json()["draft"]
        assert draft["rejections"][0]["name"] == "Heart Rate"
        w4 = next(f for f in draft["forms"] if f["visit"] == "Week 4")
        sys_bp = next(f for f in w4["fields"] if f["name"] == "Systolic Blood Pressure")
        assert sys_bp["issue"] == "conflicting" and sys_bp["cdash"] == "VSORRES_SYSBP"

        r = c.post(f"/api/protocols/{pid}/review", json={
            "changes": [{"visit": "Week 4", "name": "Systolic Blood Pressure",
                         "status": "approved", "max": 220}]})
        assert r.json()["version"] == 2

        r = c.post("/api/data/validate", json={
            "protocol_id": pid, "subject_id": "S1", "visit": "Week 4",
            "readings": [{"field_name": "Systolic Blood Pressure", "value": 1420}]})
        assert not r.json()["ok"]

        c.post(f"/api/data/seed/{pid}")
        dash = c.get(f"/api/dashboard/{pid}").json()
        assert all(s["pass"] for s in dash["stats"]), "app and independent results must agree"

        r = c.post(f"/api/dashboard/{pid}/unsupported?name=breakdown_by_age")
        assert r.status_code == 403
```


---

# Part B — Frontend

## B.1 Contract files (verbatim)

These fix the project shape, the API types and the design tokens. Create
them exactly.

### `frontend/package.json`

```json
{
  "name": "ecrf-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.6.3",
    "vite": "^5.4.11"
  }
}
```

### `frontend/vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
```

### `frontend/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "resolveJsonModule": true
  },
  "include": ["src"]
}
```

### `frontend/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>eCRF Builder</title>
    <link rel="icon" href="/logo.svg" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

### `frontend/public/logo.svg`

```xml
<!-- PLACEHOLDER. Replace this file with the Phoenix Clinical logo, keeping the filename logo.svg (or update Layout.tsx). -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40">
  <rect width="40" height="40" rx="8" fill="#16262E"/>
  <path d="M12 28 L20 10 L28 28 M15.5 21 H24.5" stroke="#E09A6F" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

### `frontend/src/styles/tokens.css`

```css
/* Design tokens. The only place colours, type and spacing are defined.
   Components reference these, never raw values. */

:root {
  /* palette */
  --ink: #16262e;
  --ink-2: #24404b;
  --paper: #f6f4ef;
  --card: #ffffff;
  --line: #d8d3c7;
  --line-strong: #b4b2a9;
  --muted: #4d5e66;
  --muted-2: #8a939a;

  --teal: #1f7a6b;
  --teal-bg: #d7ede8;
  --teal-ink: #0f3d35;

  --amber: #ba7517;
  --amber-bg: #faeeda;
  --amber-ink: #633806;

  --rust: #bf5632;
  --rust-bg: #f7e6dd;
  --rust-ink: #6b2e16;

  --accent: #e09a6f;

  /* type */
  --font-sans: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
  --text-xs: 12px;
  --text-sm: 13.5px;
  --text-md: 15px;
  --text-lg: 18px;
  --text-xl: 24px;
  --text-2xl: 32px;

  /* spacing */
  --s-1: 4px;
  --s-2: 8px;
  --s-3: 12px;
  --s-4: 16px;
  --s-5: 24px;
  --s-6: 32px;
  --s-7: 48px;

  --radius: 8px;
  --radius-lg: 12px;
  --sidebar: 232px;
}
```

### `frontend/src/api/types.ts`

```ts
/* Mirrors backend/ecrf/schema.py and the API responses. If the backend
   changes, change this file. Nothing else in the frontend declares shapes. */

export type FieldType = "integer" | "decimal" | "text" | "date" | "choice" | "boolean";
export type Issue = "none" | "missing" | "conflicting" | "ambiguous" | "unsupported";
export type Status = "draft" | "approved" | "flagged" | "rejected";
export type Verdict = "exact" | "approximate" | "rejected" | "unchecked";

export interface Source {
  section: string;
  quote: string;
}

export interface FieldDef {
  name: string;
  type: FieldType;
  required: boolean;
  unit: string | null;
  repeats: number;
  choices: string[] | null;
  min: number | null;
  max: number | null;
  source: Source;
  issue: Issue;
  issue_note: string | null;
  status: Status;
  verdict: Verdict;
  match_score: number | null;
  section_ok: boolean | null;
  cdash: string | null;
  domain: string | null;
}

export interface VisitForm {
  visit: string;
  form: string;
  fields: FieldDef[];
}

export interface Rejection {
  visit: string;
  name: string;
  quote: string;
  section: string;
  score: number;
  reason: string;
}

export interface Summary {
  visits: number;
  fields_generated: number;
  fields_kept: number;
  exact: number;
  approximate: number;
  rejected: number;
  flagged: number;
  threshold: number;
  seconds: number;
}

export interface DraftECRF {
  protocol_id: number;
  protocol_hash: string;
  version: number;
  backend: string;
  model: string;
  forms: VisitForm[];
  rejections: Rejection[];
  summary: Summary;
}

export interface LibrarySuggestion {
  domain: string;
  name: string;
  cdash: string;
  type: string | null;
  unit: string | null;
}

export interface ProtocolListItem {
  id: number;
  name: string;
  filename: string;
  pages: number;
  tokens_estimate: number;
  uploaded_by: string;
  uploaded_at: string;
  latest_version: number | null;
  summary: Summary | null;
}

export interface DraftResponse {
  protocol: { id: number; name: string; pages: number; tokens_estimate: number; hash: string };
  version: number | null;
  created_by?: string;
  created_at?: string;
  note?: string | null;
  draft: DraftECRF | null;
  library_suggestions?: Record<string, LibrarySuggestion[]>;
}

export interface VersionRow {
  version: number;
  created_by: string;
  created_at: string;
  note: string | null;
  summary: Summary | null;
}

export interface FieldChange {
  visit: string;
  name: string;
  status?: Status;
  min?: number | null;
  max?: number | null;
  required?: boolean;
  repeats?: number;
}

export interface Reading {
  field_name: string;
  repeat_num: number;
  value: string | number | boolean | null;
}

export interface StatResult {
  name: string;
  label: string;
  unit: string;
  kind: "scalar" | "by_visit";
  app: number | Record<string, number>;
  independent: number | Record<string, number>;
  pass: boolean;
}

export interface DashboardResponse {
  protocol: { id: number; name: string };
  extraction: {
    version: number;
    summary: Summary;
    per_visit: { visit: string; fields: number; flagged: number; approved: number }[];
    rejections: number;
    backend: string;
    model: string;
  } | null;
  data: { subjects: number; readings: number };
  stats: StatResult[];
}

export interface Health {
  ok: boolean;
  version: string;
  backend: string;
  model: string;
  context_mode: string;
  quote_match_threshold: number;
}
```

### `frontend/src/api/client.ts`

```ts
/* The only file that knows URLs. Pages call these functions and nothing
   else. Vite proxies /api to the backend in dev. */

import type {
  DashboardResponse, DraftResponse, FieldChange, Health,
  ProtocolListItem, Reading, VersionRow,
} from "./types";

const USER = "demo-reviewer"; // stand-in for Phoenix auth

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "X-User": USER, ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init.headers || {}) },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = JSON.stringify((await r.json()).detail); } catch { /* ignore */ }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/api/health"),

  listProtocols: () => req<ProtocolListItem[]>("/api/protocols"),
  loadSample: () => req<{ id: number; name: string }>("/api/protocols/sample", { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return req<{ id: number; name: string; pages: number }>("/api/protocols/upload", { method: "POST", body: fd });
  },
  extract: (id: number) => req<{ version: number }>(`/api/protocols/${id}/extract`, { method: "POST" }),
  draft: (id: number) => req<DraftResponse>(`/api/protocols/${id}/draft`),
  versions: (id: number) => req<VersionRow[]>(`/api/protocols/${id}/versions`),
  section: (id: number, n: string) => req<{ number: string; title: string; page: number; text: string }>(`/api/protocols/${id}/section/${encodeURIComponent(n)}`),
  review: (id: number, changes: FieldChange[], note?: string, action: "save" | "approve_all_remaining" = "save") =>
    req<{ version: number; applied: number }>(`/api/protocols/${id}/review`, {
      method: "POST", body: JSON.stringify({ changes, note, action }),
    }),

  validate: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ ok: boolean; errors: Record<string, string> }>("/api/data/validate", {
      method: "POST", body: JSON.stringify({ protocol_id, subject_id, visit, readings }),
    }),
  enter: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ saved: number }>("/api/data/enter", {
      method: "POST", body: JSON.stringify({ protocol_id, subject_id, visit, readings }),
    }),
  seed: (id: number) => req<{ seeded: number; already: boolean }>(`/api/data/seed/${id}`, { method: "POST" }),

  dashboard: (id: number) => req<DashboardResponse>(`/api/dashboard/${id}`),
};
```


## B.2 Files to build from this spec

Build these with `react`, `react-dom`, `react-router-dom` only. Plain CSS.
Every colour, size and font comes from `tokens.css` via `var(--…)`. No
gradients, no box shadows, no icon packs, no emoji in the UI.

### Look and feel

The brief is "should not look AI generated". Concretely:

- Background `--paper`. Cards are `--card` with a `1px solid var(--line)`
  border and `--radius-lg`. No shadows anywhere.
- Left sidebar, `--sidebar` wide, background `--ink`, text `--paper`. Logo
  at top (`/logo.svg`, 28px, next to the word "eCRF Builder" in 500 weight),
  nav links below, and at the bottom a small mono pill showing the backend
  from `/api/health` (e.g. `mock · recorded` or `openai_compat · gpt-4o-mini`).
- Page titles `--text-2xl` weight 600 `--ink`. Section titles `--text-lg`
  weight 600. Body `--text-md` `--muted`. Codes, hashes, scores, CDASH ids
  and numbers in `--font-mono`.
- Buttons: primary is `--ink` background, `--paper` text; secondary is
  `--card` with a `--line-strong` border; danger is `--rust`. 8px radius,
  `--text-sm`, 500 weight, 8px 14px padding. No uppercase.
- Badges (`Badge.tsx`): small pill, `--text-xs`, 500 weight, mono. Variants
  map to token pairs:
  - `exact` → bg `--teal-bg`, text `--teal-ink`, label "exact"
  - `approximate` → bg `--amber-bg`, text `--amber-ink`, label "approximate"
  - `rejected` → bg `--rust-bg`, text `--rust-ink`, label "rejected"
  - `flagged` → bg `--amber-bg`, text `--amber-ink`
  - `approved` → bg `--teal-bg`, text `--teal-ink`
  - `draft` → bg `--paper`, text `--muted`, border `--line`
  - `pass` / `fail` → teal / rust pairs, labels "PASS" / "FAIL"
- Spacing from the `--s-*` scale only. Max content width 1100px, left
  aligned, 32px padding.

### `src/styles/global.css`

Imports `tokens.css`. Resets margin/box-sizing. Sets `body` font to
`--font-sans`, color `--ink`, background `--paper`. Defines the shared
classes used by pages: `.page`, `.page-title`, `.card`, `.btn`, `.btn-primary`,
`.btn-secondary`, `.btn-danger`, `.row` (flex, gap `--s-3`, align center),
`.grid-2`, `.grid-3`, `.mono`, `.muted`, `.input` (1px `--line` border,
`--radius`, `--s-2` `--s-3` padding, mono for numeric), `.tabs` and `.tab`
(underline style, active tab `--ink` 2px bottom border), `.error` (text
`--rust-ink`, `--text-sm`).

### `src/main.tsx`

Mounts `<App />` inside `BrowserRouter`. Imports `global.css`.

### `src/App.tsx`

Routes inside `<Layout>`:

| path | page |
| --- | --- |
| `/` | `Protocols` |
| `/review/:id` | `Review` |
| `/data/:id` | `DataEntry` |
| `/dashboard/:id` | `Dashboard` |

### `src/components/Layout.tsx`

Sidebar + `<main>`. Nav links: Protocols (`/`), and when a protocol id is
in the current URL, Review, Data entry, Dashboard for that id. Fetches
`api.health()` once on mount for the backend pill.

### `src/components/Badge.tsx`

`<Badge kind="exact" />` etc. per the variant table above. Optional
`children` override the label.

### `src/components/Stat.tsx`

A stat tile: label (`--text-xs` muted, sentence case), value (`--text-2xl`
mono 500), optional sub-line. Used in a `.grid-3`/`.grid-2` row.

### `src/components/charts/BarChart.tsx`

Props: `data: {label: string; value: number}[]`, `height?: number` (default
180), `color?: string` (default `var(--teal)`), `valueSuffix?: string`.
Hand-rolled SVG. Vertical bars, 1px baseline in `--line`, label under each
bar in `--text-xs`, value above each bar in mono `--text-xs`. Bar width
computed from count. No axis ticks beyond the baseline. `role="img"` with an
`aria-label` summarising the series.

### `src/components/charts/DonutChart.tsx`

Props: `slices: {label: string; value: number; color: string}[]`,
`size?: number` (default 160), `centerLabel?: string`. Hand-rolled SVG donut
using stroke-dasharray on circles, 18px stroke. Legend to the right: colour
square, label, value in mono. `role="img"` + `aria-label`. If total is 0
render a muted "no data" ring.

### `src/components/FieldCard.tsx`

Props: `field: FieldDef`, `onChange(change: Partial<FieldChange>)`,
`onShowSection(section: string)`.

Layout, top to bottom:

1. Header row: field name (`--text-md` 600), CDASH code in a mono muted
   pill if present, then `<Badge kind={field.status} />` right-aligned.
2. Meta row (mono, `--text-sm`, muted): `type` · `unit` · `min–max` (only if
   set) · `×repeats` (only if > 1) · `required`/`optional` · choices joined
   with " / " if present.
3. Quote block: background `--paper`, left border 3px in the verdict colour
   (teal exact, amber approximate, rust rejected). Inside: the quote in
   italic `--text-sm`, then a row with `§{section}` as a button-link that
   calls `onShowSection`, `<Badge kind={field.verdict} />`, the score in
   mono (`{match_score}%`), and if `section_ok === false` a small rust
   "section mismatch" text.
4. If `field.issue !== "none"`: an amber banner with the issue word in
   mono 500 and `issue_note` as body.
5. Controls row: two small numeric inputs for min and max (prefilled,
   `onChange` on blur), and three buttons: Approve (teal), Flag (secondary),
   Reject (danger). Clicking sets status via `onChange({status})`.

### `src/pages/Protocols.tsx`

- Title "Protocols".
- A card with two actions side by side: **Load sample protocol** (calls
  `api.loadSample`) and a file input styled as a dashed drop area
  ("Upload a protocol PDF") calling `api.upload`. Below it one muted line:
  "Public protocols: run `backend/scripts/fetch_ctgov_protocol.py`".
- List of protocols from `api.listProtocols()`, each a card: name (600),
  mono line `{pages} pages · ~{tokens_estimate} tokens · by {uploaded_by}`,
  and on the right either an **Extract** primary button (if
  `latest_version` is null) or a row of summary chips (`{fields_kept} kept`
  teal, `{rejected} rejected` rust, `{flagged} flagged` amber, `v{n}`) and
  links to Review / Data entry / Dashboard.
- Extract shows a spinner text "Extracting…" on the button and refreshes the
  list when done. Errors render in `.error` under the card.

### `src/pages/Review.tsx`

- Loads `api.draft(id)`. If `draft` is null, show a card saying "Not
  extracted yet" with an Extract button.
- Header: protocol name, then a mono muted line
  `v{version} · {backend} · {model} · hash {protocol.hash} · threshold {summary.threshold}`.
- Summary strip (`.grid-3` of `Stat`): "Fields kept" (`fields_kept`),
  "Dropped by verification" (`rejected`, value in rust if > 0),
  "Flagged for review" (`flagged`, amber if > 0).
- **Dropped by verification** panel, always visible when
  `rejections.length > 0`, rust-tinted card. One row per rejection: visit ·
  field name · the quote in italic · `§section` · score in mono · the
  reason. One line of body text above the rows: "These quotes were not
  found in the protocol. The fields were deleted before review. This is the
  grounding check working."
- Visit tabs (`.tabs`) over `draft.forms`. Under the active tab, a list of
  `FieldCard`s. Edits accumulate in local state keyed by `visit+name`.
- Collapsed panel per visit: "Library also defines…" listing
  `library_suggestions[visit]` as mono chips (`name · cdash`). One muted
  line: "Standard fields from the CDASH library not found in this protocol.
  Not grounded. Shown for reference only."
- Bottom bar (sticky): count of pending changes, **Save review** (calls
  `api.review(id, changes, note)` with a small note input), and
  **Approve all remaining** (calls with `action: "approve_all_remaining"`).
  After save, reload the draft and clear local changes.
- Section viewer: clicking `§7.3.2` opens a right-side panel (fixed, 420px,
  card background) showing `api.section(id, n)`: title, page, and the text
  in `--text-sm`. Close button.
- Version history: a small collapsible list from `api.versions(id)` at the
  bottom (`v{n} · {note} · {created_by} · {date}`).

### `src/pages/DataEntry.tsx`

- Loads `api.draft(id)`. Visit select (from forms), subject id text input
  (default `PHX-021`).
- For the chosen visit, render one input per field with status `approved`
  or `draft`, and for `repeats > 1` render that many inputs labelled
  "Reading 1/2/3". Input type by field type: number (with `min`/`max`
  attributes), date, select for choices, checkbox for boolean, text
  otherwise. Required fields marked with a rust asterisk.
- Client-side validation mirrors the backend rules (required, numeric,
  integer, min, max, choice) and shows `.error` text under the input as
  the user types. The **Save readings** button calls `api.validate` first
  and, if ok, `api.enter`. Server-side errors map back under the inputs.
- A secondary button **Seed 20 synthetic subjects** calls `api.seed(id)`
  and shows "{seeded} readings added" or "already seeded".
- A muted line at the top: "Synthetic data only. No real patient
  information is entered into this prototype."

### `src/pages/Dashboard.tsx`

- Loads `api.dashboard(id)`. If `extraction` is null show "Extract first".
- Row 1 (`.grid-3` of `Stat`): Subjects, Readings, Fields kept
  (`extraction.summary.fields_kept`).
- Row 2 (`.grid-2`):
  - Card "Verification outcome": `DonutChart` with slices exact (teal),
    approximate (amber), rejected (rust) from `extraction.summary`. Center
    label = total generated. Sub-line: "{rejected} fabricated field(s)
    deleted before review".
  - Card "Fields per visit": `BarChart` from `extraction.per_visit`
    (label=visit, value=fields).
- Row 3 (`.grid-2`):
  - Card "Subjects per visit": `BarChart` from the `subjects_per_visit`
    stat's `app` map (object → array in visit order Screening, Day 1,
    Week 4, Week 12).
  - Card "Independently verified": a table with one row per scalar stat
    (`kind === "scalar"`): label, `app` (mono, 1 decimal, with unit),
    `independent` (mono), and `<Badge kind={pass ? "pass" : "fail"} />`.
    Body line above: "Each figure is recomputed by a script that shares no
    code with the app. A number that only checks itself proves nothing."
- Row 4: a card "Unsupported analysis" with a text input prefilled
  `breakdown_by_age` and a button **Request**. It POSTs to
  `/api/dashboard/{id}/unsupported?name=…` and shows the 403 message
  verbatim in a rust-tinted block. Body line: "Anything not in the approved
  registry is refused, not approximated."
- If `data.readings === 0`, rows 3 and 4 show a muted prompt "Seed data on
  the Data entry page" instead of charts.


---

# Part C — Root files (verbatim)

### `README.md`

````markdown
# eCRF Builder — prototype

BU Spark! Fall 2026 · DS519 · Client: Phoenix Clinical

A clinical trial protocol goes in. Draft electronic case report forms come
out, every generated field carrying a verbatim protocol quote that the code
verifies before a human sees it. A reviewer approves, synthetic data is
entered through the approved forms, and a dashboard reports statistics that
have been independently recomputed.

```
./run.sh          # backend on :8000, frontend on :5173, no API key needed
./run.sh test     # backend tests
```

Then open http://localhost:5173, click **Load sample protocol**, then
**Extract**.

## What runs where

```
protocol.pdf
   │
   ▼
 1 INGEST        pdfplumber, pdffonts gate        backend/ecrf/ingest.py
   ▼
 2 EXTRACT       one call for visits,             backend/ecrf/extract/
                 one per visit, cached prefix     backend/ecrf/pipeline.py
   ▼
 3 VERIFY        quote search, exact then fuzzy   backend/ecrf/verify.py
                 not found → field deleted
   ▼
   CDASH         attach standard codes            backend/ecrf/cdash.py
   ▼
 4 REVIEW        approve, edit, append a version  backend/ecrf/api/protocols.py
   ▼
 5 DATA ENTRY    validated against approved defs  backend/ecrf/api/data.py
   ▼
 6 STATS         fixed registry, refuse the rest  backend/ecrf/stats/
                 independent recomputation        backend/verification/
   ▼
 dashboard                                        frontend/src/pages/Dashboard.tsx
```

## Model backends

The model is a config value. `ECRF_BACKEND=mock` replays a recorded run on
the bundled sample and needs nothing. `ECRF_BACKEND=openai_compat` talks to
any provider that speaks the OpenAI chat format: OpenAI, vLLM on SCC, Groq,
OpenRouter, Gemini. See `.env.example`.

## The sample protocol

`backend/data/sample/PHX-401-201_protocol.pdf` is synthetic. Two things are
planted so the safety checks visibly fire:

- Section 7.3.2 says 5 minutes of rest, Appendix B says 10. The model
  flags **conflicting** rather than picking.
- There is no heart rate requirement anywhere. The recorded extraction
  fabricates one, and the grounding check deletes it. You will see it in the
  **Dropped by verification** panel with a match score of 57.

For a real public protocol: `python backend/scripts/fetch_ctgov_protocol.py`.

## Layout

```
backend/
  ecrf/            the pipeline and API
  data/            cdash library, sample protocol, recorded fixture
  verification/    independent stats. Imports NOTHING from ecrf/.
  scripts/         fetch a ClinicalTrials.gov protocol
  tests/
frontend/
  src/api/         types.ts mirrors the backend schema; client.ts owns URLs
  src/styles/      tokens.css is the only place colours and type are defined
  src/components/  Layout, Badge, FieldCard, Stat, charts/
  src/pages/       Protocols, Review, DataEntry, Dashboard
  public/logo.svg  REPLACE with the Phoenix Clinical logo
```

## Rules that are not negotiable

- No real patient data. Synthetic or approved de-identified only.
- No Phoenix material to unapproved services.
- No generated form used without qualified approval.
- No unsupported analysis attempted. Refuse instead.
- `verification/` imports nothing from `ecrf/`.

## Credits

Architecture draft by the team's systems member informed the CDASH
mapping layer and the structured document representation.
````

### `run.sh`

```bash
#!/usr/bin/env bash
# One command to run the whole prototype.
#   ./run.sh            backend + frontend, mock backend
#   ./run.sh backend    backend only
#   ./run.sh test       backend tests
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || cp .env.example .env

# ---------- backend ----------
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev]"
[ -f data/sample/PHX-401-201_protocol.pdf ] || python data/sample/make_sample_protocol.py

if [ "${1:-}" = "test" ]; then
  rm -f ecrf.db
  python -m pytest -q
  exit 0
fi

uvicorn ecrf.api.app:app --port 8000 --reload &
BACK=$!
cd ..

if [ "${1:-}" = "backend" ]; then
  wait $BACK
  exit 0
fi

# ---------- frontend ----------
cd frontend
[ -d node_modules ] || npm install --silent
npm run dev -- --port 5173 &
FRONT=$!
cd ..

echo
echo "  backend   http://localhost:8000/docs"
echo "  frontend  http://localhost:5173"
echo
trap "kill $BACK $FRONT 2>/dev/null" EXIT
wait
```

### `.env.example`

```bash
# ------------------------------------------------------------------
# Extraction backend.  "mock" needs nothing and replays a recorded run on
# the bundled sample protocol.  "openai_compat" talks to any provider that
# speaks the OpenAI chat format: OpenAI, vLLM on SCC, Groq, OpenRouter,
# Gemini.  Pick one block below and uncomment it.
# ------------------------------------------------------------------
ECRF_BACKEND=mock

# --- OpenAI (Omar's key) --------------------------------------------
# ECRF_BACKEND=openai_compat
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_API_KEY=sk-...
# LLM_MODEL=gpt-4o-mini

# --- Groq, free tier, no card, OpenAI-compatible -------------------
# Sign up at console.groq.com. Limits are per-minute and per-day; our run
# is six calls so it fits easily.
# ECRF_BACKEND=openai_compat
# LLM_BASE_URL=https://api.groq.com/openai/v1
# LLM_API_KEY=gsk_...
# LLM_MODEL=llama-3.3-70b-versatile

# --- Gemini, free tier, no card ------------------------------------
# Key from aistudio.google.com. Uses Google's OpenAI-compatible endpoint.
# ECRF_BACKEND=openai_compat
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# LLM_API_KEY=AIza...
# LLM_MODEL=gemini-2.5-flash

# --- vLLM on SCC (self-hosted) -------------------------------------
# From an SCC GPU node:
#   qrsh -l gpus=1 -l gpu_memory=24G -pe omp 8
#   python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-32B-AWQ \
#          --enable-prefix-caching --max-model-len 32768 --port 8000
# Then ssh tunnel port 8000 to your laptop, or run the backend on the node.
# ECRF_BACKEND=openai_compat
# LLM_BASE_URL=http://localhost:8000/v1
# LLM_API_KEY=none
# LLM_MODEL=Qwen/Qwen3-32B-AWQ

LLM_TEMPERATURE=0

# full | sections | auto.  "sections" sends only relevant parts of the
# protocol, which is what makes a 24GB GPU enough.
ECRF_CONTEXT=auto
ECRF_CONTEXT_TOKEN_LIMIT=60000

# PLACEHOLDER. Tune against the answer key before trusting it.
QUOTE_MATCH_THRESHOLD=90

# SQLite by default. Postgres is a URL change.
# DATABASE_URL=postgresql+psycopg://ecrf:ecrf@localhost:5432/ecrf
```

### `.gitignore`

```
__pycache__/
*.py[cod]
.venv/
.env
.pytest_cache/
.ruff_cache/
*.egg-info/
backend/ecrf.db
backend/data/uploads/
backend/data/protocols/*.pdf
node_modules/
dist/
.DS_Store
```


---

# Part D — Verify

Run from the repo root and report the output.

```bash
chmod +x run.sh
./run.sh test
```

Expected: `3 passed`. Those tests assert the planted behaviours: exactly one
field rejected (Heart Rate), one approximate (Diastolic at Week 4, "five
minutes"), one flagged (Systolic at Week 4, conflicting), review creates
version 2, validation rejects 1420 against the reviewer's new max, and all
three statistics match the independent recomputation.

```bash
cd frontend && npm install && npm run build && cd ..
```

Expected: a clean `tsc` + `vite build`. Fix any TypeScript errors in files
from B.2 only.

```bash
./run.sh
```

Then open http://localhost:5173 and walk through: Load sample protocol →
Extract → Review (see the Dropped panel and the Week 4 conflict) → Save
review → Data entry (seed, then try entering 1420 for systolic) → Dashboard.

Print the final directory tree and stop.

---

# Part E — Tomorrow, when the key and SCC arrive

**OpenAI key from Omar.** In `.env`:

```bash
ECRF_BACKEND=openai_compat
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

Restart the backend. Upload a real protocol (`python backend/scripts/fetch_ctgov_protocol.py`
or any PDF) and extract. The mock only works on the bundled sample; the
real backend works on anything with a text layer.

**Free tier while waiting.** Groq and Gemini both have no-card free tiers
and OpenAI-compatible endpoints. The exact lines are in `.env.example`. Six
calls per protocol fits any free tier comfortably.

**vLLM on SCC.** Request a 24GB card now that we send sections, not whole
documents:

```bash
qrsh -l gpus=1 -l gpu_memory=24G -pe omp 8
pip install vllm
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-32B-AWQ \
    --enable-prefix-caching --max-model-len 32768 --port 8000
```

Then either run the backend on the same node, or tunnel:
`ssh -L 8000:localhost:8000 scc1.bu.edu`. Set `LLM_BASE_URL=http://localhost:8000/v1`,
`LLM_API_KEY=none`, `LLM_MODEL=Qwen/Qwen3-32B-AWQ`, `ECRF_CONTEXT=sections`.

**Comparing the two.** Run the same protocol through both backends. The
`summary` on each version row records backend, model, kept/rejected/flagged
counts and seconds. That is the comparison table for Omar.

**What is deliberately not here.** Answer-key scoring (needs a real eCRF
from Phoenix), the client's actual approved calculation list, Phoenix auth,
Postgres. All are config or data drops, not rewrites.
