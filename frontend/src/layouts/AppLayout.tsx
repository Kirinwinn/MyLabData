import { NavLink, Outlet, useLocation } from "react-router";

import { GlobalJobStatus } from "../features/jobs/JobTrackingProvider";
import { MoleculeAttributeDirectory } from "../features/molecules/MoleculeAttributeDirectory";

const navigation = [
  { to: "/", label: "Overview", end: true },
  { to: "/molecules", label: "Molecules", end: false },
  { to: "/search", label: "Search", end: false },
  { to: "/catalog", label: "Catalog", end: false },
  { to: "/imports", label: "Import", end: false },
  { to: "/activity", label: "Activity", end: false },
] as const;

const routeTitles: Record<string, { eyebrow: string; title: string }> = {
  "/": { eyebrow: "Workspace overview", title: "Workspace Overview" },
  "/molecules": { eyebrow: "Molecule registry", title: "Molecule Registry" },
  "/search": { eyebrow: "Cross-filter query", title: "Molecule Search" },
  "/catalog": { eyebrow: "Attribute catalog", title: "Attribute Catalog" },
  "/drydata-demo": { eyebrow: "Interface prototype", title: "DryData Prototype" },
};

export function AppLayout() {
  const location = useLocation();
  const detailMatch = /^\/molecules\/(\d+)$/.exec(location.pathname);
  const detailMoleculeId = detailMatch ? Number(detailMatch[1]) : null;
  const heading =
    routeTitles[location.pathname] ??
    (location.pathname.startsWith("/molecules/")
      ? { eyebrow: "Molecule registry", title: "Molecule Detail" }
      : { eyebrow: "MyLabData", title: "Page" });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span>
            <strong>MyLabData</strong>
          </span>
        </div>

        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <NavLink
              className={({ isActive }) => `nav-item${isActive ? " nav-item--active" : ""}`}
              end={item.end}
              key={item.to}
              to={item.to}
            >
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {detailMoleculeId !== null ? (
          <MoleculeAttributeDirectory moleculeId={detailMoleculeId} />
        ) : null}

        <div className="sidebar__footer">
          <span className="sidebar__pulse" aria-hidden="true" />
          <span>
            <strong>Local workspace</strong>
            <small>API v1 · DuckDB</small>
          </span>
        </div>
      </aside>

      <div className="app-main">
        {location.pathname !== "/" &&
        !location.pathname.startsWith("/molecules") &&
        location.pathname !== "/search" &&
        location.pathname !== "/catalog" &&
        location.pathname !== "/imports" &&
        location.pathname !== "/activity" ? (
          <header className="topbar">
            <div>
              <p className="topbar__eyebrow">{heading.eyebrow}</p>
              <h1>{heading.title}</h1>
            </div>
            <div className="topbar__context" aria-label="Application context">
              <GlobalJobStatus />
            </div>
          </header>
        ) : null}
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
