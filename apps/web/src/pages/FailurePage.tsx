import { type ReactNode, useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";
import type { DemoPrincipal, FailureItem, FailureQueue } from "../types";
import { RequestState } from "../shared";

function FailureCard({ item, principal, reload }: { item: FailureItem; principal: DemoPrincipal; reload: () => Promise<void> }): ReactNode {
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  const lock = useRef(false);
  async function retry(): Promise<void> {
    if (lock.current) return;
    lock.current = true; setWorking(true);
    try {
      await apiRequest(`/api/failures/${item.call_id}/retry`, principal, { method: "POST" });
      await reload();
      setMessage("Processing attempt recorded. Check the current state and preserved history below.");
    } catch (reason) {
      setMessage(`Retry outcome could not be confirmed. Reload the queue before another attempt. ${reason instanceof Error ? reason.message : "Local service unavailable."}`);
    } finally { lock.current = false; setWorking(false); }
  }
  return <article className="failure-card"><div className="item-topline"><h3>{item.synthetic_reference}</h3><span className={item.resolved ? "resolved-badge" : "failure-badge"}>{item.resolved ? "Resolved" : "Current failure"}</span></div><dl className="failure-meta"><dt>Failed stage</dt><dd>{item.failed_stage}</dd><dt>Diagnostic code</dt><dd>{item.diagnostic_code}</dd><dt>First attempt</dt><dd>{new Date(item.first_attempt_at).toLocaleString()}</dd><dt>Latest attempt</dt><dd>{new Date(item.latest_attempt_at).toLocaleString()}</dd><dt>Attempts</dt><dd>{item.attempt_count}</dd><dt>Terminal state</dt><dd>{item.current_terminal_state}</dd></dl><ol className="attempt-list">{item.attempt_history.map((attempt) => <li key={attempt.attempt_id}><b>Attempt {attempt.attempt_number}</b><span>{attempt.state}</span>{attempt.diagnostic_code && <small>{attempt.diagnostic_code}</small>}</li>)}</ol>{!item.resolved && <button type="button" className="secondary-button" disabled={working || !item.retryable} onClick={() => void retry()}>{item.retryable ? "Retry synthetic processing" : "Permanent failure · Retry unavailable"}</button>}<p className="form-message" aria-live="polite">{message}</p></article>;
}

export function FailurePage({ principal }: { principal: DemoPrincipal }): ReactNode {
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

