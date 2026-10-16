# Test protocols

Three real, public clinical trial protocols for demonstrating the eCRF
Builder. All are from completed trials on ClinicalTrials.gov, so there is
nothing confidential in any of them.

Protocols 1 and 2 are small enough to run on a free API tier. Protocol 3 is
a full-length industry protocol at 76 pages, which is the realistic size,
and needs a paid key: one run is about nine API calls and roughly a dollar
on gpt-5.1.

| | test_protocol1.pdf | test_protocol2.pdf | test_protocol3.pdf |
| --- | --- | --- | --- |
| Study | NCT03541174 | NCT02664558 | NCT02630316 |
| Title | Aprocitentan in resistant hypertension | Ubenimex in pulmonary arterial hypertension | Inhaled treprostinil in pulmonary hypertension |
| Phase | 3 | 2 | 3 |
| Sponsor | Industry | Industry | Industry |
| Pages | 11 | 6 | 76 |
| Estimated tokens | 5,143 | 2,351 | 35,870 |
| Sections found | 32 | 31 | 245 |
| File size | 292 KB | 192 KB | 16 MB |

## What the pipeline produced from them

Run on 15 October 2026 with Groq, model `openai/gpt-oss-120b`.

| | test_protocol1 | test_protocol2 | test_protocol3 |
| --- | --- | --- | --- |
| Visits found | 8 | 4 | 8 |
| Fields generated | 32 | 38 | 339 |
| Fields kept after verification | 32 | 38 | 325 |
| Quotes matched exactly | 28 | 36 | 261 |
| Quotes matched approximately | 4 | 2 | 64 |
| Fields deleted as ungrounded | 0 | 0 | 14 |
| Fields flagged for review | 4 | 24 | 172 |
| Run time | 322 s | 187 s | 554 s |

Protocols 1 and 2 ran on Groq, where the time is dominated by waiting on
the free tier rather than the work. Protocol 3 ran on gpt-5.1.

Protocol 3 is the interesting one. It is the only test where the grounding
check deleted anything: 14 fields whose quotes scored between 71 and 88,
below the threshold of 90. It also shows the review problem at scale, with
172 of 325 fields flagged because the protocol states no unit or range.

## Re-downloading these

    cd ecrf-prototype/backend
    python scripts/fetch_ctgov_protocol.py NCT03541174
    python scripts/fetch_ctgov_protocol.py NCT02664558
    python scripts/fetch_ctgov_protocol.py NCT02630316

The script reports pages, whether the PDF has a text layer, and the token
estimate, which are the three things that decide whether a protocol can be
processed.

## Finding more

    python scripts/fetch_ctgov_protocol.py --rank 20 --phase PHASE3 --industry

Ranks protocol documents by file size. Size alone is misleading: the
largest file found during testing was 31 MB and turned out to be a scan
with no text layer, which the pipeline refuses. Always download a candidate
and read the pages / text layer / token lines before relying on it.
