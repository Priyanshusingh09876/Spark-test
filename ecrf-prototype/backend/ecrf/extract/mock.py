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
