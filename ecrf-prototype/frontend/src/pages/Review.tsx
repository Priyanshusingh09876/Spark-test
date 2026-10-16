import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DraftResponse, FieldChange, FieldDef, VersionRow } from "../api/types";
import FieldCard from "../components/FieldCard";
import Stat from "../components/Stat";

type SectionView = { number: string; title: string; page: number; text: string };

const key = (visit: string, name: string) => `${visit}\u0000${name}`;

export default function Review() {
  const id = Number(useParams().id);
  const [resp, setResp] = useState<DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [changes, setChanges] = useState<Record<string, FieldChange>>({});
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [section, setSection] = useState<{ loading: boolean; data: SectionView | null; error: string | null } | null>(null);
  const [versions, setVersions] = useState<VersionRow[] | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.draft(id);
      setResp(r);
      setError(null);
      setActive((a) => (a && r.draft?.forms.some((f) => f.visit === a) ? a : r.draft?.forms[0]?.visit ?? null));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const loadVersions = async () => {
    try { setVersions(await api.versions(id)); }
    catch (e) { setError((e as Error).message); }
  };

  const extract = async () => {
    setExtracting(true); setError(null);
    try { await api.extract(id); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setExtracting(false); }
  };

  const onChange = (visit: string, name: string, change: Partial<FieldChange>) => {
    setChanges((prev) => {
      const k = key(visit, name);
      return { ...prev, [k]: { ...(prev[k] ?? { visit, name }), ...change } };
    });
  };

  const save = async (action: "save" | "approve_all_remaining") => {
    setSaving(true); setError(null);
    try {
      await api.review(id, Object.values(changes), note.trim() || undefined, action);
      setChanges({});
      setNote("");
      await load();
      if (versions) await loadVersions();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const showSection = async (n: string) => {
    setSection({ loading: true, data: null, error: null });
    try { setSection({ loading: false, data: await api.section(id, n), error: null }); }
    catch (e) { setSection({ loading: false, data: null, error: (e as Error).message }); }
  };

  const draft = resp?.draft ?? null;
  const form = useMemo(() => draft?.forms.find((f) => f.visit === active) ?? null, [draft, active]);
  const pending = Object.keys(changes).length;

  // Merge pending local edits into the field so the card reflects them.
  const merged = (f: FieldDef, visit: string): FieldDef => {
    const c = changes[key(visit, f.name)];
    if (!c) return f;
    return {
      ...f,
      status: c.status ?? f.status,
      min: c.min !== undefined ? c.min : f.min,
      max: c.max !== undefined ? c.max : f.max,
      required: c.required ?? f.required,
      repeats: c.repeats ?? f.repeats,
    };
  };

  if (!resp && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  if (resp && !draft) {
    return (
      <div className="page">
        <h1 className="page-title">{resp.protocol.name}</h1>
        <div className="card">
          <p className="strong">Not extracted yet</p>
          <p className="muted small mt-2">Run the extraction pipeline to produce a draft eCRF for review.</p>
          <button type="button" className="btn btn-primary mt-4" onClick={extract} disabled={extracting}>
            {extracting ? "Extracting…" : "Extract"}
          </button>
        </div>
        {error && <p className="error mt-3">{error}</p>}
      </div>
    );
  }

  if (!resp || !draft) {
    return <div className="page">{error && <p className="error">{error}</p>}</div>;
  }

  const s = draft.summary;
  const sugg = resp.library_suggestions ?? {};

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{resp.protocol.name}</h1>
        <div className="mono small muted">
          v{resp.version} · {draft.backend} · {draft.model} · hash {resp.protocol.hash} · threshold {s.threshold}
        </div>
      </div>

      <div className="grid-3">
        <Stat label="Fields kept" value={s.fields_kept} sub={`of ${s.fields_generated} generated across ${s.visits} visits`} />
        <Stat label="Dropped by verification" value={s.rejected} tone={s.rejected > 0 ? "rust" : "default"} sub="quote not found in protocol" />
        <Stat label="Flagged for review" value={s.flagged} tone={s.flagged > 0 ? "amber" : "default"} sub="model reported an issue" />
      </div>

      {draft.rejections.length > 0 && (
        <div className="card card-rust mt-4">
          <div className="section-title">Dropped by verification</div>
          <p className="small mb-3">
            These quotes were not found in the protocol. The fields were deleted before review.
            This is the grounding check working.
          </p>
          {draft.rejections.map((r, i) => (
            <div className="reject-row" key={i}>
              <div className="mono">{r.visit}</div>
              <div className="strong">{r.name}</div>
              <div>
                <div className="italic">"{r.quote}"</div>
                <div className="row row-wrap mt-2 xs">
                  <span className="mono">§{r.section}</span>
                  <span className="mono">{r.score}%</span>
                  <span className="muted">{r.reason}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-5">
        <div className="tabs" role="tablist">
          {draft.forms.map((f) => (
            <button
              key={f.visit}
              type="button"
              role="tab"
              aria-selected={f.visit === active}
              className={`tab${f.visit === active ? " active" : ""}`}
              onClick={() => setActive(f.visit)}
            >
              {f.visit}<span className="tab-count">{f.fields.length}</span>
            </button>
          ))}
        </div>

        {form && (
          <>
            {form.fields.length === 0 && <p className="muted">No fields survived verification for this visit.</p>}
            {form.fields.map((f) => (
              <FieldCard
                key={`${form.visit}-${f.name}`}
                field={merged(f, form.visit)}
                onChange={(c) => onChange(form.visit, f.name, c)}
                onShowSection={showSection}
              />
            ))}

            <details className="panel mt-4">
              <summary>Library also defines… <span className="mono muted-2">{(sugg[form.visit] ?? []).length}</span></summary>
              <div className="panel-body">
                <p className="muted small mb-3">
                  Standard fields from the CDASH library not found in this protocol. Not grounded. Shown for reference only.
                </p>
                <div className="row row-wrap">
                  {(sugg[form.visit] ?? []).map((x) => (
                    <span className="pill" key={x.cdash}>{x.name} · {x.cdash}</span>
                  ))}
                  {(sugg[form.visit] ?? []).length === 0 && <span className="muted small">Nothing further.</span>}
                </div>
              </div>
            </details>
          </>
        )}
      </div>

      <details className="panel mt-4" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && !versions) loadVersions(); }}>
        <summary>Version history</summary>
        <div className="panel-body">
          {!versions && <p className="muted small">Loading…</p>}
          {versions && versions.map((v) => (
            <div className="mono small row row-wrap" key={v.version} style={{ padding: "var(--s-1) 0" }}>
              <span>v{v.version}</span>
              <span className="muted">·</span>
              <span>{v.note ?? "—"}</span>
              <span className="muted">·</span>
              <span>{v.created_by}</span>
              <span className="muted">·</span>
              <span className="muted">{new Date(v.created_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </details>

      {error && <p className="error mt-3">{error}</p>}

      <div className="sticky-bar">
        <span className="small muted">
          <span className="mono">{pending}</span> pending change{pending === 1 ? "" : "s"}
        </span>
        <input
          className="input grow"
          placeholder="Review note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button type="button" className="btn btn-primary" onClick={() => save("save")} disabled={saving || pending === 0}>
          {saving ? "Saving…" : "Save review"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => save("approve_all_remaining")} disabled={saving}>
          Approve all remaining
        </button>
      </div>

      {section && (
        <aside className="side-panel" aria-label="Protocol section">
          <div className="row row-between mb-3">
            <div className="section-title" style={{ marginBottom: 0 }}>
              {section.data ? `§${section.data.number} ${section.data.title}` : "Section"}
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSection(null)}>Close</button>
          </div>
          {section.loading && <p className="muted small">Loading…</p>}
          {section.error && <p className="error">{section.error}</p>}
          {section.data && (
            <>
              <div className="mono xs muted mb-3">page {section.data.page}</div>
              <pre>{section.data.text}</pre>
            </>
          )}
        </aside>
      )}
    </div>
  );
}
