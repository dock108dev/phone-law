import {
  Fragment,
  type FormEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";

import { ApiRequestError, apiRequest } from "./api";
import { loadWebConfiguration } from "./config";
import type {
  CallDetail,
  AuditEvent,
  ConfigurationHistory,
  DailyReport,
  MonthHistory,
  DeletionJob,
  DemoPrincipal,
  Evidence,
  FailureItem,
  FailureQueue,
  Finding,
  LocalConfiguration,
  OperationsOverview,
  Playbook,
  PlaybookDraftCreate,
  UploadCapabilities,
  UploadReceipt,
} from "./types";

const principals: { id: DemoPrincipal; label: string; role: string }[] = [
  { id: "demo-reviewer", label: "Demo reviewer", role: "Reviewer" },
  { id: "demo-admin", label: "Demo admin", role: "Administrator" },
  { id: "demo-operations", label: "Demo operations", role: "Operations" },
];

const feedbackLabels = [
  "correct",
  "partially_correct",
  "incorrect",
  "unsupported",
  "not_applicable",
] as const;

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function provenanceValue(value: unknown): string {
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

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes.toString()}:${remainder.toString().padStart(2, "0")}`;
}

function currentPrincipal(): DemoPrincipal {
  if (typeof window === "undefined") return "demo-reviewer";
  const saved = window.localStorage.getItem("colacci-demo-principal");
  return principals.some((principal) => principal.id === saved)
    ? (saved as DemoPrincipal)
    : "demo-reviewer";
}

function SyntheticBanner(): ReactNode {
  return (
    <div className="environment-indicator" role="status">
      <span className="banner-dot" aria-hidden="true" />
      <span><strong>Local / synthetic</strong><small>No client data or live services</small></span>
    </div>
  );
}

function Header({
  principal,
  setPrincipal,
  path,
}: {
  principal: DemoPrincipal;
  setPrincipal: (principal: DemoPrincipal) => void;
  path: string;
}): ReactNode {
  const selectedRole = principals.find((item) => item.id === principal)?.role ?? "Reviewer";
  const workArea = path === "/uploads" ? "Manual upload" : path === "/failures" ? "Failure queue" : path === "/playbooks" ? "Playbook" : path === "/operations" ? "Operations" : path.startsWith("/calls/") ? "Call review" : path.startsWith("/reports/") ? "Daily report" : "Month history";
  const reportDate = path.match(/^\/reports\/(\d{4}-\d{2}-\d{2})$/)?.[1];
  return (
    <header className="site-header">
      <a className="brand" href="/" aria-label="Colacci Law Call Review home">
        <span className="brand-mark" aria-hidden="true">CL</span>
        <span><b>Colacci Law</b><small>{workArea}{reportDate ? ` · ${reportDate}` : ""}</small></span>
      </a>
      <nav aria-label="Primary navigation">
        <a className={`nav-link ${path === "/" || path.startsWith("/months/") || path.startsWith("/reports/") ? "active" : ""}`} href="/">Month history</a>
        <a className={`nav-link ${path === "/uploads" ? "active" : ""}`} href="/uploads">Manual upload</a>
        <a className={`nav-link ${path === "/failures" ? "active" : ""}`} href="/failures">Failures</a>
        <a className={`nav-link ${path === "/playbooks" ? "active" : ""}`} href="/playbooks">Playbook</a>
        <a className={`nav-link ${path === "/operations" ? "active" : ""}`} href="/operations">Operations</a>
      </nav>
      <SyntheticBanner />
      <label className="identity-control">
        <span>Current role</span>
        <select
          aria-label="Demo identity and role"
          value={principal}
          onChange={(event) => {
            const next = event.target.value as DemoPrincipal;
            window.localStorage.setItem("colacci-demo-principal", next);
            setPrincipal(next);
          }}
        >
          {principals.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
        </select>
        <small>{selectedRole}</small>
      </label>
    </header>
  );
}

function Shell({
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
    </>
  );
}

function RequestState({
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

function Metric({ label, value }: { label: string; value: number }): ReactNode {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function EvidenceLink({ callId, evidence }: { callId: string; evidence: Evidence }): ReactNode {
  return (
    <a className="evidence-link" href={`/calls/${callId}#${evidence.segment_id}`}>
      Evidence · {clock(evidence.start_seconds)} · {humanize(evidence.speaker)}
    </a>
  );
}

