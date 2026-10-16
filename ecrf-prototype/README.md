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
