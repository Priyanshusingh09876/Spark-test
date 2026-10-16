import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ProtocolListItem } from "../api/types";

export default function Protocols() {
  const [items, setItems] = useState<ProtocolListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);       // "sample" | "upload"
  const [extracting, setExtracting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await api.listProtocols());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loadSample = async () => {
    setBusy("sample"); setError(null);
    try { await api.loadSample(); await refresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy("upload"); setError(null);
    try { await api.upload(f); await refresh(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(null); if (fileRef.current) fileRef.current.value = ""; }
  };

  const extract = async (id: number) => {
    setExtracting(id); setError(null);
    try { await api.extract(id); await refresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setExtracting(null); }
  };

  return (
    <div className="page">
      <h1 className="page-title">Protocols</h1>

      <div className="card">
        <div className="row row-top">
          <button type="button" className="btn btn-primary" onClick={loadSample} disabled={busy !== null}>
            {busy === "sample" ? "Loading…" : "Load sample protocol"}
          </button>
          <label className="drop">
            <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={upload} disabled={busy !== null} />
            {busy === "upload" ? "Uploading…" : "Upload a protocol PDF"}
          </label>
        </div>
        <p className="muted small mt-3">
          Public protocols: run <span className="mono">backend/scripts/fetch_ctgov_protocol.py</span>
        </p>
      </div>
      {error && <p className="error mt-3">{error}</p>}

      <div className="mt-5 stack">
        {loading && <p className="muted">Loading…</p>}
        {!loading && items.length === 0 && (
          <div className="empty">No protocols yet. Load the sample or upload a PDF.</div>
        )}
        {items.map((p) => (
          <div className="card card-hover" key={p.id} style={{ marginTop: 0 }}>
            <div className="row row-between row-top">
              <div className="grow">
                <div className="strong">{p.name}</div>
                <div className="mono small muted mt-2">
                  {p.pages} pages · ~{p.tokens_estimate.toLocaleString()} tokens · by {p.uploaded_by}
                </div>
              </div>
              {p.latest_version === null ? (
                <button type="button" className="btn btn-primary" onClick={() => extract(p.id)} disabled={extracting !== null}>
                  {extracting === p.id ? "Extracting…" : "Extract"}
                </button>
              ) : (
                <div className="row row-wrap">
                  {p.summary && (
                    <>
                      <span className="pill chip-teal">{p.summary.fields_kept} kept</span>
                      <span className="pill chip-rust">{p.summary.rejected} rejected</span>
                      <span className="pill chip-amber">{p.summary.flagged} flagged</span>
                    </>
                  )}
                  <span className="pill">v{p.latest_version}</span>
                  <Link className="btn btn-secondary btn-sm" to={`/review/${p.id}`}>Review</Link>
                  <Link className="btn btn-secondary btn-sm" to={`/data/${p.id}`}>Data entry</Link>
                  <Link className="btn btn-secondary btn-sm" to={`/dashboard/${p.id}`}>Dashboard</Link>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
