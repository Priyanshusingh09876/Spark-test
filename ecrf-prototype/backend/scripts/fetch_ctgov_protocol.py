"""Download a real, public protocol PDF from ClinicalTrials.gov.

Usage:
    python scripts/fetch_ctgov_protocol.py                  # search + pick first
    python scripts/fetch_ctgov_protocol.py NCT04576988      # a specific study
    python scripts/fetch_ctgov_protocol.py --cond diabetes --n 5   # list candidates
    python scripts/fetch_ctgov_protocol.py --rank 20        # rank by document size
    python scripts/fetch_ctgov_protocol.py --rank 20 --phase PHASE3 --industry

Protocol documents are public and these trials are completed, so there is
nothing confidential here. Saves to data/protocols/<NCT>_<filename>.

PICKING A REALISTIC PROTOCOL
----------------------------
File size is a poor guide. A 31 MB document is usually a SCAN with no text
layer, which ingest.py refuses; a 4 MB one can be 110 clean pages. So --rank
sorts by size only to produce candidates, and every download then reports
what actually matters:

    pages        110 is a typical industry phase 3 protocol
    text layer   no fonts means scanned, and the pipeline will refuse it
    ~tokens      compare against your provider's tokens-per-minute limit

That last number is the one that bites. Extraction pass one sends the WHOLE
protocol in a single request to list the visits, so a provider with an
8,000 TPM limit (Groq free tier) cannot process a protocol much over ~8,000
tokens, roughly 12 pages, however many pages it has.
"""

import argparse
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
CDN = "https://cdn.clinicaltrials.gov/large-docs"
OUT = Path(__file__).resolve().parent.parent / "data" / "protocols"

# NOTE: the API field is DocumentSection. An earlier version asked for
# "LargeDocs", which the API now rejects with HTTP 400.
FIELDS = "NCTId,BriefTitle,DocumentSection,Phase,LeadSponsorClass"


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params, safe="[]")
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def search(cond: str, n: int, phase: str | None = None,
           token: str | None = None) -> dict:
    params = {
        "query.cond": cond,
        "filter.overallStatus": "COMPLETED",
        "query.term": "AREA[LargeDocHasProtocol]true",
        "fields": FIELDS,
        "pageSize": str(n),
        "format": "json",
    }
    if phase:
        params["filter.advanced"] = f"AREA[Phase]{phase}"
    if token:
        params["pageToken"] = token
    return _get(params)


def fetch_study(nct: str) -> dict:
    """One study by its NCT id, via the single-study endpoint."""
    url = f"{API}/{nct}?" + urllib.parse.urlencode(
        {"fields": FIELDS, "format": "json"}, safe="[]")
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def protocol_docs(study: dict) -> list[dict]:
    docs = study.get("documentSection", {}).get("largeDocumentModule", {}).get("largeDocs", [])
    return [d for d in docs if d.get("hasProtocol")]


def _ident(study: dict) -> tuple[str, str, str]:
    ps = study.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("class", "?")
    return ident.get("nctId", "?"), ident.get("briefTitle", ""), str(sponsor)


def download(nct: str, filename: str) -> Path:
    # CDN path uses the last two digits of the NCT number as a shard.
    shard = nct[-2:]
    url = f"{CDN}/{shard}/{nct}/{filename}"
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{nct}_{filename}"
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def inspect(path: Path) -> None:
    """Report what decides whether this PDF is usable: pages, text layer, size."""
    pages = fonts = None
    if shutil.which("pdfinfo"):
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                pages = line.split()[1]
    if shutil.which("pdffonts"):
        out = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True).stdout
        fonts = max(0, len([ln for ln in out.splitlines() if ln.strip()]) - 2)

    print(f"  pages      {pages or '?'}")
    if fonts == 0:
        print("  text layer NONE - this is a scan. ingest.py will refuse it.")
        return
    print(f"  text layer {fonts if fonts is not None else '?'} fonts")

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from ecrf.ingest import load
        doc = load(str(path))
        print(f"  ~tokens    {doc.tokens_estimate:,}  "
              f"({len(doc.sections)} sections, {len(doc.tables)} tables)")
        if doc.tokens_estimate > 8000:
            print("  WARNING    pass one sends the whole protocol in one request;")
            print("             this exceeds an 8,000 TPM free tier (Groq).")
    except Exception as e:  # ingest is best-effort here
        print(f"  ~tokens    could not parse: {type(e).__name__}: {e}")


def rank(cond: str, top: int, phase: str | None, industry: bool, pages: int = 3) -> None:
    rows, token = [], None
    for _ in range(pages):
        data = search(cond, 200, phase, token)
        for s in data.get("studies", []):
            nct, title, sponsor = _ident(s)
            if industry and sponsor != "INDUSTRY":
                continue
            for d in protocol_docs(s):
                rows.append((d.get("size", 0), nct, d.get("filename", ""), title, sponsor))
        token = data.get("nextPageToken")
        if not token:
            break

    rows.sort(reverse=True)
    print(f"{len(rows)} protocol documents  cond={cond} phase={phase or 'any'}\n")
    print(f"{'MB':>6}  {'NCT':12} {'sponsor':9} {'filename':22} title")
    for size, nct, fn, title, sponsor in rows[:top]:
        print(f"{size / 1e6:6.1f}  {nct:12} {sponsor[:9]:9} {fn[:22]:22} {title[:52]}")
    print("\nSize is only a shortlist. Download one and read the pages / text")
    print("layer / token lines, which is what decides whether it is usable:")
    print("  python scripts/fetch_ctgov_protocol.py <NCT>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nct", nargs="?")
    ap.add_argument("--cond", default="hypertension")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--rank", type=int, metavar="N",
                    help="list the N largest protocol documents and exit")
    ap.add_argument("--phase", help="e.g. PHASE3")
    ap.add_argument("--industry", action="store_true",
                    help="industry-sponsored only; these look most like Phoenix's")
    a = ap.parse_args()

    if a.rank:
        rank(a.cond, a.rank, a.phase, a.industry)
        return

    if a.nct:
        studies = [fetch_study(a.nct)]
    else:
        studies = search(a.cond, a.n, a.phase).get("studies", [])

    if not studies:
        print("no studies found")
        sys.exit(1)

    for s in studies:
        nct, title, _ = _ident(s)
        docs = protocol_docs(s)
        print(f"{nct}  {title[:80]}")
        for d in docs:
            print(f"    {d.get('filename')}  {d.get('size', '?')} bytes")
        if (a.n == 1 or a.nct) and docs:
            path = download(nct, docs[0]["filename"])
            print(f"saved to {path}")
            inspect(path)
            print("\nupload it through the UI, or: curl -F file=@" + str(path)
                  + " localhost:8000/api/protocols/upload")


if __name__ == "__main__":
    main()
