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
  DailyReport,
  DemoPrincipal,
  Evidence,
  FailureItem,
  FailureQueue,
  Finding,
  Playbook,
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
    <div className="synthetic-banner" role="status">
      <span className="banner-dot" aria-hidden="true" />
      <strong>Synthetic demo data</strong>
      <span>No live services connected. No client calls, audio, or identities are present.</span>
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
  return (
    <header className="site-header">
      <a className="brand" href="/" aria-label="Colacci Law Call Review home">
        <span className="brand-mark" aria-hidden="true">CL</span>
        <span><b>Colacci Law</b><small>Synthetic call review</small></span>
      </a>
      <nav aria-label="Primary navigation">
        <a className={`nav-link ${path === "/" ? "active" : ""}`} href="/">Daily report</a>
        <a className={`nav-link ${path === "/failures" ? "active" : ""}`} href="/failures">Failures</a>
        <a className={`nav-link ${path === "/playbooks" ? "active" : ""}`} href="/playbooks">Playbook</a>
      </nav>
      <label className="identity-control">
        <span>Demo identity</span>
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
      <SyntheticBanner />
      <Header principal={principal} setPrincipal={setPrincipal} path={path} />
      <main id="main-content" tabIndex={-1}>{children}</main>
      <footer>
        <span>Slice 2 · Synthetic review experience</span>
        <span>Advisory workflow · Human review required</span>
      </footer>
    </>
  );
}

function RequestState({
  loading,
  error,
  empty,
}: {
  loading: boolean;
  error: string | null;
  empty?: string;
}): ReactNode {
  if (loading) return <div className="state-panel" role="status">Loading synthetic review data…</div>;
  if (error) return <div className="state-panel error-state" role="alert"><b>Unable to load this view.</b><span>{error}</span></div>;
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

function ReportPage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<{ dates: string[] }>("/api/reports/dates", principal)
      .then(async (result) => {
        if (!active) return;
        setDates(result.dates);
        const date = selectedDate || result.dates[0];
        if (!date) {
          setReport(null);
          return;
        }
        setSelectedDate(date);
        const value = await apiRequest<DailyReport>(`/api/reports/${date}`, principal);
        setReport(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unknown request error");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [principal, selectedDate]);

  if (loading || error || !report) {
    return <RequestState loading={loading} error={error} empty={!loading && !error ? "Run make seed-demo to create the report." : undefined} />;
  }
  const counts = report.completeness.reconciliation;
  return (
    <>
      <section className="report-hero" aria-labelledby="report-title">
        <div>
          <div className="eyebrow">Daily synthetic call review</div>
          <h1 id="report-title">Review the calls that need a human decision.</h1>
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
          <h2 id="completeness-title">Coverage is {report.completeness.status}.</h2>
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
                <span className="section-index">{String(index + 1).padStart(2, "0")}</span>
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
                      <a className="call-reference" href={item.analysis_id ? `/calls/${item.call_id}` : "/failures"}>{item.synthetic_reference}</a>
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

  if (loading || error || !detail) return <RequestState loading={loading} error={error} />;
  return (
    <>
      <a className="back-link" href="/">← Back to daily report</a>
      <section className="call-heading">
        <div>
          <div className="eyebrow">Synthetic call analysis</div>
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
          <section className="side-card provenance"><h2>Provenance</h2><dl>{Object.entries(detail.provenance).map(([key, value]) => <Fragment key={key}><dt>{humanize(key)}</dt><dd>{value}</dd></Fragment>)}</dl></section>
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
  if (loading || error || !queue) return <RequestState loading={loading} error={error} />;
  return <><section className="page-title"><div className="eyebrow">Content-free operations</div><h1>Synthetic failure queue</h1><p>Safe identifiers and diagnostics only. No transcript, summary, payload, URL, credential, or stack trace appears here.</p></section><section className="queue-section"><div className="section-heading"><h2>Current failures</h2><span className="count-badge">{queue.current.length}</span></div>{queue.current.map((item) => <FailureCard item={item} principal={principal} reload={load} key={item.call_id} />)}</section><section className="queue-section"><div className="section-heading"><h2>Resolved history</h2><span className="count-badge">{queue.resolved.length}</span></div>{queue.resolved.map((item) => <FailureCard item={item} principal={principal} reload={load} key={item.call_id} />)}</section></>;
}

function PlaybookPage({ principal }: { principal: DemoPrincipal }): ReactNode {
  const [items, setItems] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  async function load(): Promise<void> { setItems(await apiRequest<Playbook[]>("/api/playbooks", principal)); }
  useEffect(() => { setLoading(true); setError(null); load().catch((reason: unknown) => { setError(reason instanceof Error ? reason.message : "Unknown request error"); }).finally(() => { setLoading(false); }); }, [principal]);
  async function publish(version: string): Promise<void> {
    setMessage("");
    try { await apiRequest(`/api/playbooks/${version}/publish`, principal, { method: "POST" }); setMessage("Synthetic playbook published. Prior analyses remain tied to their original provenance."); await load(); }
    catch (reason) { setMessage(reason instanceof ApiRequestError ? reason.message : "Publication could not be completed."); }
  }
  if (loading || error) return <RequestState loading={loading} error={error} />;
  return <><section className="page-title"><div className="eyebrow">Versioned synthetic rules</div><h1>Review playbook lifecycle</h1><p>This view publishes an immutable synthetic draft. It does not edit prompts, reprocess calls, or change earlier analyses.</p></section><p className="authorization-message" role="status" tabIndex={-1}>{message}</p><div className="playbook-list">{items.map((item) => <article className="playbook-card" key={item.version}><div className="item-topline"><div><span className="content-origin inference-origin">Synthetic playbook</span><h2>{item.label}</h2></div><span className={`lifecycle lifecycle-${item.lifecycle}`}>{humanize(item.lifecycle)}</span></div><dl className="playbook-meta"><dt>Version</dt><dd>{item.version}</dd><dt>Created</dt><dd>{new Date(item.created_at).toLocaleString()}</dd><dt>Published</dt><dd>{item.published_at ? new Date(item.published_at).toLocaleString() : "Not published"}</dd></dl><h3>Categories</h3><div className="tag-list">{item.categories.map((category) => <span key={category}>{humanize(category)}</span>)}</div><h3>Key rules</h3><ul>{item.key_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul><button className="primary-button" type="button" disabled={item.lifecycle !== "draft"} onClick={() => void publish(item.version)}>{item.lifecycle === "draft" ? "Publish synthetic draft" : "Published · Rules preserved"}</button></article>)}</div></>;
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
  if (callId) page = <CallPage callId={callId} principal={principal} />;
  else if (path === "/failures") page = <FailurePage principal={principal} />;
  else if (path === "/playbooks") page = <PlaybookPage principal={principal} />;
  else if (path === "/health") page = <HealthPage />;
  else page = <ReportPage principal={principal} />;
  return <Shell principal={principal} setPrincipal={setPrincipal} path={path}>{page}</Shell>;
}
