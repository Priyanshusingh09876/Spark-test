"""Runtime configuration, read from the environment.

The extraction backend is a config value on purpose. Which LLM service is
approved is still an open question with the client, so nothing outside
ecrf/extract/ names a vendor.

Every provider we might use speaks the OpenAI chat-completions format
(OpenAI, vLLM, Groq, OpenRouter, Gemini's compat endpoint), so one backend
covers all of them and the difference is three env vars.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


@dataclass(frozen=True)
class Config:
    # "mock" replays a recorded fixture and needs no key. "openai_compat"
    # talks to whatever LLM_BASE_URL points at.
    backend: str

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float

    # "full" sends the whole protocol, "sections" sends only relevant
    # sections, "auto" picks by size.
    context_mode: str
    context_token_limit: int

    # Fuzzy match threshold for quote grounding. PLACEHOLDER until tuned
    # against the answer key. Single most consequential number here.
    quote_match_threshold: int

    database_url: str
    data_dir: Path


def load() -> Config:
    return Config(
        backend=os.getenv("ECRF_BACKEND", "mock"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        context_mode=os.getenv("ECRF_CONTEXT", "auto"),
        context_token_limit=int(os.getenv("ECRF_CONTEXT_TOKEN_LIMIT", "60000")),
        quote_match_threshold=int(os.getenv("QUOTE_MATCH_THRESHOLD", "90")),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'ecrf.db'}"),
        data_dir=Path(os.getenv("ECRF_DATA_DIR", ROOT / "data")),
    )


config = load()
