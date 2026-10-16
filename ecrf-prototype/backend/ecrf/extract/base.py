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
