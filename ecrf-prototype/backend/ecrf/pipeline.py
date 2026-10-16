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
