"""Prompt assembly.

ORDER IS LOAD BEARING. Providers discount a repeated prefix by around 90%,
but only when it is byte-identical and at the very start. We send the same
protocol once per visit, so:

    [system instruction]   stable
    [protocol text]        stable, cached
    [visit list]           stable within a run
    [the question]         varies

Never put anything that changes per call above the protocol. A timestamp
or request id in the system instruction kills every cache hit silently.
"""

import json

from ecrf.schema import model_field_schema, model_visits_schema

SYSTEM = """\
You extract electronic case report form (eCRF) field definitions from
clinical trial protocols. You answer ONLY with a JSON object matching the
schema you are given. No prose, no markdown fences.

Rules:
1. Every field MUST carry source.quote: a verbatim fragment copied from the
   protocol, at least 20 characters, exactly as written. The quote will be
   searched for in the protocol text. A quote that is not found causes the
   field to be discarded, so copy precisely rather than paraphrasing.
2. source.section is the section number the quote came from, e.g. "7.3.2".
3. Never state a value the protocol does not give. If a range, unit or
   requirement is not stated, leave it null.
4. If the protocol is unclear, contradictory, or silent on something it
   should specify, keep the field but set issue to one of: missing,
   conflicting, ambiguous, unsupported, and explain in issue_note.
   Flagging beats guessing.
5. Use these standard field names where they apply: Systolic Blood
   Pressure, Diastolic Blood Pressure, Heart Rate, Temperature, Respiratory
   Rate, Position, Weight, Height, ECG Performed, ECG Result, QTcF Interval,
   HbA1c, Fasting Plasma Glucose, Adverse Event Term, AE Start Date,
   AE Severity, Date of Birth, Sex.
6. If a measurement is taken more than once at a visit (e.g. in triplicate),
   set repeats to that count.
"""


def visits_messages(protocol_text: str) -> list[dict]:
    schema = json.dumps(model_visits_schema())
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"PROTOCOL:\n\n{protocol_text}\n\n"
            "TASK: List the study visits in the order they occur, using the "
            "names the protocol uses (e.g. Screening, Day 1, Week 4). "
            f"Respond with JSON matching this schema:\n{schema}"
        )},
    ]


def fields_messages(protocol_text: str, visit: str, visits: list[str]) -> list[dict]:
    schema = json.dumps(model_field_schema())
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"PROTOCOL:\n\n{protocol_text}\n\n"
            f"STUDY VISITS: {', '.join(visits)}\n\n"
            f"TASK: List every data field that must be collected at the "
            f"\"{visit}\" visit only. Include validation ranges, units and "
            f"repeat counts only when the protocol states them. "
            f"Respond with JSON matching this schema:\n{schema}"
        )},
    ]
