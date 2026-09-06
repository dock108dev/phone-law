import { Fragment, type ReactNode, type SubmitEvent, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "../api";
import type { CallDetail, DemoPrincipal, Evidence, Finding, ReviewEvent } from "../types";
import { feedbackLabels, humanize, provenanceValue, clock, RequestState } from "../shared";

function EvidenceButton({ evidence, jump }: { evidence: Evidence; jump: (id: string) => void }): ReactNode {
  return <button className="evidence-link button-link" type="button" onClick={() => { jump(evidence.segment_id); }}>Jump to {clock(evidence.start_seconds)} · {humanize(evidence.speaker)}</button>;
}

type ReviewIntent = { request_id: string; label: string; finding_id: string | null; note: string | null };

function useReviewSave(detail: CallDetail, target: string | null, principal: DemoPrincipal, reload: () => Promise<void>): {
  pending: ReviewIntent | null; working: boolean; message: string; save: (label: string, note: string) => Promise<boolean>;
} {
  const storageKey = `colacci-review-intent:${principal}:${detail.analysis_id}:${target ?? "missing"}`;
  const [pending, setPending] = useState<ReviewIntent | null>(() => {
    const stored = window.sessionStorage.getItem(storageKey);
    return stored ? JSON.parse(stored) as ReviewIntent : null;
  });
  const lock = useRef(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState(pending ? "Previous save not confirmed. Retry the same assessment to check its persisted result." : "");
  async function save(label: string, note: string): Promise<boolean> {
    if (lock.current) return false;
    lock.current = true;
    setWorking(true);
    setMessage("");
    const intent = pending ?? { request_id: Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join(""), label, finding_id: target, note: note.trim() || null };
    window.sessionStorage.setItem(storageKey, JSON.stringify(intent));
    setPending(intent);
    try {
      const result = await apiRequest<ReviewEvent>(`/api/analyses/${detail.analysis_id}/reviews`, principal, { method: "POST", body: JSON.stringify(intent) });
      window.sessionStorage.removeItem(storageKey);
      setPending(null);
      try {
        await reload();
        setMessage(target ? "Feedback saved as a new review event." : "Missing finding saved as a new review event.");
      } catch {
        setMessage(`Assessment saved (${result.event_id}). History could not refresh; reload to see the persisted result.`);
      }
      return true;
    } catch (reason) {
      const denied = reason instanceof ApiRequestError && [400, 403, 404, 409, 422].includes(reason.status);
      if (denied) { window.sessionStorage.removeItem(storageKey); setPending(null); }
      setMessage(`${denied ? "Assessment was not saved." : "Save not confirmed. Retry the same assessment; it will not create a duplicate."} ${reason instanceof Error ? reason.message : "Local service unavailable."}`);
      return false;
    } finally { lock.current = false; setWorking(false); }
  }
  return { pending, working, message, save };
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
  const { pending, working, message, save } = useReviewSave(detail, finding.finding_id, principal, reload);
  const [label, setLabel] = useState(pending?.label ?? "");
  const [note, setNote] = useState(pending?.note ?? "");
  const messageRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!message) return undefined;
    const focusMessage = window.setTimeout(() => {
      messageRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => { window.clearTimeout(focusMessage); };
  }, [message]);
  async function submit(event: SubmitEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (await save(label, note)) { setLabel(""); setNote(""); }
  }
  return (
    <article className="finding-card">
      <div className="content-origin inference-origin">Fixture/model inference</div>
      <div className="item-topline"><span className="finding-kind">{humanize(finding.kind)}</span><span>{finding.material ? "Material finding" : "Supporting finding"}</span></div>
      <h3>{finding.statement}</h3>
      <div className="evidence-list">{finding.evidence.map((evidence) => <EvidenceButton evidence={evidence} jump={jump} key={evidence.segment_id} />)}</div>
      <form className="feedback-form" onSubmit={(event) => void submit(event)}>
        <fieldset disabled={working || !!pending}>
          <legend>Assess the finding above</legend>
          <p>Correct confirms this analysis; Incorrect rejects it. Neither completes any real-world action.</p>
          <div className="feedback-options">
            {feedbackLabels.map((value) => (
              <label key={value}>
                <input type="radio" name={`label-${finding.finding_id}`} value={value} checked={label === value} onChange={() => { setLabel(value); }} />
                <span>{humanize(value)}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="note-field"><span>Reviewer note <small>(optional)</small></span><textarea disabled={working || !!pending} value={note} onChange={(event) => { setNote(event.target.value); }} rows={2} /></label>
        <button className="primary-button" disabled={working || (!label && !pending)} type="submit">{working ? "Saving assessment…" : pending ? "Retry same assessment" : "Save feedback"}</button>
        <div aria-live="polite">
          {message ? <a className="form-message" ref={messageRef} href="#review-history-title" autoFocus>{message}</a> : <p className="form-message" />}
        </div>
      </form>
    </article>
  );
}

function MissingFeedback({ detail, principal, reload }: { detail: CallDetail; principal: DemoPrincipal; reload: () => Promise<void> }): ReactNode {
  const { pending, working, message, save } = useReviewSave(detail, null, principal, reload);
  const [note, setNote] = useState(pending?.note ?? "");
  const messageRef = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (!message) return undefined;
    const focusMessage = window.setTimeout(() => {
      messageRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => { window.clearTimeout(focusMessage); };
  }, [message]);
  async function submit(event: SubmitEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (await save("missing", note)) setNote("");
  }
  return (
    <form className="missing-form" onSubmit={(event) => void submit(event)}>
      <div className="content-origin human-origin">Human review</div>
      <h3>Add a missing finding</h3>
      <p>Record an omission without changing the original analysis or playbook.</p>
      <label className="note-field"><span>What is missing? <b>(required)</b></span><textarea disabled={working || !!pending} required value={note} onChange={(event) => { setNote(event.target.value); }} rows={3} /></label>
      <button className="secondary-button" disabled={working} type="submit">{working ? "Saving assessment…" : pending ? "Retry same assessment" : "Add missing finding"}</button>
      <div aria-live="polite">
        {message ? <a className="form-message" ref={messageRef} href="#review-history-title" autoFocus>{message}</a> : <p className="form-message" />}
      </div>
    </form>
  );
}

export function CallPage({ callId, principal }: { callId: string; principal: DemoPrincipal }): ReactNode {
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
      document.getElementById(segmentId)?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
      document.getElementById(segmentId)?.focus();
    }, 0);
  }
  useEffect(() => {
    if (detail && window.location.hash && !handledInitialHash.current) {
      handledInitialHash.current = true;
      jump(window.location.hash.slice(1));
    }
  }, [detail]);

  useEffect(() => {
    const onHashChange = (): void => { if (window.location.hash) jump(window.location.hash.slice(1)); };
    window.addEventListener("hashchange", onHashChange);
    return () => { window.removeEventListener("hashchange", onHashChange); };
  }, []);

  if (loading || error || !detail) return <RequestState loading={loading} error={error} area="call review" />;
  return (
    <>
      {new URLSearchParams(window.location.search).get("briefing")?.match(/^\d{4}-\d{2}-\d{2}$/) ? <a className="back-link" href={`/briefing/${new URLSearchParams(window.location.search).get("briefing") ?? ""}#call-${detail.call_id}`}>← Back to morning briefing</a> : <a className="back-link" href={`/reports/${detail.occurred_at.slice(0, 10)}?month=${detail.occurred_at.slice(0, 7)}`}>← Back to daily report</a>}
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
        <div className="metadata"><span>Time</span><strong>{new Date(detail.occurred_at).toLocaleString("en-US", { timeZone: "America/New_York", timeZoneName: "short" })}</strong></div>
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
              {detail.findings.map((finding) => <FindingFeedback finding={finding} detail={detail} principal={principal} jump={jump} reload={load} key={`${principal}:${finding.finding_id}`} />)}
              {detail.findings.length === 0 && <div className="empty-section">No original finding was produced. Use the missing-finding control when needed.</div>}
            </div>
            <MissingFeedback key={principal} detail={detail} principal={principal} reload={load} />
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
        <h2 id="review-history-title" tabIndex={-1}>Append-only review history</h2>
        {detail.review_history.length === 0 ? <p>No feedback recorded yet.</p> : <ol>{detail.review_history.map((event) => <li key={event.event_id}><b>{humanize(event.label)}</b><span>{detail.findings.find((finding) => finding.finding_id === event.finding_id)?.statement ?? event.finding_id ?? "Analysis-level missing finding"}</span>{event.note && <p>{event.note}</p>}<small>{event.principal.principal_id} · {new Date(event.created_at).toLocaleString()}</small></li>)}</ol>}
      </section>
    </>
  );
}

