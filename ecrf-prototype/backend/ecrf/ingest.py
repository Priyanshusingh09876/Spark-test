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
    "‘": "'", "’": "'", "“": '"', "”": '"',  # noqa: RUF001
    "–": "-", "—": "-", "−": "-", " ": " ",  # noqa: RUF001
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
