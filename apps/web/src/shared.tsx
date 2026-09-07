import { type ReactNode } from "react";
import type { DemoPrincipal, Evidence } from "./types";

export const principals: { id: DemoPrincipal; label: string; role: string }[] = [
  { id: "demo-reviewer", label: "Demo reviewer", role: "Reviewer" },
  { id: "demo-admin", label: "Demo admin", role: "Administrator" },
  { id: "demo-operations", label: "Demo operations", role: "Operations" },
];

export const feedbackLabels = [
  "correct",
  "partially_correct",
  "incorrect",
  "unsupported",
  "not_applicable",
] as const;

export function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function provenanceValue(value: unknown): string {
  if (value === null || value === undefined) return "Not recorded";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${humanize(key)}: ${provenanceValue(nested)}`)
      .join(" · ");
  }
  return "Structured provenance available";
}

export function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes.toString()}:${remainder.toString().padStart(2, "0")}`;
}

export function currentPrincipal(): DemoPrincipal {
  if (typeof window === "undefined") return "demo-reviewer";
  const saved = window.localStorage.getItem("colacci-demo-principal");
  return principals.some((principal) => principal.id === saved)
    ? (saved as DemoPrincipal)
    : "demo-reviewer";
}

export function SyntheticBanner(): ReactNode {
  return (
    <div className="environment-indicator" role="status">
      <span className="banner-dot" aria-hidden="true" />
      <span>Synthetic demo</span>
    </div>
  );
}

export function briefingReturn(): string {
  if (typeof window === "undefined") return "/";
  if (window.location.pathname.startsWith("/briefing/")) return window.location.pathname + window.location.hash;
  return window.sessionStorage.getItem("colacci-briefing-return") ?? "/";
}

export function Header({
  principal,
  setPrincipal,
  path,
}: {
  principal: DemoPrincipal;
  setPrincipal: (principal: DemoPrincipal) => void;
  path: string;
}): ReactNode {
  const operatorArea = ["/operator", "/uploads", "/failures", "/playbooks", "/operations"].includes(path);
  return (
    <header className="site-header">
      <a className="brand" href="/" aria-label="Colacci Law Call Review home">
        <span className="brand-mark" aria-hidden="true">CL</span>
        <span><b>Colacci Law</b><small>Call review</small></span>
      </a>
      <nav aria-label="Primary navigation">
        <a className={`nav-link ${path === "/" || path.startsWith("/briefing/") ? "active" : ""}`} href={briefingReturn()}>Morning briefing</a>
        <a className="nav-link" href="/months/2026-07">Month history</a>
      </nav>
      <SyntheticBanner />
      {operatorArea && <div className="operator-access">
        <label className="identity-control"><span>Demo identity and role</span>
          <select aria-label="Demo identity and role" value={principal} onChange={(event) => {
            const next = event.target.value as DemoPrincipal;
            window.localStorage.setItem("colacci-demo-principal", next);
            setPrincipal(next);
          }}>{principals.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select>
        </label>
        <nav aria-label="Operator navigation">
          <a href="/uploads">Manual upload</a><a href="/failures">Failures</a>
          <a href="/playbooks">Playbook</a><a href="/operations">Operations</a>
        </nav>
      </div>}
    </header>
  );
}

export function Shell({
  children,
  principal,
  setPrincipal,
  path,
}: {
  children: ReactNode;
  principal: DemoPrincipal;
  setPrincipal: (principal: DemoPrincipal) => void;
  path: string;
}): ReactNode {
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <Header principal={principal} setPrincipal={setPrincipal} path={path} />
      <main id="main-content" tabIndex={-1}>{children}</main>
      <footer><a href="/operator">Operator access</a></footer>
    </>
  );
}

export function RequestState({
  loading,
  error,
  empty,
  area = "workspace",
}: {
  loading: boolean;
  error: string | null;
  empty?: string;
  area?: string;
}): ReactNode {
  if (loading) return <div className="state-panel" role="status"><span className="loading-mark" aria-hidden="true" /><b>Loading {area}</b><span>Retrieving local records.</span></div>;
  if (error) return <div className="state-panel error-state" role="alert"><b>The {area} could not be loaded.</b><span>{error}</span><button className="secondary-button" type="button" onClick={() => { window.location.reload(); }}>Reload {area}</button></div>;
  if (empty) return <div className="state-panel"><b>Nothing to review.</b><span>{empty}</span></div>;
  return null;
}

export function Metric({ label, value }: { label: string; value: number }): ReactNode {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

export function EvidenceLink({ callId, evidence }: { callId: string; evidence: Evidence }): ReactNode {
  return (
    <a className="evidence-link" href={`/calls/${callId}#${evidence.segment_id}`}>
      Evidence · {clock(evidence.start_seconds)} · {humanize(evidence.speaker)}
    </a>
  );
}

export function longDate(value: string): string {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "long", day: "numeric", year: "numeric" });
}

