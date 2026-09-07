import { type ReactNode, useEffect, useState } from "react";
import { apiRequest } from "../api";
import type { DailyReport, DemoPrincipal } from "../types";
import { humanize, RequestState, Metric, EvidenceLink } from "../shared";

export function ReportPage({ principal, initialDate = "" }: { principal: DemoPrincipal; initialDate?: string }): ReactNode {
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
          <a href={`/briefing/${report.business_date}`}>Open this day’s briefing</a>
        </div>
        <label className="date-control">
          <span>Report date</span>
          <select value={selectedDate} onChange={(event) => { window.location.assign(`/reports/${encodeURIComponent(event.target.value)}`); }}>
            {dates.map((date) => <option value={date} key={date}>{date}</option>)}
          </select>
        </label>
      </section>

      <section className={`completeness ${report.completeness.status}`} aria-labelledby="completeness-title">
        <div>
          <span className="status-badge">{humanize(report.completeness.status)} report</span>
          <h2 id="completeness-title">Coverage is {report.completeness.status === "zero_activity" ? "zero activity" : report.completeness.status}.</h2>
          <p>{report.completeness.explanation}</p>

        </div>
        <details><summary>Coverage details</summary><p>Cutoff: 6:00 PM America/New_York. Duplicate deliveries excluded.</p><div className="metric-grid" aria-label="Report reconciliation counts">
          <Metric label="Expected" value={counts.expected} />
          <Metric label="Received" value={counts.received} />
          <Metric label="Analyzed" value={counts.analyzed} />
          <Metric label="Failed" value={counts.failed} />
          <Metric label="Missing" value={counts.missing} />
          <Metric label="Late" value={counts.late} />
        </div></details>
      </section>

      {counts.failed > 0 && (
        <aside className="warning-strip" aria-label="Processing failure warning">
          <b>{counts.failed} call did not produce a reviewable result.</b>
          <span>Coverage is incomplete. An operator can inspect the failure.</span>
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
                    <details><summary>Analysis details</summary><dl className="item-meta">
                      {item.category && <><dt>Category</dt><dd>{humanize(item.category)}</dd></>}
                      {item.confidence && <><dt>Confidence</dt><dd>{humanize(item.confidence)}</dd></>}
                      {item.responsible_role && <><dt>Responsible role</dt><dd>{humanize(item.responsible_role)}</dd></>}
                      {item.suggested_timing && <><dt>Suggested timing</dt><dd>{item.suggested_timing}</dd></>}
                    </dl></details>
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

