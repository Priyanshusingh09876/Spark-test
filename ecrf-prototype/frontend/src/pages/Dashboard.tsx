import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DashboardResponse, StatResult } from "../api/types";
import Badge from "../components/Badge";
import Stat from "../components/Stat";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";

const VISIT_ORDER = ["Screening", "Day 1", "Week 4", "Week 12"];

function visitSeries(map: Record<string, number>): { label: string; value: number }[] {
  const keys = Object.keys(map);
  const ordered = [...VISIT_ORDER.filter((v) => v in map), ...keys.filter((k) => !VISIT_ORDER.includes(k)).sort()];
  return ordered.map((v) => ({ label: v, value: map[v] }));
}

function fmt(v: number | Record<string, number>, unit: string): string {
  if (typeof v !== "number") return JSON.stringify(v);
  if (Number.isNaN(v)) return "n/a";
  return `${v.toFixed(1)}${unit ? ` ${unit}` : ""}`;
}

export default function Dashboard() {
  const id = Number(useParams().id);
  const [d, setD] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setD(await api.dashboard(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // The "unsupported analysis" demo panel was removed from this page: it
  // asked the reviewer to type an analysis name purely to watch the server
  // refuse it, which read as a broken feature rather than a safeguard. The
  // safeguard itself is unchanged. The dashboard is still built from
  // registry.CALCULATIONS, there is still no free-text query anywhere, and
  // POST /api/dashboard/{id}/unsupported still returns 403.

  if (!d && !error) return <div className="page"><p className="muted">Loading…</p></div>;
  if (!d) return <div className="page"><p className="error">{error}</p></div>;

  if (!d.extraction) {
    return (
      <div className="page">
        <h1 className="page-title">{d.protocol.name}</h1>
        <div className="card">
          <p className="strong">Extract first</p>
          <p className="muted small mt-2">
            The dashboard reads the latest eCRF version. <Link className="inline" to={`/review/${id}`}>Go to Review</Link> to run extraction.
          </p>
        </div>
      </div>
    );
  }

  const ex = d.extraction;
  const s = ex.summary;
  const hasData = d.data.readings > 0;
  const perVisitStat = d.stats.find((x) => x.name === "subjects_per_visit");
  const perVisit = perVisitStat && typeof perVisitStat.app === "object" ? visitSeries(perVisitStat.app) : [];
  const scalars = d.stats.filter((x): x is StatResult => x.kind === "scalar");

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{d.protocol.name}</h1>
        <div className="mono small muted">v{ex.version} · {ex.backend} · {ex.model}</div>
      </div>

      <div className="grid-3">
        <Stat label="Subjects" value={d.data.subjects} sub="with at least one reading" />
        <Stat label="Readings" value={d.data.readings.toLocaleString()} sub="synthetic observations" />
        <Stat label="Fields kept" value={s.fields_kept} sub={`of ${s.fields_generated} generated`} />
      </div>

      <div className="grid-2 mt-4">
        <div className="card" style={{ marginTop: 0 }}>
          <div className="section-title">Verification outcome</div>
          <DonutChart
            slices={[
              { label: "exact", value: s.exact, color: "var(--teal)" },
              { label: "approximate", value: s.approximate, color: "var(--amber)" },
              { label: "rejected", value: s.rejected, color: "var(--rust)" },
            ]}
            centerLabel={String(s.fields_generated)}
          />
          <p className="muted small mt-3">
            {s.rejected} fabricated field{s.rejected === 1 ? "" : "s"} deleted before review
          </p>
        </div>
        <div className="card" style={{ marginTop: 0 }}>
          <div className="section-title">Fields per visit</div>
          <BarChart data={ex.per_visit.map((v) => ({ label: v.visit, value: v.fields }))} />
        </div>
      </div>

      <div className="grid-2 mt-4">
        <div className="card" style={{ marginTop: 0 }}>
          <div className="section-title">Subjects per visit</div>
          {hasData
            ? <BarChart data={perVisit} color="var(--ink-2)" />
            : <p className="muted small">Seed data on the <Link className="inline" to={`/data/${id}`}>Data entry</Link> page</p>}
        </div>
        <div className="card" style={{ marginTop: 0 }}>
          <div className="section-title">Independently verified</div>
          <p className="muted small mb-3">
            Each figure is recomputed by a script that shares no code with the app.
            A number that only checks itself proves nothing.
          </p>
          {hasData ? (
            <table className="table">
              <thead>
                <tr><th>Statistic</th><th className="num">App</th><th className="num">Independent</th><th /></tr>
              </thead>
              <tbody>
                {scalars.map((st) => (
                  <tr key={st.name}>
                    <td>{st.label}</td>
                    <td className="num">{fmt(st.app, st.unit)}</td>
                    <td className="num">{fmt(st.independent, st.unit)}</td>
                    <td><Badge kind={st.pass ? "pass" : "fail"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted small">Seed data on the <Link className="inline" to={`/data/${id}`}>Data entry</Link> page</p>
          )}
        </div>
      </div>

      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
