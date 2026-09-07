import { type ReactNode, type SubmitEvent, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "../api";
import type { AuditEvent, ConfigurationHistory, DeletionJob, DemoPrincipal, LocalConfiguration, OperationsOverview } from "../types";
import { humanize, RequestState } from "../shared";

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

export function OperationsPage({ principal }: { principal: DemoPrincipal }): ReactNode {
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

  async function publish(event: SubmitEvent<HTMLFormElement>): Promise<void> {
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
        <p>Settings and maintenance for synthetic data.</p>
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

