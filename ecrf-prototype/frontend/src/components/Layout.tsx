import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { Health } from "../api/types";

const ID_IN_PATH = /^\/(review|data|dashboard)\/(\d+)/;

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  const m = pathname.match(ID_IN_PATH);
  const id = m ? m[2] : null;
  const pillState = health ? "" : healthError ? " offline" : " pending";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">
            <img src="/logo.png" alt="Phoenix Clinical Research" />
          </div>
          <div className="brand-name">eCRF Builder</div>
        </div>

        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Protocols</NavLink>
          {id && (
            <div className="nav-group">
              <div className="nav-group-label">protocol {id}</div>
              <NavLink to={`/review/${id}`}>Review</NavLink>
              <NavLink to={`/data/${id}`}>Data entry</NavLink>
              <NavLink to={`/dashboard/${id}`}>Dashboard</NavLink>
            </div>
          )}
        </nav>

        <div className="sidebar-foot">
          <span className={`backend-pill${pillState}`} title="Extraction backend">
            {health ? `${health.backend} · ${health.model}` : healthError ? "backend offline" : "connecting…"}
          </span>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
