import { type ReactNode, useEffect, useState } from "react";
import { apiRequest } from "../api";
import type { MonthHistory, DemoPrincipal } from "../types";
import { humanize, briefingReturn, RequestState, Metric } from "../shared";

export function MonthPage({ principal, monthKey = "2026-07" }: { principal: DemoPrincipal; monthKey?: string }): ReactNode {
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
    return <RequestState loading={loading} error={error} area="month history" empty={!loading && !error ? "Month history is unavailable." : undefined} />;
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
  const selectedDay = briefingReturn().match(/\/briefing\/(\d{4}-\d{2}-\d{2})/)?.[1];
  const leadingBlanks = new Date(`${history.year.toString()}-${history.month.toString().padStart(2, "0")}-01T12:00:00Z`).getUTCDay();
  return (
    <>
      <a className="back-link" href={briefingReturn()}>← Return to selected briefing</a>
      <section className="month-heading" aria-labelledby="month-title">
        <div><h1 id="month-title">{history.label}</h1></div>
        <nav className="month-controls" aria-label="Month controls">
          <a href={history.previous_month_path} aria-label="Previous month">← Previous</a>
          <a href={history.next_month_path} aria-label="Next month">Next →</a>
        </nav>
      </section>
      <details className="month-reconciliation"><summary>Monthly coverage details</summary><section className="month-totals" aria-label="Monthly reconciliation">
        <Metric label="Expected" value={totals.expected} /><Metric label="Analyzed" value={totals.analyzed} /><Metric label="Failed" value={totals.failed} /><Metric label="Missing" value={totals.missing} /><Metric label="Late" value={totals.late} />
      </section></details>
      <section className="calendar" aria-label={`${history.label} daily report history`}>
        <div className="calendar-weekdays" aria-hidden="true">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <span key={day}>{day}</span>)}</div>
        <div className="calendar-grid">
          {Array.from({ length: leadingBlanks }, (_, index) => <span className="calendar-blank" key={`blank-${index.toString()}`} />)}
          {history.days.map((day) => (
            <a className={`calendar-day state-${day.state}`} href={`/briefing/${day.business_date}`} key={day.business_date} aria-current={selectedDay === day.business_date ? "date" : undefined} aria-label={`${day.business_date}, ${humanize(day.state)}, expected ${day.expected.toString()}, analyzed ${day.analyzed.toString()}, failed ${day.failed.toString()}, missing ${day.missing.toString()}, late ${day.late.toString()}`}>
              <span className="calendar-date">{Number(day.business_date.slice(-2))}</span>
              <span className="day-state">{day.state === "zero_activity" ? "No calls" : day.state === "complete" ? "Complete" : "Incomplete"}</span>
              {day.state !== "zero_activity" && <small>{day.received} received · {day.analyzed} recaps</small>}
              {day.missing > 0 && <small className="coverage-warning">{day.missing} missing</small>}
              {day.failed > 0 && <small className="coverage-warning">{day.failed} without analysis</small>}
              {day.late > 0 && <small>{day.late} late arrivals</small>}

            </a>
          ))}
        </div>
      </section>
    </>
  );
}

