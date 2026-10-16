# Test protocols

Two real, public clinical trial protocols for demonstrating the eCRF
Builder. Both are from completed trials on ClinicalTrials.gov, so there is
nothing confidential in either file.

Both were chosen to fit the **Groq free tier limit of 8,000 tokens per
minute**. Larger protocols (the typical industry protocol is 100 to 280
pages) need either the paid OpenAI key or the context changes described in
the project notes.

| | test_protocol1.pdf | test_protocol2.pdf |
| --- | --- | --- |
| Study | NCT03541174 | NCT02664558 |
| Title | Aprocitentan in resistant hypertension | Ubenimex in pulmonary arterial hypertension |
| Phase | 3 | 2 |
| Sponsor | Industry | Industry |
| Pages | 11 | 6 |
| Estimated tokens | 5,143 | 2,351 |
| Sections found | 32 | 31 |

## What the pipeline produced from them

Run on 15 October 2026 with Groq, model `openai/gpt-oss-120b`.

| | test_protocol1 | test_protocol2 |
| --- | --- | --- |
| Visits found | 8 | 4 |
| Fields generated | 32 | 38 |
| Fields kept after verification | 32 | 38 |
| Quotes matched exactly | 28 | 36 |
| Quotes matched approximately | 4 | 2 |
| Fields deleted as ungrounded | 0 | 0 |
| Fields flagged for review | 4 | 24 |
| Run time | 322 s | 187 s |

Run time is dominated by waiting on the free tier, not by the work itself.

## Re-downloading these

    cd ecrf-prototype/backend
    python scripts/fetch_ctgov_protocol.py NCT03541174
    python scripts/fetch_ctgov_protocol.py NCT02664558

The script reports pages, whether the PDF has a text layer, and the token
estimate, which are the three things that decide whether a protocol can be
processed.

## Finding more

    python scripts/fetch_ctgov_protocol.py --rank 20 --phase PHASE3 --industry

Ranks protocol documents by file size. Size alone is misleading: the
largest file found during testing was 31 MB and turned out to be a scan
with no text layer, which the pipeline refuses. Always download a candidate
and read the pages / text layer / token lines before relying on it.
