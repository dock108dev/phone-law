import type { ReactNode } from "react";

import { loadWebConfiguration } from "./config";
import "./styles.css";

const services = [
  { name: "API", description: "Liveness, readiness, and migration checks" },
  { name: "Worker", description: "Process and database readiness" },
  { name: "Database", description: "PostgreSQL foundation migration" },
  { name: "Web", description: "Synthetic-only review shell" },
] as const;

function SyntheticBanner(): ReactNode {
  return (
    <div className="synthetic-banner" role="status" aria-label="Synthetic demo data">
      <span className="banner-dot" aria-hidden="true" />
      <strong>Synthetic demo data</strong>
      <span>No client calls, recordings, transcripts, or identities are loaded.</span>
    </div>
  );
}

function Header(): ReactNode {
  return (
    <header className="site-header">
      <a className="brand" href="/" aria-label="Colacci Law Call Review home">
        <span className="brand-mark" aria-hidden="true">CL</span>
        <span>
          <b>Colacci Law</b>
          <small>Call review foundation</small>
        </span>
      </a>
      <nav aria-label="Primary navigation">
        <a className="nav-link active" href="/">Overview</a>
        <a className="nav-link" href="/health">System health</a>
      </nav>
      <div className="profile-chip" aria-label="Environment profile">
        <span aria-hidden="true" /> Demo
      </div>
    </header>
  );
}

function Shell({ children }: { children: ReactNode }): ReactNode {
  return (
    <>
      <SyntheticBanner />
      <Header />
      <main>{children}</main>
      <footer>
        <span>Foundation v0.1.0</span>
        <span>Advisory workflow • Human review required</span>
      </footer>
    </>
  );
}

function Dashboard(): ReactNode {
  return (
    <Shell>
      <section className="hero">
        <div className="eyebrow">Slice 0 · Foundation ready</div>
        <h1>A safe starting point for call review.</h1>
        <p>
          The local services, database migration, and fail-closed configuration are in place.
          Call analysis has not been added.
        </p>
        <div className="hero-note">
          <span className="lock-icon" aria-hidden="true">⌁</span>
          <span>
            <strong>Real call processing is locked.</strong>
            <small>Demo mode uses placeholder adapters and rejects client data.</small>
          </span>
        </div>
      </section>

      <section className="summary-grid" aria-label="Foundation summary">
        <article className="summary-card primary-card">
          <div className="card-label">Environment</div>
          <div className="large-value">Demo</div>
          <p>Synthetic-only profile</p>
          <div className="card-rule" />
          <div className="status-line"><span className="status-dot" /> Safety guard active</div>
        </article>
        <article className="summary-card">
          <div className="card-label">Calls loaded</div>
          <div className="large-value">0</div>
          <p>No call content exists in Slice 0</p>
        </article>
        <article className="summary-card">
          <div className="card-label">External services</div>
          <div className="large-value">None</div>
          <p>No AI, Broadvoice, or cloud connection</p>
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">Local system</div>
            <h2>Foundation components</h2>
          </div>
          <a className="text-link" href="/health">View health details →</a>
        </div>
        <div className="service-list">
          {services.map((service) => (
            <div className="service-row" key={service.name}>
              <span className="service-icon" aria-hidden="true">✓</span>
              <span className="service-copy"><b>{service.name}</b><small>{service.description}</small></span>
              <span className="ready-pill">Ready</span>
            </div>
          ))}
        </div>
      </section>
    </Shell>
  );
}

function HealthPage(): ReactNode {
  return (
    <Shell>
      <section className="page-title">
        <div className="eyebrow">Operational status</div>
        <h1>System health</h1>
        <p>All checks are content-free and verify only service and database readiness.</p>
      </section>
      <section className="panel health-panel">
        <div className="service-list">
          {services.map((service) => (
            <div className="service-row" key={service.name}>
              <span className="service-icon" aria-hidden="true">✓</span>
              <span className="service-copy"><b>{service.name}</b><small>{service.description}</small></span>
              <span className="ready-pill">Healthy</span>
            </div>
          ))}
        </div>
      </section>
    </Shell>
  );
}

export function App({ path = window.location.pathname }: { path?: string }): ReactNode {
  loadWebConfiguration();
  return path === "/health" ? <HealthPage /> : <Dashboard />;
}