function MonthPage({ principal, monthKey = "2026-07" }: { principal: DemoPrincipal; monthKey?: string }): ReactNode {
  const [history, setHistory] = useState<MonthHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<MonthHistory>(`/api/reports/months/${monthKey}`, principal)
      .then((result) => { if (active) setHistory(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Unknown request error"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [monthKey, principal]);
  if (loading || error || !history) {
    return <RequestState loading={loading} error={error} area="month history" empty={!loading && !error ? "Run make seed-demo-month to create the month." : undefined} />;
  }
  const totals = history.days.reduce(
    (result, item) => ({
      expected: result.expected + item.expected,
      analyzed: result.analyzed + item.analyzed,
      failed: result.failed + item.failed,
      missing: result.missing + item.missing,
      late: result.late + item.late,
    }),
    { expected: 0, analyzed: 0, failed: 0, missing: 0, late: 0 },
  );
  const leadingBlanks = new Date(`${history.year.toString()}-${history.month.toString().padStart(2, "0")}-01T12:00:00Z`).getUTCDay();
  return (
    <>
      <section className="month-heading" aria-labelledby="month-title">
        <div><div className="eyebrow">Full-month synthetic call history</div><h1 id="month-title">{history.label}</h1><p>Every calendar date is visible. Open any day to inspect its complete eight-section report and evidence.</p></div>
        <nav className="month-controls" aria-label="Month controls">
          <a href={history.previous_month_path} aria-label="Previous month">← Previous</a>
          <a href={history.next_month_path} aria-label="Next month">Next →</a>
        </nav>
      </section>
      <section className="month-totals" aria-label="July monthly reconciliation">
        <Metric label="Expected" value={totals.expected} /><Metric label="Analyzed" value={totals.analyzed} /><Metric label="Failed" value={totals.failed} /><Metric label="Missing" value={totals.missing} /><Metric label="Late" value={totals.late} />
      </section>
      <div className="month-legend" aria-label="Date state legend">
        {["complete", "partial", "failed", "missing", "zero_activity"].map((state) => <span className={`day-state state-${state}`} key={state}>{humanize(state)}</span>)}
      </div>
      <section className="calendar" aria-label={`${history.label} daily report history`}>
        <div className="calendar-weekdays" aria-hidden="true">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <span key={day}>{day}</span>)}</div>
        <div className="calendar-grid">
          {Array.from({ length: leadingBlanks }, (_, index) => <span className="calendar-blank" key={`blank-${index.toString()}`} />)}
          {history.days.map((day) => (
            <a className={`calendar-day state-${day.state}`} href={day.report_path} key={day.business_date} aria-label={`${day.business_date}, ${humanize(day.state)}, expected ${day.expected.toString()}, analyzed ${day.analyzed.toString()}, failed ${day.failed.toString()}, missing ${day.missing.toString()}, late ${day.late.toString()}`}>
              <span className="calendar-date">{Number(day.business_date.slice(-2))}</span><span className="day-state">{humanize(day.state)}</span>
              {day.state === "zero_activity" ? <small>No eligible calls</small> : <><dl><dt>Expected</dt><dd>{day.expected}</dd><dt>Analyzed</dt><dd>{day.analyzed}</dd><dt>Failed</dt><dd>{day.failed}</dd><dt>Missing</dt><dd>{day.missing}</dd><dt>Late</dt><dd>{day.late}</dd></dl>{day.scenarios.some((scenario) => ["duplicate_delivery", "retryable_transcription_failure", "cancellation", "retention_eligibility", "successful_deletion", "retryable_deletion_failure", "terminal_deletion_failed"].includes(scenario)) && <small className="scenario-note">{day.scenarios.filter((scenario) => ["duplicate_delivery", "retryable_transcription_failure", "cancellation", "retention_eligibility", "successful_deletion", "retryable_deletion_failure", "terminal_deletion_failed"].includes(scenario)).map(humanize).join(" · ")}</small>}</>}
            </a>
          ))}
        </div>
      </section>
    </>
  );
}

function ReportPage({ principal, initialDate = "" }: { principal: DemoPrincipal; initialDate?: string }): ReactNode {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<{ dates: string[] }>("/api/reports/dates", principal)
      .then((result) => {
        if (!active) return;
        setDates(result.dates);
        setSelectedDate((current) => current || result.dates[0] || "");
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unknown request error");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [principal]);

  useEffect(() => {
    if (!selectedDate) return;
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<DailyReport>(`/api/reports/${selectedDate}`, principal)
      .then((value) => { if (active) setReport(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "The daily report request failed."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [principal, selectedDate]);

  if (loading || error || !report) {
    return <RequestState loading={loading} error={error} area="daily report" empty={!loading && !error ? "No report exists for this work date." : undefined} />;
  }
  const counts = report.completeness.reconciliation;
  return (
    <>
      {initialDate.startsWith("2026-07") && <a className="back-link" href="/months/2026-07">← Back to July 2026 month history</a>}
      <section className="report-hero" aria-labelledby="report-title">
        <div>
          <div className="eyebrow">Daily report</div>
          <h1 id="report-title">Call review · {report.business_date}</h1>
          <p>{report.advisory_notice}</p>
        </div>
        <label className="date-control">
          <span>Report date</span>
          <select value={selectedDate} onChange={(event) => { setSelectedDate(event.target.value); }}>
            {dates.map((date) => <option value={date} key={date}>{date}</option>)}
          </select>
        </label>
      </section>

      <section className={`completeness ${report.completeness.status}`} aria-labelledby="completeness-title">
        <div>
          <span className="status-badge">{humanize(report.completeness.status)} report</span>
          <h2 id="completeness-title">Coverage is {report.completeness.status === "zero_activity" ? "zero activity" : report.completeness.status}.</h2>
          <p>{report.completeness.explanation}</p>
          <small>Cutoff: 6:00 PM America/New_York · Duplicate deliveries excluded from call totals.</small>
        </div>
        <div className="metric-grid" aria-label="Report reconciliation counts">
          <Metric label="Expected" value={counts.expected} />
          <Metric label="Received" value={counts.received} />
          <Metric label="Analyzed" value={counts.analyzed} />
          <Metric label="Failed" value={counts.failed} />
          <Metric label="Missing" value={counts.missing} />
          <Metric label="Late" value={counts.late} />
        </div>
      </section>

      {counts.failed > 0 && (
        <aside className="warning-strip" aria-label="Processing failure warning">
          <b>{counts.failed} call did not produce a reviewable result.</b>
          <span>The report is not complete. Authorized roles can inspect the content-free failure queue.</span>
          <a href="/failures">Open failure queue</a>
        </aside>
      )}
      {report.late_calls.length > 0 && <div className="late-notice" role="status">Late recordings: {report.late_calls.length}</div>}

      <div className="report-sections">
        {report.sections.map((section, index) => (
          <section className={`report-section ${index === 0 ? "attention-section" : ""}`} key={section.kind} aria-labelledby={`section-${section.kind}`}>
            <div className="section-heading">
              <div>
                <h2 id={`section-${section.kind}`}>{section.title}</h2>
                <p>{section.description}</p>
              </div>
              <span className="count-badge" aria-label={`${section.items.length.toString()} items`}>{section.items.length}</span>
            </div>
            {section.items.length === 0 ? (
              <div className="empty-section">No synthetic calls in this section.</div>
            ) : (
              <div className="report-items">
                {section.items.map((item) => (
                  <article className="report-item" key={item.item_id}>
                    <div className="item-topline">
                      <a className="call-reference" href={item.analysis_id ? `/calls/${item.call_id}?month=${report.business_date.slice(0, 7)}` : "/failures"}>{item.synthetic_reference}</a>
                      <span className={`priority priority-${item.priority}`}>Priority: {humanize(item.priority)}</span>
                    </div>
                    <h3>{item.summary}</h3>
                    <dl className="item-meta">
                      {item.category && <><dt>Category</dt><dd>{humanize(item.category)}</dd></>}
                      {item.confidence && <><dt>Confidence</dt><dd>{humanize(item.confidence)}</dd></>}
                      {item.responsible_role && <><dt>Responsible role</dt><dd>{humanize(item.responsible_role)}</dd></>}
                      {item.suggested_timing && <><dt>Suggested timing</dt><dd>{item.suggested_timing}</dd></>}
                    </dl>
                    {item.failure && <div className="failure-summary">{item.failure.failed_stage} · {item.failure.diagnostic_code} · {item.failure.retryable ? "Retryable" : "Permanent"}</div>}
                    {item.evidence.length > 0 && <div className="evidence-list">{item.evidence.map((evidence) => <EvidenceLink callId={item.call_id} evidence={evidence} key={evidence.segment_id} />)}</div>}
                  </article>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

function EvidenceButton({ evidence, jump }: { evidence: Evidence; jump: (id: string) => void }): ReactNode {
  return <button className="evidence-link button-link" type="button" onClick={() => { jump(evidence.segment_id); }}>Jump to {clock(evidence.start_seconds)} · {humanize(evidence.speaker)}</button>;
}

function FindingFeedback({
  finding,
  detail,
  principal,
  jump,
  reload,
}: {
  finding: Finding;
  detail: CallDetail;
  principal: DemoPrincipal;
  jump: (id: string) => void;
  reload: () => Promise<void>;
}): ReactNode {
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const messageRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!message) return undefined;
    const focusMessage = window.setTimeout(() => {
      messageRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => { window.clearTimeout(focusMessage); };
  }, [message]);
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setMessage("");
    try {
      await apiRequest(`/api/analyses/${detail.analysis_id}/reviews`, principal, {
        method: "POST",
        body: JSON.stringify({ label, finding_id: finding.finding_id, note: note || null }),
      });
      setLabel("");
      setNote("");
      await reload();
      setMessage("Feedback saved as a new review event.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Feedback could not be saved.");
    }
  }
  return (
    <article className="finding-card">
      <div className="content-origin inference-origin">Fixture/model inference</div>
      <div className="item-topline"><span className="finding-kind">{humanize(finding.kind)}</span><span>{finding.material ? "Material finding" : "Supporting finding"}</span></div>
      <h3>{finding.statement}</h3>
      <div className="evidence-list">{finding.evidence.map((evidence) => <EvidenceButton evidence={evidence} jump={jump} key={evidence.segment_id} />)}</div>
      <form className="feedback-form" onSubmit={(event) => void submit(event)}>
        <fieldset>
          <legend>Record human feedback</legend>
          <div className="feedback-options">
            {feedbackLabels.map((value) => (
              <label key={value}>
                <input type="radio" name={`label-${finding.finding_id}`} value={value} checked={label === value} onChange={() => { setLabel(value); }} />
                <span>{humanize(value)}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="note-field"><span>Reviewer note <small>(optional)</small></span><textarea value={note} onChange={(event) => { setNote(event.target.value); }} rows={2} /></label>
        <button className="primary-button" disabled={!label} type="submit">Save feedback</button>
        <div aria-live="polite">
          {message ? <a className="form-message" ref={messageRef} href="#review-history-title" autoFocus>{message}</a> : <p className="form-message" />}
        </div>
      </form>
    </article>
  );
}

function MissingFeedback({ detail, principal, reload }: { detail: CallDetail; principal: DemoPrincipal; reload: () => Promise<void> }): ReactNode {
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const messageRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!message) return undefined;
    const focusMessage = window.setTimeout(() => {
      messageRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => { window.clearTimeout(focusMessage); };
  }, [message]);
  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    try {
      await apiRequest(`/api/analyses/${detail.analysis_id}/reviews`, principal, {
        method: "POST",
        body: JSON.stringify({ label: "missing", finding_id: null, note }),
      });
      setNote("");
      await reload();
      setMessage("Missing finding saved as a new review event.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Feedback could not be saved.");
    }
  }
  return (
    <form className="missing-form" onSubmit={(event) => void submit(event)}>
      <div className="content-origin human-origin">Human review</div>
      <h3>Add a missing finding</h3>
      <p>Record an omission without changing the original analysis or playbook.</p>
      <label className="note-field"><span>What is missing? <b>(required)</b></span><textarea required value={note} onChange={(event) => { setNote(event.target.value); }} rows={3} /></label>
      <button className="secondary-button" type="submit">Add missing finding</button>
      <div aria-live="polite">
        {message ? <a className="form-message" ref={messageRef} href="#review-history-title" autoFocus>{message}</a> : <p className="form-message" />}
      </div>
    </form>
  );
}

function CallPage({ callId, principal }: { callId: string; principal: DemoPrincipal }): ReactNode {
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState("");
  const handledInitialHash = useRef(false);

  async function load(): Promise<void> {
    setError(null);
    const result = await apiRequest<CallDetail>(`/api/calls/${callId}`, principal);
    setDetail(result);
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    apiRequest<CallDetail>(`/api/calls/${callId}`, principal)
      .then((result) => { if (active) setDetail(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Unknown request error"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [callId, principal]);

  function jump(segmentId: string): void {
    handledInitialHash.current = true;
    setHighlighted(segmentId);
    window.history.replaceState(null, "", `#${segmentId}`);
    window.setTimeout(() => {
      document.getElementById(segmentId)?.scrollIntoView({ block: "center", behavior: "smooth" });
      document.getElementById(segmentId)?.focus();
    }, 0);
  }
  useEffect(() => {
    if (detail && window.location.hash && !handledInitialHash.current) {
      handledInitialHash.current = true;
      jump(window.location.hash.slice(1));
    }
  }, [detail]);

  if (loading || error || !detail) return <RequestState loading={loading} error={error} area="call review" />;
  return (
    <>
      <a className="back-link" href={`/reports/${detail.occurred_at.slice(0, 10)}?month=${detail.occurred_at.slice(0, 7)}`}>← Back to daily report</a>
      <section className="call-heading">
        <div>
          <div className="eyebrow">Call review</div>
          <h1>{detail.synthetic_reference}</h1>
          <p>{detail.summary}</p>
        </div>
        <span className={`priority priority-${detail.priority}`}>Priority: {humanize(detail.priority)}</span>
      </section>
      <aside className="advisory-notice"><b>Human review required.</b> This is synthetic advisory output. It does not create a task, deadline, communication, or legal conclusion.</aside>

      <section className="metadata-grid" aria-label="Synthetic call metadata">
        <div className="metadata"><span>Direction</span><strong>{humanize(detail.direction)}</strong></div>
        <div className="metadata"><span>Time</span><strong>{new Date(detail.occurred_at).toLocaleString()}</strong></div>
        <div className="metadata"><span>Duration</span><strong>{clock(detail.duration_seconds)}</strong></div>
        <div className="metadata"><span>Language</span><strong>{detail.language === "es" ? "Spanish" : "English"}</strong></div>
        <div className="metadata"><span>Staff extension</span><strong>{detail.staff_extension ?? "Unknown"}</strong></div>
        <div className="metadata"><span>Caller identity</span><strong>{humanize(detail.identity_state)}{detail.identity_label ? ` · ${detail.identity_label}` : ""}</strong></div>
      </section>

      <div className="analysis-layout">
        <div className="analysis-main">
          <section className="detail-panel" aria-labelledby="findings-title">
            <div className="panel-title"><div><span className="content-origin inference-origin">Fixture/model inference</span><h2 id="findings-title">Structured findings</h2></div><span>{humanize(detail.confidence)} confidence</span></div>
            {detail.uncertainty.length > 0 && <div className="uncertainty"><b>Uncertainty remains</b><ul>{detail.uncertainty.map((item) => <li key={item}>{item}</li>)}</ul></div>}
            <div className="finding-list">
              {detail.findings.map((finding) => <FindingFeedback finding={finding} detail={detail} principal={principal} jump={jump} reload={load} key={finding.finding_id} />)}
              {detail.findings.length === 0 && <div className="empty-section">No original finding was produced. Use the missing-finding control when needed.</div>}
            </div>
            <MissingFeedback detail={detail} principal={principal} reload={load} />
          </section>

          <section className="detail-panel" aria-labelledby="transcript-title">
            <div className="panel-title"><div><span className="content-origin fact-origin">Transcript fact</span><h2 id="transcript-title">Original-language transcript</h2></div><span>{detail.language.toUpperCase()}</span></div>
            <div className="transcript" lang={detail.language}>
              {detail.transcript_segments.map((segment) => (
                <article
                  className={`segment ${highlighted === segment.segment_id ? "highlighted" : ""}`}
                  id={segment.segment_id}
                  key={segment.segment_id}
                  tabIndex={-1}
                  aria-label={`${humanize(segment.speaker)} at ${clock(segment.start_seconds)}`}
                >
                  <div><span>{clock(segment.start_seconds)}</span><b>{humanize(segment.speaker)}</b></div>
                  <p>{segment.text}</p>
                  {highlighted === segment.segment_id && <span className="highlight-label">Evidence highlighted</span>}
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside className="analysis-side">
          <section className="side-card"><span className="content-origin fact-origin">Transcript fact</span><h2>Extracted facts</h2><dl><dt>Caller request</dt><dd>{detail.facts.caller_request.value ?? humanize(detail.facts.caller_request.state)}</dd>{detail.facts.reported_facts.map((fact, index) => <Fragment key={`${fact.value ?? "reported"}-${index.toString()}`}><dt>Reported fact</dt><dd>{fact.value ?? humanize(fact.state)}</dd></Fragment>)}{detail.facts.dates.map((fact, index) => <Fragment key={`${fact.expression ?? "date"}-${index.toString()}`}><dt>Date</dt><dd>{fact.expression ?? "Unknown"} · {humanize(fact.state)}{fact.is_deadline ? " · deadline" : ""}</dd></Fragment>)}</dl></section>
          <section className="side-card"><h2>Proposed next steps</h2><ol>{detail.proposed_next_steps.map((step) => <li key={step}>{step}</li>)}</ol><p><b>Role:</b> {humanize(detail.responsible_role)}</p><p><b>Timing:</b> {detail.suggested_response_timing ?? "Not specified"}</p></section>
          <section className="side-card"><h2>Processing attempts</h2><ol className="attempt-list">{detail.attempts.map((attempt) => <li key={attempt.attempt_id}><b>Attempt {attempt.attempt_number}</b><span>{attempt.state}</span>{attempt.diagnostic_code && <small>{attempt.diagnostic_code}</small>}</li>)}</ol></section>
          <section className="side-card provenance"><h2>Provenance</h2><dl>{Object.entries(detail.provenance).map(([key, value]) => <Fragment key={key}><dt>{humanize(key)}</dt><dd>{provenanceValue(value)}</dd></Fragment>)}</dl></section>
        </aside>
      </div>

      <section className="review-history" aria-labelledby="review-history-title">
        <div className="content-origin human-origin">Human review</div>
        <h2 id="review-history-title">Append-only review history</h2>
        {detail.review_history.length === 0 ? <p>No feedback recorded yet.</p> : <ol>{detail.review_history.map((event) => <li key={event.event_id}><b>{humanize(event.label)}</b><span>{event.finding_id ?? "Analysis-level missing finding"}</span>{event.note && <p>{event.note}</p>}<small>{event.principal.principal_id} · {new Date(event.created_at).toLocaleString()}</small></li>)}</ol>}
      </section>
    </>
  );
}

function FailureCard({ item, principal, reload }: { item: FailureItem; principal: DemoPrincipal; reload: () => Promise<void> }): ReactNode {
  const [message, setMessage] = useState("");
  async function retry(): Promise<void> {
    try {
      await apiRequest(`/api/failures/${item.call_id}/retry`, principal, { method: "POST" });
      setMessage("Retry completed.");
      await reload();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Retry could not be completed.");
    }
  }
  return <article className="failure-card"><div className="item-topline"><h3>{item.synthetic_reference}</h3><span className={item.resolved ? "resolved-badge" : "failure-badge"}>{item.resolved ? "Resolved" : "Current failure"}</span></div><dl className="failure-meta"><dt>Failed stage</dt><dd>{item.failed_stage}</dd><dt>Diagnostic code</dt><dd>{item.diagnostic_code}</dd><dt>First attempt</dt><dd>{new Date(item.first_attempt_at).toLocaleString()}</dd><dt>Latest attempt</dt><dd>{new Date(item.latest_attempt_at).toLocaleString()}</dd><dt>Attempts</dt><dd>{item.attempt_count}</dd><dt>Terminal state</dt><dd>{item.current_terminal_state}</dd></dl><ol className="attempt-list">{item.attempt_history.map((attempt) => <li key={attempt.attempt_id}><b>Attempt {attempt.attempt_number}</b><span>{attempt.state}</span>{attempt.diagnostic_code && <small>{attempt.diagnostic_code}</small>}</li>)}</ol>{!item.resolved && <button type="button" className="secondary-button" disabled={!item.retryable} onClick={() => void retry()}>{item.retryable ? "Retry synthetic processing" : "Permanent failure · Retry unavailable"}</button>}<p className="form-message" aria-live="polite">{message}</p></article>;
}

function FailurePage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [queue, setQueue] = useState<FailureQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  async function load(): Promise<void> {
    const result = await apiRequest<FailureQueue>("/api/failures", principal);
    setQueue(result);
  }
  useEffect(() => {
    setLoading(true); setError(null);
    load().catch((reason: unknown) => { setError(reason instanceof Error ? reason.message : "Unknown request error"); }).finally(() => { setLoading(false); });
  }, [principal]);
  if (loading || error || !queue) return <RequestState loading={loading} error={error} area="failure queue" />;
  return <><section className="page-title"><div className="eyebrow">Content-free operations</div><h1>Synthetic failure queue</h1><p>Safe identifiers and diagnostics only. No transcript, summary, payload, URL, credential, or stack trace appears here.</p></section><section className="queue-section"><div className="section-heading"><h2>Current failures</h2><span className="count-badge">{queue.current.length}</span></div>{queue.current.map((item) => <FailureCard item={item} principal={principal} reload={load} key={item.call_id} />)}</section><section className="queue-section"><div className="section-heading"><h2>Resolved history</h2><span className="count-badge">{queue.resolved.length}</span></div>{queue.resolved.map((item) => <FailureCard item={item} principal={principal} reload={load} key={item.call_id} />)}</section></>;
}

function PlaybookPage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [items, setItems] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState<PlaybookDraftCreate>({
    version: "synthetic-acceptance-v2",
    label: "Synthetic local acceptance playbook",
    source_version: "synthetic-draft-v1",
  });
  async function load(): Promise<void> { setItems(await apiRequest<Playbook[]>("/api/playbooks", principal)); }
  useEffect(() => { setLoading(true); setError(null); load().catch((reason: unknown) => { setError(reason instanceof Error ? reason.message : "Unknown request error"); }).finally(() => { setLoading(false); }); }, [principal]);
  async function publish(version: string): Promise<void> {
    setMessage("");
    try { await apiRequest(`/api/playbooks/${version}/publish`, principal, { method: "POST" }); setMessage("Synthetic playbook published. Prior analyses remain tied to their original provenance."); await load(); }
    catch (reason) { setMessage(reason instanceof ApiRequestError ? reason.message : "Publication could not be completed."); }
  }
  async function createDraft(event: FormEvent): Promise<void> {
    event.preventDefault();
    setMessage("");
    try {
      await apiRequest("/api/playbooks/drafts", principal, {
        method: "POST",
        body: JSON.stringify(draft),
      });
      setMessage("New synthetic draft created as an immutable version candidate.");
      await load();
    } catch (reason) {
      setMessage(reason instanceof ApiRequestError ? reason.message : "Draft creation could not be completed.");
    }
  }
  if (loading || error) return <RequestState loading={loading} error={error} area="playbook" />;
  return <>
    <section className="page-title">
      <div className="eyebrow">Versioned synthetic rules</div>
        <h1>Playbook lifecycle</h1>
      <p>Create a bounded synthetic draft from an existing version, then publish it immutably. Earlier analyses are never reprocessed or rewritten.</p>
    </section>
    <p className="authorization-message" role="status" tabIndex={-1}>{message}</p>
    <form className="playbook-card playbook-draft-form" onSubmit={(event) => void createDraft(event)}>
      <div className="item-topline"><div><span className="content-origin human-origin">Administrator action</span><h2>Create synthetic draft</h2></div><span className="lifecycle lifecycle-draft">Draft only</span></div>
      <fieldset disabled={principal !== "demo-admin"}>
        <legend>Clone a validated synthetic version</legend>
        <label><span>New version</span><input required value={draft.version} onChange={(event) => { setDraft({ ...draft, version: event.target.value }); }} /></label>
        <label><span>Draft label</span><input required value={draft.label} onChange={(event) => { setDraft({ ...draft, label: event.target.value }); }} /></label>
        <label><span>Source version</span><select value={draft.source_version} onChange={(event) => { setDraft({ ...draft, source_version: event.target.value }); }}>{items.map((item) => <option key={item.version} value={item.version}>{item.version}</option>)}</select></label>
      </fieldset>
      {principal === "demo-admin" ? <button className="primary-button" type="submit">Create synthetic draft</button> : <p className="operator-note">Only the demo administrator may create a draft.</p>}
    </form>
    <div className="playbook-list">{items.map((item) => <article className="playbook-card" key={item.version}><div className="item-topline"><div><span className="content-origin inference-origin">Synthetic playbook</span><h2>{item.label}</h2></div><span className={`lifecycle lifecycle-${item.lifecycle}`}>{humanize(item.lifecycle)}</span></div><dl className="playbook-meta"><dt>Version</dt><dd>{item.version}</dd><dt>Created</dt><dd>{new Date(item.created_at).toLocaleString()}</dd><dt>Published</dt><dd>{item.published_at ? new Date(item.published_at).toLocaleString() : "Not published"}</dd></dl><h3>Categories</h3><div className="tag-list">{item.categories.map((category) => <span key={category}>{humanize(category)}</span>)}</div><h3>Key rules</h3><ul>{item.key_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul><button className="primary-button" type="button" disabled={item.lifecycle !== "draft"} onClick={() => void publish(item.version)}>{item.lifecycle === "draft" ? "Publish synthetic draft" : "Published · Rules preserved"}</button></article>)}</div>
  </>;
}

function localDateTimeValue(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

function localSubmissionId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return `browser-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function UploadPage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [capabilities, setCapabilities] = useState<UploadCapabilities | null>(null);
  const [receipts, setReceipts] = useState<UploadReceipt[]>([]);
  const [receipt, setReceipt] = useState<UploadReceipt | null>(null);
  const [mode, setMode] = useState<"synthetic_audio" | "transcript_only">("synthetic_audio");
  const [file, setFile] = useState<File | null>(null);
  const [attested, setAttested] = useState(false);
  const [direction, setDirection] = useState("inbound");
  const [capturedAt, setCapturedAt] = useState(localDateTimeValue);
  const [language, setLanguage] = useState("en");
  const [staffExtension, setStaffExtension] = useState("SYN-104");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const messageRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function clearSelectedFile(): void {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function load(): Promise<void> {
    const result = await apiRequest<UploadCapabilities>("/api/uploads/capabilities", principal);
    setCapabilities(result);
    if (result.can_view_receipts) {
      const list = await apiRequest<{ uploads: UploadReceipt[] }>("/api/uploads", principal);
      setReceipts(list.uploads);
    } else {
      setReceipts([]);
      setReceipt(null);
    }
  }

  useEffect(() => {
    setMessage("");
    load().catch((reason: unknown) => {
      setMessage(reason instanceof Error ? reason.message : "Upload authorization could not be checked.");
    });
  }, [principal]);

  useEffect(() => {
    if (!message) return undefined;
    const focus = window.setTimeout(() => messageRef.current?.focus({ preventScroll: true }), 0);
    return () => { window.clearTimeout(focus); };
  }, [message]);

  async function processUpload(uploadId: string): Promise<void> {
    try {
      const result = await apiRequest<UploadReceipt>(`/api/uploads/${uploadId}/process`, principal, {
        method: "POST",
      });
      setReceipt(result);
      setReceipts((items) => [result, ...items.filter((item) => item.upload_id !== result.upload_id)]);
      setMessage(result.state === "analyzed" ? "Synthetic processing completed." : `Processing stopped: ${humanize(result.state)}.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Synthetic processing could not start.");
    }
  }

  useEffect(() => {
    if (receipt?.submission_kind !== "synthetic_audio" || receipt.state !== "ready") return undefined;
    const timer = window.setTimeout(() => void processUpload(receipt.upload_id), 2500);
    return () => { window.clearTimeout(timer); };
  }, [receipt?.upload_id, receipt?.state, principal]);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!file || !attested) return;
    setSubmitting(true);
    setMessage("");
    const submissionId = localSubmissionId();
    const capturedIso = new Date(capturedAt).toISOString();
    try {
      let result: UploadReceipt;
      if (mode === "synthetic_audio") {
        const body = new FormData();
        body.set("client_submission_id", submissionId);
        body.set("generated_only_attestation", "true");
        body.set("direction", direction);
        body.set("captured_at", capturedIso);
        body.set("language_hint", language);
        body.set("staff_extension", staffExtension);
        body.set("file", file);
        result = await apiRequest<UploadReceipt>("/api/uploads/audio", principal, {
          method: "POST",
          body,
        });
      } else {
        result = await apiRequest<UploadReceipt>("/api/uploads/transcript", principal, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Client-Submission-ID": submissionId,
            "X-Generated-Only-Attestation": "true",
            "X-Upload-Direction": direction,
            "X-Upload-Captured-At": capturedIso,
            "X-Upload-Language": language,
            "X-Upload-Staff-Extension": staffExtension,
          },
          body: await file.text(),
        });
      }
      setReceipt(result);
      setReceipts((items) => [result, ...items.filter((item) => item.upload_id !== result.upload_id)]);
      setMessage(result.duplicate ? "Duplicate recognized. The existing internal receipt was returned." : "Internal receipt created. Input validation passed.");
      clearSelectedFile();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "The upload could not be accepted.");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel(): Promise<void> {
    if (!receipt) return;
    try {
      const result = await apiRequest<UploadReceipt>(`/api/uploads/${receipt.upload_id}`, principal, {
        method: "DELETE",
      });
      setReceipt(result);
      setReceipts((items) => [result, ...items.filter((item) => item.upload_id !== result.upload_id)]);
      setMessage(result.state === "cancelled" ? "Upload cancelled and temporary media deletion confirmed." : "Cancellation ended with a visible deletion failure.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Cancellation could not be completed.");
    }
  }

  async function retry(): Promise<void> {
    if (!receipt) return;
    try {
      const result = await apiRequest<UploadReceipt>(`/api/uploads/${receipt.upload_id}/retry`, principal, {
        method: "POST",
      });
      setReceipt(result);
      setReceipts((items) => [result, ...items.filter((item) => item.upload_id !== result.upload_id)]);
      setMessage(result.state === "analyzed" ? "Retry completed for the same call." : "Retry reached a named failure.");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Retry could not be completed.");
    }
  }

  const denied = capabilities !== null && !capabilities.can_submit;
  return (
    <>
      <section className="page-title upload-title">
        <div className="eyebrow">Local single-item bridge</div>
        <h1>Submit one invented call artifact.</h1>
        <p>Only locally generated non-human audio or a fully invented transcript-only JSON artifact is permitted.</p>
      </section>
      <aside className="upload-prohibition" role="note">
        <b>Real or human recordings are prohibited.</b>
        <span>Do not select, copy, inspect, or submit client, caller, employee, or other human audio. This surface is synthetic-only and cannot activate production processing.</span>
      </aside>
      {denied && (
        <div className="authorization-denial" role="alert">
          <b>Upload access denied for the reviewer role.</b>
          <span>Reviewers may open completed uploaded calls and append feedback, but cannot submit, view receipts, retry, cancel, or delete.</span>
        </div>
      )}
      <div className="upload-layout">
        <form className="upload-form" onSubmit={(event) => void submit(event)} aria-describedby="upload-boundary">
          <div id="upload-boundary" className="form-boundary">Single item only · No folders, URLs, recording capture, batch manifests, or remote downloads.</div>
          <fieldset disabled={denied || submitting}>
            <legend>Artifact mode</legend>
            <div className="mode-selector">
              <label><input type="radio" name="upload-mode" value="synthetic_audio" checked={mode === "synthetic_audio"} onChange={() => { setMode("synthetic_audio"); clearSelectedFile(); }} /><span><b>Generated synthetic audio</b><small>Allowlisted non-human audio fingerprint</small></span></label>
              <label><input type="radio" name="upload-mode" value="transcript_only" checked={mode === "transcript_only"} onChange={() => { setMode("transcript_only"); clearSelectedFile(); }} /><span><b>Invented transcript JSON</b><small>transcript-only-artifact-v1</small></span></label>
            </div>
          </fieldset>
          <label className="file-field">
            <span>{mode === "synthetic_audio" ? "Choose one generated audio file" : "Choose one invented transcript JSON file"}</span>
            <input
              type="file"
              ref={fileInputRef}
              required
              disabled={denied || submitting}
              accept={mode === "synthetic_audio" ? ".wav,.mp3,.m4a,.mp4,.mpeg,.mpga,.webm" : ".json,application/json"}
              onChange={(event) => { setFile(event.target.files?.item(0) ?? null); }}
            />
            <small aria-live="polite">{file ? `Selected for this browser session: ${file.name}` : "No file selected. The filename is never retained."}</small>
          </label>
          <div className="upload-fields">
            <label><span>Direction</span><select value={direction} disabled={denied || submitting} onChange={(event) => { setDirection(event.target.value); }}><option value="inbound">Inbound</option><option value="outbound">Outbound</option><option value="unknown">Unknown</option></select></label>
            <label><span>Captured at</span><input type="datetime-local" required value={capturedAt} disabled={denied || submitting} onChange={(event) => { setCapturedAt(event.target.value); }} /></label>
            <label><span>Language hint</span><select value={language} disabled={denied || submitting} onChange={(event) => { setLanguage(event.target.value); }}><option value="en">English</option><option value="es">Spanish</option></select></label>
            <label><span>Synthetic staff extension</span><input type="text" required pattern="SYN-[0-9]{3}" value={staffExtension} disabled={denied || submitting} onChange={(event) => { setStaffExtension(event.target.value); }} aria-describedby="extension-help" /><small id="extension-help">Invented format: SYN-000 through SYN-999</small></label>
          </div>
          <label className="attestation"><input type="checkbox" required checked={attested} disabled={denied || submitting} onChange={(event) => { setAttested(event.target.checked); }} /><span><b>I attest this artifact is entirely generated or invented.</b><small>It contains no real or human recording, caller identity, phone number, or client data.</small></span></label>
          <button className="primary-button upload-submit" disabled={denied || submitting || !file || !attested} type="submit">{submitting ? "Validating one item…" : "Submit synthetic artifact"}</button>
        </form>

        <aside className="receipt-panel" aria-labelledby="receipt-title">
          <div className="panel-title"><div><span className="content-origin fact-origin">Content-free status</span><h2 id="receipt-title">Internal upload receipt</h2></div></div>
          {!receipt ? <p className="receipt-empty">A safe receipt and processing state will appear here after validation.</p> : (
            <div className="receipt-content">
              <span className={`upload-state state-${receipt.state}`}>{humanize(receipt.state)}</span>
              <dl>
                <dt>Internal receipt</dt><dd>{receipt.upload_id}</dd>
                <dt>Mode</dt><dd>{humanize(receipt.submission_kind)}</dd>
                <dt>Content reference</dt><dd>{receipt.content_hash_reference}</dd>
                <dt>Validation</dt><dd>{receipt.validation.media_format ? `${receipt.validation.media_format.toUpperCase()} · ${(receipt.validation.channel_count ?? 0).toString()} channel · ${(receipt.validation.sample_rate_hz ?? 0).toString()} Hz` : `${(receipt.validation.segment_count ?? 0).toString()} segments · ${receipt.validation.contract_version}`}</dd>
                <dt>Attempt</dt><dd>{receipt.attempt_number}</dd>
                <dt>Cleanup</dt><dd>{receipt.deletion_confirmed === null ? "Pending or not yet required" : receipt.deletion_confirmed ? "Confirmed" : "Failed"}</dd>
                {receipt.diagnostic_code && <><dt>Named result</dt><dd>{humanize(receipt.diagnostic_code)}</dd></>}
              </dl>
              <ol className="receipt-timeline">{receipt.history.map((event) => <li key={event.event_id}><span>{humanize(event.state)}</span><small>{event.attempt_number > 0 ? `Attempt ${event.attempt_number.toString()}` : "Pre-processing"}</small></li>)}</ol>
              <div className="receipt-actions">
                {receipt.state === "ready" && <button type="button" className="secondary-button" onClick={() => void cancel()}>Cancel and delete before processing</button>}
                {receipt.retryable && <button type="button" className="secondary-button" onClick={() => void retry()}>Retry same call</button>}
                {receipt.call_path && <a className="primary-button" href={receipt.call_path}>Open completed call</a>}
                {receipt.report_path && <a className="secondary-button" href={receipt.report_path}>Open resulting report</a>}
              </div>
            </div>
          )}
        </aside>
      </div>
      <div className="upload-message" ref={messageRef} role="status" tabIndex={-1}>{message}</div>
      {capabilities?.can_view_receipts && receipts.length > 0 && (
        <section className="recent-receipts" aria-labelledby="recent-receipts-title">
          <div className="section-heading"><h2 id="recent-receipts-title">Recent content-free receipts</h2><span className="count-badge">{receipts.length}</span></div>
          <div>{receipts.map((item) => <button type="button" key={item.upload_id} onClick={() => { setReceipt(item); }}><span>{item.content_hash_reference}</span><b>{humanize(item.state)}</b><small>{humanize(item.submission_kind)} · Attempt {item.attempt_number}</small></button>)}</div>
        </section>
      )}
    </>
  );
}

const retentionLabels: { key: keyof LocalConfiguration["retention"]; label: string }[] = [
  { key: "generated_media_days", label: "Generated media" },
  { key: "invented_transcript_days", label: "Invented transcripts" },
  { key: "accepted_analysis_days", label: "Accepted analyses" },
  { key: "daily_report_days", label: "Daily reports" },
  { key: "processing_attempt_days", label: "Processing attempts" },
  { key: "manual_upload_receipt_days", label: "Manual-upload receipts" },
  { key: "reviewer_feedback_days", label: "Reviewer feedback" },
  { key: "playbook_version_days", label: "Playbook versions" },
  { key: "audit_metadata_days", label: "Audit metadata" },
];

function OperationsPage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [history, setHistory] = useState<ConfigurationHistory | null>(null);
  const [draft, setDraft] = useState<LocalConfiguration | null>(null);
  const [jobs, setJobs] = useState<DeletionJob[]>([]);
  const [audits, setAudits] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const messageRef = useRef<HTMLDivElement>(null);

  async function load(): Promise<void> {
    const [overviewResult, historyResult, jobResult, auditResult] = await Promise.all([
      apiRequest<OperationsOverview>("/api/operations/overview", principal),
      apiRequest<ConfigurationHistory>("/api/operations/configuration", principal),
      apiRequest<DeletionJob[]>("/api/operations/deletions", principal),
      apiRequest<AuditEvent[]>("/api/audit-events", principal),
    ]);
    const current = historyResult.versions[0];
    if (!current) throw new Error("Local configuration history is empty.");
    setOverview(overviewResult);
    setHistory(historyResult);
    setDraft(structuredClone(current.configuration));
    setJobs(jobResult);
    setAudits(auditResult.slice(-25).reverse());
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDenied(false);
    setMessage("");
    load()
      .catch((reason: unknown) => {
        if (!active) return;
        setDenied(reason instanceof ApiRequestError && reason.status === 403);
        if (!(reason instanceof ApiRequestError) || reason.status !== 403) {
          setMessage(reason instanceof Error ? reason.message : "Operations data is unavailable.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [principal]);

  useEffect(() => {
    if (!message) return undefined;
    const focus = window.setTimeout(() => messageRef.current?.focus({ preventScroll: true }), 0);
    return () => { window.clearTimeout(focus); };
  }, [message]);

  async function perform(action: () => Promise<unknown>, success: string): Promise<void> {
    setWorking(true);
    setMessage("");
    try {
      await action();
      setMessage(success);
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "The local operation could not complete.");
    } finally {
      setWorking(false);
    }
  }

  async function publish(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!draft) return;
    await perform(
      () => apiRequest("/api/operations/configuration", principal, {
        method: "POST",
        body: JSON.stringify(draft),
      }),
      "New immutable local configuration version published.",
    );
  }

  if (loading) return <RequestState loading error={null} area="operations workspace" />;
  if (denied) {
    return (
      <section className="authorization-denial operations-denial" role="alert">
        <b>Operations access denied for the reviewer role.</b>
        <span>Reviewers cannot view configuration, retention, recovery, metrics, or operational audit controls.</span>
      </section>
    );
  }
  if (!overview || !history || !draft) return <RequestState loading={false} error={message || "Operations data is unavailable."} area="operations workspace" />;

  return (
    <>
      <section className="page-title operations-title">
        <div className="eyebrow">Operations</div>
        <h1>Local controls and recovery</h1>
        <p>Configuration, reconciliation, retention, deletion, and recovery controls for invented data only.</p>
        <div className="operations-boundary" role="note"><b>{overview.data_label}</b><span>{overview.environment}</span><span>Zero external requests</span></div>
      </section>
      <div className="operations-message" ref={messageRef} role="status" tabIndex={-1}>{message}</div>

      <section className="operations-metrics" aria-labelledby="operations-metrics-title">
        <div className="section-heading"><div><span className="content-origin fact-origin">Persisted safe counts</span><h2 id="operations-metrics-title">Operational reconciliation</h2></div><span className="count-badge">Config v{overview.configuration_version}</span></div>
        <div className="operations-metric-grid">
          <div><span>Successful</span><b>{overview.success_count}</b></div>
          <div><span>Failures</span><b>{overview.failure_count}</b></div>
          <div><span>Retries</span><b>{overview.retry_count}</b></div>
          <div><span>Average latency</span><b>{overview.processing_latency.average_milliseconds} ms</b></div>
          <div><span>Maximum latency</span><b>{overview.processing_latency.maximum_milliseconds} ms</b></div>
          <div><span>Pending deletion</span><b>{overview.pending_deletions}</b></div>
          <div><span>Failed deletion</span><b>{overview.failed_deletions}</b></div>
          <div><span>Restore drill</span><b>{humanize(overview.backup_restore_status)}</b></div>
        </div>
        <div className={`reconciliation-strip ${overview.reconciliation.exact ? "exact" : "mismatch"}`}>
          <b>{!overview.reconciliation.available ? "Reconciliation unavailable" : overview.reconciliation.exact ? "Reconciliation exact" : "Reconciliation needs attention"}</b>
          <span>Expected {overview.reconciliation.expected} · Received {overview.reconciliation.received} · Analyzed {overview.reconciliation.analyzed} · Failed {overview.reconciliation.failed} · Missing {overview.reconciliation.missing}</span>
        </div>
        <div className="safe-state-list" aria-label="Processing volume by safe state">
          {overview.processing_volume.map((item) => <span key={item.state}><b>{item.count}</b>{humanize(item.state)}</span>)}
        </div>
      </section>

      <div className="operations-layout">
        <form className="configuration-panel" onSubmit={(event) => void publish(event)}>
          <div className="panel-title"><div><span className="content-origin inference-origin">Versioned local policy</span><h2>Current configuration</h2></div><span className="lifecycle lifecycle-published">Version {history.current_version}</span></div>
          <fieldset disabled={working || principal !== "demo-admin"}>
            <legend>Deterministic report settings</legend>
            <label><span>Firm timezone</span><input value={draft.firm_timezone} readOnly /></label>
            <label><span>Daily report cutoff</span><input type="time" value={draft.daily_report_cutoff} onChange={(event) => { setDraft({ ...draft, daily_report_cutoff: event.target.value }); }} /></label>
            <label><span>Synthetic playbook</span><input value={draft.synthetic_playbook_version} readOnly /></label>
          </fieldset>
          <fieldset disabled={working || principal !== "demo-admin"}>
            <legend>Synthetic retention schedule in days</legend>
            <div className="retention-grid">
              {retentionLabels.map((item) => (
                <label key={item.key}><span>{item.label}</span><input type="number" min="1" max="3650" required value={draft.retention[item.key]} onChange={(event) => { setDraft({ ...draft, retention: { ...draft.retention, [item.key]: Number(event.target.value) } }); }} /></label>
              ))}
            </div>
          </fieldset>
          <dl className="configuration-summary">
            <dt>Eligible directions</dt><dd>{draft.eligible_call_directions.map(humanize).join(" · ")}</dd>
            <dt>Eligible categories</dt><dd>{draft.eligible_call_categories.length} synthetic categories</dd>
            <dt>Invented extensions</dt><dd>{draft.staff_extension_mappings.map((item) => item.extension).join(" · ")}</dd>
            <dt>Report roles</dt><dd>{draft.report_roles.map(humanize).join(" · ")}</dd>
            <dt>Deletion</dt><dd>Scheduled content destruction with content-free tombstone</dd>
            <dt>Notifications</dt><dd>Local preview / no-op</dd>
          </dl>
          {principal === "demo-admin" ? <button className="primary-button" type="submit" disabled={working}>Publish new configuration version</button> : <p className="operator-note">Operations users may review history and run controls. Only the demo administrator may publish configuration.</p>}
        </form>

        <section className="operator-actions" aria-labelledby="operator-actions-title">
          <div className="panel-title"><div><span className="content-origin fact-origin">Authorized local actions</span><h2 id="operator-actions-title">Maintenance controls</h2></div></div>
          <button className="primary-button" type="button" disabled={working} onClick={() => void perform(() => apiRequest("/api/operations/retention/run", principal, { method: "POST" }), "Retention evaluation and scheduled deletion run completed.")}>Run retention evaluation</button>
          <button className="secondary-button" type="button" disabled={working} onClick={() => void perform(() => apiRequest("/api/operations/backup-restore-drill", principal, { method: "POST" }), "Disposable backup and isolated restore drill passed; artifacts removed.")}>Run backup / restore drill</button>
          <button className="secondary-button" type="button" disabled={working} onClick={() => void perform(() => apiRequest("/api/operations/notification-preview", principal, { method: "POST" }), "Local notification preview created. Nothing was sent.")}>Preview no-op notification</button>
          <dl className="maintenance-status">
            <dt>Retention policy</dt><dd>{humanize(overview.retention_policy_status)}</dd>
            <dt>Last maintenance</dt><dd>{overview.last_successful_maintenance_at ? new Date(overview.last_successful_maintenance_at).toLocaleString() : "Not run"}</dd>
            <dt>External attempts</dt><dd>{overview.external_requests}</dd>
          </dl>
        </section>
      </div>

      <section className="deletion-section" aria-labelledby="deletion-jobs-title">
        <div className="section-heading"><div><span className="content-origin fact-origin">Content-free lifecycle</span><h2 id="deletion-jobs-title">Retention and deletion status</h2></div><span className="count-badge">{jobs.length}</span></div>
        {jobs.length === 0 ? <p className="empty-section">No retention records are due under the active local policy.</p> : <div className="deletion-list">{jobs.map((job) => <article key={job.job_id}><div><b>{humanize(job.resource_type)}</b><span>{job.resource_id}</span></div><span className={`deletion-state deletion-${job.state.toLowerCase()}`}>{humanize(job.state)}</span><small>Attempt {job.attempt_count} of 3 · Policy v{job.configuration_version}</small>{job.diagnostic_code && <p>{humanize(job.diagnostic_code)}</p>}{job.state === "RETRY_SCHEDULED" && <button className="secondary-button" type="button" disabled={working} onClick={() => void perform(() => apiRequest(`/api/operations/deletions/${job.job_id}/retry`, principal, { method: "POST" }), "Eligible deletion retry completed.")}>Retry eligible deletion</button>}</article>)}</div>}
      </section>

      <section className="configuration-history" aria-labelledby="configuration-history-title">
        <div className="section-heading"><div><span className="content-origin fact-origin">Immutable versions</span><h2 id="configuration-history-title">Configuration history</h2></div><span className="count-badge">{history.versions.length}</span></div>
        <ol>{history.versions.map((version) => <li key={version.configuration_id}><b>Version {version.version}</b><span>{version.content_hash_reference}</span><small>{new Date(version.created_at).toLocaleString()} · {humanize(version.principal.role)}</small></li>)}</ol>
      </section>

      <section className="operations-audit" aria-labelledby="operations-audit-title">
        <div className="section-heading"><div><span className="content-origin fact-origin">No request content retained</span><h2 id="operations-audit-title">Content-free audit history</h2></div><span className="count-badge">{audits.length}</span></div>
        <ol>{audits.map((event) => <li key={event.event_id}><b>{humanize(event.action)}</b><span>{humanize(event.result)}</span><small>{humanize(event.target_type)} · {event.target_id} · {new Date(event.created_at).toLocaleString()}</small></li>)}</ol>
      </section>
    </>
  );
}

function HealthPage(): ReactNode {
  return <section className="page-title"><div className="eyebrow">Operational status</div><h1>System health</h1><p>Use the content-free liveness and readiness endpoints for API and worker health.</p></section>;
}

export function App({ path = window.location.pathname }: { path?: string }): ReactNode {
  loadWebConfiguration();
  const [principal, setPrincipal] = useState<DemoPrincipal>(currentPrincipal);
  let page: ReactNode;
  const callMatch = path.match(/^\/calls\/([A-Za-z0-9._:-]+)$/);
  const callId = callMatch?.[1];
  const reportMatch = path.match(/^\/reports\/(\d{4}-\d{2}-\d{2})$/);
  const monthMatch = path.match(/^\/months\/(\d{4}-\d{2})$/);
  if (callId) page = <CallPage callId={callId} principal={principal} />;
  else if (reportMatch?.[1]) page = <ReportPage principal={principal} initialDate={reportMatch[1]} />;
  else if (monthMatch?.[1]) page = <MonthPage principal={principal} monthKey={monthMatch[1]} />;
  else if (path === "/uploads") page = <UploadPage principal={principal} />;
  else if (path === "/failures") page = <FailurePage principal={principal} />;
  else if (path === "/playbooks") page = <PlaybookPage principal={principal} />;
  else if (path === "/operations") page = <OperationsPage principal={principal} />;
  else if (path === "/health") page = <HealthPage />;
  else page = <MonthPage principal={principal} />;
  return <Shell principal={principal} setPrincipal={setPrincipal} path={path}>{page}</Shell>;
}
