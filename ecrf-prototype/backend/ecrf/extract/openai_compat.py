"""One backend for every provider that speaks the OpenAI chat format.

    OpenAI       LLM_BASE_URL=https://api.openai.com/v1
    vLLM (SCC)   LLM_BASE_URL=http://localhost:8000/v1
    Groq         LLM_BASE_URL=https://api.groq.com/openai/v1
    OpenRouter   LLM_BASE_URL=https://openrouter.ai/api/v1
    Gemini       LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

JSON mode is requested where the provider supports it; the response is
validated with Pydantic either way, and one retry feeds the validation
error back. If the second attempt also fails, the error surfaces rather
than a silent empty result.
"""

import json
import re

from openai import OpenAI
from pydantic import ValidationError

from ecrf.extract import prompts
from ecrf.schema import VisitForm, VisitList

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class OpenAICompatExtractor:
    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.0):
        if not api_key and "localhost" not in base_url and "127.0.0.1" not in base_url:
            raise RuntimeError("LLM_API_KEY is not set")
        self.client = OpenAI(base_url=base_url, api_key=api_key or "none")
        self.model = model
        self.temperature = temperature

    # ---------------------------------------------------------- internals
    def _chat(self, messages: list[dict]) -> str:
        kwargs = dict(model=self.model, messages=messages, temperature=self.temperature)
        try:
            resp = self.client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs)
        except Exception:
            # Some compat servers reject response_format. Try without.
            resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _json(self, messages: list[dict], model_cls):
        raw = self._chat(messages)
        try:
            return model_cls.model_validate(json.loads(_FENCE.sub("", raw).strip()))
        except (json.JSONDecodeError, ValidationError) as e:
            retry = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"That response was invalid: {e}\n"
                    "Return ONLY a corrected JSON object matching the schema."
                )},
            ]
            raw2 = self._chat(retry)
            return model_cls.model_validate(json.loads(_FENCE.sub("", raw2).strip()))

    # ---------------------------------------------------------- interface
    def list_visits(self, protocol_text: str) -> VisitList:
        return self._json(prompts.visits_messages(protocol_text), VisitList)

    def fields_for_visit(self, protocol_text: str, visit: str, visits: list[str]) -> VisitForm:
        return self._json(prompts.fields_messages(protocol_text, visit, visits), VisitForm)
