/* The only file that knows URLs. Pages call these functions and nothing
   else. Vite proxies /api to the backend in dev. */

import type {
  DashboardResponse, DraftResponse, FieldChange, Health,
  ProtocolListItem, Reading, VersionRow,
} from "./types";

const USER = "demo-reviewer"; // stand-in for Phoenix auth

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "X-User": USER, ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init.headers || {}) },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = JSON.stringify((await r.json()).detail); } catch { /* ignore */ }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/api/health"),

  listProtocols: () => req<ProtocolListItem[]>("/api/protocols"),
  loadSample: () => req<{ id: number; name: string }>("/api/protocols/sample", { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return req<{ id: number; name: string; pages: number }>("/api/protocols/upload", { method: "POST", body: fd });
  },
  extract: (id: number) => req<{ version: number }>(`/api/protocols/${id}/extract`, { method: "POST" }),
  draft: (id: number) => req<DraftResponse>(`/api/protocols/${id}/draft`),
  versions: (id: number) => req<VersionRow[]>(`/api/protocols/${id}/versions`),
  section: (id: number, n: string) => req<{ number: string; title: string; page: number; text: string }>(`/api/protocols/${id}/section/${encodeURIComponent(n)}`),
  review: (id: number, changes: FieldChange[], note?: string, action: "save" | "approve_all_remaining" = "save") =>
    req<{ version: number; applied: number }>(`/api/protocols/${id}/review`, {
      method: "POST", body: JSON.stringify({ changes, note, action }),
    }),

  validate: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ ok: boolean; errors: Record<string, string> }>("/api/data/validate", {
      method: "POST", body: JSON.stringify({ protocol_id, subject_id, visit, readings }),
    }),
  enter: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ saved: number }>("/api/data/enter", {
      method: "POST", body: JSON.stringify({ protocol_id, subject_id, visit, readings }),
    }),
  seed: (id: number) => req<{ seeded: number; already: boolean }>(`/api/data/seed/${id}`, { method: "POST" }),

  dashboard: (id: number) => req<DashboardResponse>(`/api/dashboard/${id}`),
};
