# Notes for an AI coding agent

Read this before changing anything. `README.md` covers running the project;
this file covers the parts that are easy to break.

## What the project is

Protocol PDF in, draft electronic case report forms out. The whole design
assumes the language model will sometimes invent a plausible field, so the
model is never trusted on its word: it must quote the protocol for every
field it proposes, and separate code searches the document for that quote
and deletes the field if it is not found.

`BUILD.md` is the original specification the project was built from. It is
long but it explains why most things are the way they are. When something
looks odd, check there before changing it.

## Invariants

Breaking any of these breaks the point of the project.

1. **`backend/verification/` must never import from `ecrf/`.** It
   independently recomputes every statistic the app reports, and the
   dashboard shows both numbers side by side. A shared helper with a bug
   would produce the same wrong answer twice and the comparison would pass.
2. **The grounding check is code, not a model.** `ecrf/verify.py` searches
   the protocol text. Do not replace it with a model call.
3. **Approvals are append only.** `db.save_version` inserts a new row. It
   never updates one. That table is the audit trail.
4. **Statistics come from a fixed registry.** The dashboard is built from
   `stats/registry.py`. There is no free-text query path anywhere, and the
   absence of one is the enforcement. Adding a calculation means writing
   it, testing it, and adding an independent implementation in
   `verification/expected_results.py`.
5. **Normalisation happens once**, in `ingest.load`. Stage three compares
   model output against that exact string. A second, slightly different
   cleanup elsewhere is how the check silently stops working.
6. **No real patient data.** Everything is synthetic or approved
   de-identified.

## Things that have already bitten us

- **Running the tests wipes the dev database.** `run.sh test` deletes
  `backend/ecrf.db`. If uvicorn is running it keeps a handle on the deleted
  file and every later write fails with "attempt to write a readonly
  database", surfacing as a bare HTTP 500 on upload. Stop the server first,
  or point the tests at another `DATABASE_URL`.
- **Providers may count reserved output tokens against a per-minute
  limit.** A request whose prompt is only 5,500 tokens was billed as 8,228
  and rejected, because no `max_tokens` was set and the full default output
  allowance was reserved. If you see a 413 that the arithmetic does not
  explain, this is why.
- **`ECRF_CONTEXT=sections` depends on section bodies being present.**
  `_doc_from_protocol` in `api/protocols.py` slices each section body back
  out of the stored text. An earlier version left them empty, and section
  selection then either sent the model a bare heading or quietly fell back
  to the whole document. Both look like success from outside.
- **The mock extractor only recognises the bundled sample.** It checks for
  the marker `PHX-401-201` in the first 2000 characters of whatever context
  it is given. If you trim the context sent on pass one, that marker must
  survive the trim or the offline tests fail in a confusing way.
- **Pass one sends the whole protocol.** Section selection applies only to
  the per-visit calls. A 70,000 token protocol therefore fails immediately
  on a provider with a small per-request limit, however `ECRF_CONTEXT` is
  set. Trimming pass one to the schedule of activities plus the section
  headings is the main outstanding improvement.

## Known weaknesses, stated honestly

- The quote match threshold of 90 in `.env` is a placeholder. It has never
  been tuned against ground truth.
- The grounding check proves a quote exists, not that it justifies the
  field citing it. On one 76 page protocol, 325 fields cited 129 distinct
  quotes and one sentence was cited 18 times.
- Section detection in `ingest.split_sections` treats table-of-contents
  lines as sections and finds some section numbers twice, so the section
  cross-check reported a mismatch for roughly half the fields on a long
  protocol, most of them wrongly. It is computed but not displayed.
- Roughly half the generated fields come back flagged on a real protocol,
  almost always because the protocol states no unit or range. That is
  correct behaviour, but nothing groups them, so a reviewer faces a long
  undifferentiated list.
- Tested models did not flag a contradiction deliberately planted in the
  sample protocol, although the recorded fixture does. Do not claim
  contradiction detection works.

## Layout

```
ecrf-prototype/backend/ecrf/
  config.py     all runtime configuration, read from .env
  schema.py     one Pydantic definition drives both the model-facing
                JSON schema and the API validation, so they cannot drift
  ingest.py     stage 1, PDF to text, tables, numbered sections
  extract/      stage 2, the model adapter; base.py picks the backend
  verify.py     stage 3, the grounding check
  cdash.py      standard code enrichment, deterministic, never adds fields
  pipeline.py   orchestrates stages 1 to 3
  stats/        approved calculations and the registry
  api/          FastAPI routes
```

The frontend mirrors the backend schema in `src/api/types.ts`. If the
backend schema changes, change that file; nothing else in the frontend
declares shapes. `src/api/client.ts` is the only file that knows URLs.

## Conventions

- Backend is Python 3.11+, FastAPI, SQLAlchemy, SQLite by default.
  Postgres is a `DATABASE_URL` change.
- Frontend is React with TypeScript and plain CSS. No UI framework, no
  icon library, no chart library. Charts are hand-rolled SVG.
- All colours, sizes and fonts live in `src/styles/tokens.css`. Components
  reference tokens, never raw values.
- Run `./run.sh test` and `npm run build` before claiming anything works.
