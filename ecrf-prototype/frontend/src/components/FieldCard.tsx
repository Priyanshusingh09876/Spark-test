import { useEffect, useState } from "react";
import type { FieldChange, FieldDef } from "../api/types";
import Badge from "./Badge";

interface Props {
  field: FieldDef;
  onChange: (change: Partial<FieldChange>) => void;
  onShowSection: (section: string) => void;
}

function metaLine(f: FieldDef): string {
  const parts: string[] = [f.type];
  if (f.unit) parts.push(f.unit);
  if (f.min !== null || f.max !== null) parts.push(`${f.min ?? "…"}–${f.max ?? "…"}`);
  if (f.repeats > 1) parts.push(`×${f.repeats}`);
  parts.push(f.required ? "required" : "optional");
  if (f.choices && f.choices.length) parts.push(f.choices.join(" / "));
  return parts.join(" · ");
}

function numOrNull(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export default function FieldCard({ field, onChange, onShowSection }: Props) {
  const [min, setMin] = useState(field.min === null ? "" : String(field.min));
  const [max, setMax] = useState(field.max === null ? "" : String(field.max));

  // Resync when the draft is reloaded (e.g. after a save).
  useEffect(() => { setMin(field.min === null ? "" : String(field.min)); }, [field.min]);
  useEffect(() => { setMax(field.max === null ? "" : String(field.max)); }, [field.max]);

  const commitMin = () => {
    const v = numOrNull(min);
    if (v !== field.min) onChange({ min: v });
  };
  const commitMax = () => {
    const v = numOrNull(max);
    if (v !== field.max) onChange({ max: v });
  };

  return (
    <div className="field-card">
      <div className="field-head">
        <span className="field-name">{field.name}</span>
        {field.cdash && <span className="pill">{field.cdash}</span>}
        <span className="grow" />
        <Badge kind={field.status} />
      </div>
      <div className="field-meta">{metaLine(field)}</div>

      <div className={`quote quote-${field.verdict}`}>
        <div className="quote-text">"{field.source.quote}"</div>
        <div className="quote-row">
          <button type="button" className="btn-link" onClick={() => onShowSection(field.source.section)}>
            §{field.source.section}
          </button>
          <Badge kind={field.verdict} />
          <span className="mono small muted">{field.match_score ?? "–"}%</span>
          {/* field.section_ok is deliberately NOT shown. Section detection
              treats table-of-contents lines as sections and finds some
              section numbers twice, so the check reported a mismatch for
              roughly half of all fields on a long protocol, most of them
              wrongly. The backend still computes it; put it back on screen
              only once ingest.py stops mistaking contents lines for
              sections. */}
        </div>
      </div>

      {field.issue !== "none" && (
        <div className="issue-banner">
          <span className="issue-word">{field.issue}</span>
          <span>{field.issue_note}</span>
        </div>
      )}

      <div className="field-controls">
        <label className="ctl">
          min
          <input
            className="input input-sm input-mono"
            type="number"
            value={min}
            onChange={(e) => setMin(e.target.value)}
            onBlur={commitMin}
            aria-label={`${field.name} minimum`}
          />
        </label>
        <label className="ctl">
          max
          <input
            className="input input-sm input-mono"
            type="number"
            value={max}
            onChange={(e) => setMax(e.target.value)}
            onBlur={commitMax}
            aria-label={`${field.name} maximum`}
          />
        </label>
        <span className="grow" />
        <button type="button" className="btn btn-teal btn-sm" onClick={() => onChange({ status: "approved" })}>Approve</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange({ status: "flagged" })}>Flag</button>
        <button type="button" className="btn btn-danger btn-sm" onClick={() => onChange({ status: "rejected" })}>Reject</button>
      </div>
    </div>
  );
}
