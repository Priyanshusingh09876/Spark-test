/* Mirrors backend/ecrf/schema.py and the API responses. If the backend
   changes, change this file. Nothing else in the frontend declares shapes. */

export type FieldType = "integer" | "decimal" | "text" | "date" | "choice" | "boolean";
export type Issue = "none" | "missing" | "conflicting" | "ambiguous" | "unsupported";
export type Status = "draft" | "approved" | "flagged" | "rejected";
export type Verdict = "exact" | "approximate" | "rejected" | "unchecked";

export interface Source {
  section: string;
  quote: string;
}

export interface FieldDef {
  name: string;
  type: FieldType;
  required: boolean;
  unit: string | null;
  repeats: number;
  choices: string[] | null;
  min: number | null;
  max: number | null;
  source: Source;
  issue: Issue;
  issue_note: string | null;
  status: Status;
  verdict: Verdict;
  match_score: number | null;
  section_ok: boolean | null;
  cdash: string | null;
  domain: string | null;
}

export interface VisitForm {
  visit: string;
  form: string;
  fields: FieldDef[];
}

export interface Rejection {
  visit: string;
  name: string;
  quote: string;
  section: string;
  score: number;
  reason: string;
}

export interface Summary {
  visits: number;
  fields_generated: number;
  fields_kept: number;
  exact: number;
  approximate: number;
  rejected: number;
  flagged: number;
  threshold: number;
  seconds: number;
}

export interface DraftECRF {
  protocol_id: number;
  protocol_hash: string;
  version: number;
  backend: string;
  model: string;
  forms: VisitForm[];
  rejections: Rejection[];
  summary: Summary;
}

export interface LibrarySuggestion {
  domain: string;
  name: string;
  cdash: string;
  type: string | null;
  unit: string | null;
}

export interface ProtocolListItem {
  id: number;
  name: string;
  filename: string;
  pages: number;
  tokens_estimate: number;
  uploaded_by: string;
  uploaded_at: string;
  latest_version: number | null;
  summary: Summary | null;
}

export interface DraftResponse {
  protocol: { id: number; name: string; pages: number; tokens_estimate: number; hash: string };
  version: number | null;
  created_by?: string;
  created_at?: string;
  note?: string | null;
  draft: DraftECRF | null;
  library_suggestions?: Record<string, LibrarySuggestion[]>;
}

export interface VersionRow {
  version: number;
  created_by: string;
  created_at: string;
  note: string | null;
  summary: Summary | null;
}

export interface FieldChange {
  visit: string;
  name: string;
  status?: Status;
  min?: number | null;
  max?: number | null;
  required?: boolean;
  repeats?: number;
}

export interface Reading {
  field_name: string;
  repeat_num: number;
  value: string | number | boolean | null;
}

export interface StatResult {
  name: string;
  label: string;
  unit: string;
  kind: "scalar" | "by_visit";
  app: number | Record<string, number>;
  independent: number | Record<string, number>;
  pass: boolean;
}

export interface DashboardResponse {
  protocol: { id: number; name: string };
  extraction: {
    version: number;
    summary: Summary;
    per_visit: { visit: string; fields: number; flagged: number; approved: number }[];
    rejections: number;
    backend: string;
    model: string;
  } | null;
  data: { subjects: number; readings: number };
  stats: StatResult[];
}

export interface Health {
  ok: boolean;
  version: string;
  backend: string;
  model: string;
  context_mode: string;
  quote_match_threshold: number;
}
