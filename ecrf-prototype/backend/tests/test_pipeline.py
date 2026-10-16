"""End to end against the mock backend. No network, no key, no GPU."""

import os

os.environ["ECRF_BACKEND"] = "mock"

from fastapi.testclient import TestClient

from ecrf.api.app import app
from ecrf.ingest import load
from ecrf.verify import locate

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
        assert sys_bp["issue"] == "conflicting" and sys_bp["cdash"] == "SYSBP"

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
