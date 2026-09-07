import { type ReactNode, useEffect, useState } from "react";
import { apiRequest } from "../api";
import type { DailyBriefing, DemoPrincipal } from "../types";
import { RequestState, longDate } from "../shared";

export function BriefingPage({ principal, selectedDate }: { principal: DemoPrincipal; selectedDate?: string }): ReactNode {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setError(null);
    apiRequest<DailyBriefing>(`/api/briefing${selectedDate ? `?business_date=${selectedDate}` : ""}`, principal)
      .then((result) => { if (active) setBriefing(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Request failed"); });
    return () => { active = false; };
  }, [principal, selectedDate]);
  useEffect(() => {
    if (briefing && window.location.hash) document.getElementById(window.location.hash.slice(1))?.focus();
    if (briefing) {
      window.sessionStorage.setItem("colacci-briefing-return", `/briefing/${briefing.business_date}${window.location.hash}`);
      const remember = (event: MouseEvent): void => {
        const link = (event.target as Element).closest("a");
        const recap = link?.closest(".briefing-recap");
        const linkedCall = link?.getAttribute("href")?.match(/^\/calls\/([A-Za-z0-9]+)\?briefing=/)?.[1];
        const recapId = recap?.id ?? (linkedCall ? `call-${linkedCall}` : null);
        if (recapId) {
          const target = `/briefing/${briefing.business_date}#${recapId}`;
          window.sessionStorage.setItem("colacci-briefing-return", target);
          window.history.replaceState(null, "", target);
        }
      };
      document.addEventListener("click", remember);
      return () => { document.removeEventListener("click", remember); };
    }
    return undefined;
  }, [briefing]);
  if (!briefing || error) return <RequestState loading={!error} error={error} area="morning briefing" />;
  const counts = briefing.completeness?.reconciliation;
  const attention = briefing.calls.filter((call) => call.attention.length > 0);
  const labels = { caller_request: "Caller requested", staff_promise: "Staff promised", analysis_suggestion: "Consider reviewing" };
  return <div className="morning-briefing">
    <section className="briefing-heading">
      <div className="eyebrow">Morning briefing</div>
      <h1>Calls from {longDate(briefing.business_date)}</h1>
      {briefing.simulated_morning && <p className="briefing-context">Simulated morning: {longDate(briefing.simulated_morning)} · New York time</p>}
      <form onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get("date"); if (typeof value === "string" && value) window.location.assign(`/briefing/${value}`); }}>
        <label htmlFor="briefing-date">Review another date</label>{" "}
        <input id="briefing-date" name="date" type="date" defaultValue={briefing.business_date} required />{" "}<button type="submit">Open day</button>
      </form>
    </section>
    <section className="briefing-coverage" aria-label="Call coverage">
      <p><strong>{briefing.calls.length} received {briefing.calls.length === 1 ? "call" : "calls"}</strong> · {briefing.completeness?.status === "complete" ? "Coverage complete" : briefing.completeness?.status === "zero_activity" ? "No calls expected or received" : briefing.completeness ? "Incomplete coverage" : "Coverage unavailable"}
        {attention.length > 0 && <> · {attention.length} may need attention</>}</p>
      {!!counts?.missing && <p className="coverage-warning">{counts.missing} expected {counts.missing === 1 ? "call is" : "calls are"} missing. No recap is available.</p>}
      {!!counts?.failed && <p className="coverage-warning">{counts.failed} received {counts.failed === 1 ? "call has" : "calls have"} no usable analysis.</p>}
      {!!counts?.late && <p className="coverage-warning">{counts.late} late {counts.late === 1 ? "arrival" : "arrivals"} · Coverage changed after the morning cutoff.</p>}
      {!briefing.completeness && <p>Coverage is unavailable for this date; this is not a confirmed empty day.</p>}
      <a href={`/reports/${briefing.business_date}`}>Coverage details</a>
      {briefing.calls.length === 0 && briefing.latest_activity_date && <p><a href={`/briefing/${briefing.latest_activity_date}`}>Latest earlier day with activity: {longDate(briefing.latest_activity_date)}</a></p>}
    </section>
    <section aria-labelledby="all-calls-title"><h2 id="all-calls-title">Conversations</h2>
      {briefing.calls.map((call, index) => <article className="briefing-recap" id={`call-${call.call_id}`} tabIndex={-1} key={call.call_id}>
        <div className="eyebrow">Call {index + 1} · {new Date(call.occurred_at).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" })}</div>
        <h3>{call.detail?.identity_label ?? "Caller not identified"}</h3>
        {call.detail ? <>
          {call.detail.language === "es" && <p className="language-note">Spanish · English recap</p>}
          <p className="recap-summary">{call.detail.summary}</p>
          {call.attention.length > 0 && <div className="briefing-attention-item"><span className="attention-label">May need attention</span>{call.attention.map((item, number) => <p key={number}><strong>{labels[item.kind]}:</strong> {item.reason}</p>)}</div>}
          {call.detail.uncertainty.length > 0 && <p><strong>Unclear:</strong> {call.detail.uncertainty.join(" ")}</p>}
          <a className="open-call" href={`/calls/${call.call_id}?briefing=${briefing.business_date}`}>Open call<span className="sr-only"> {index + 1}</span> →</a>
        </> : <p>Result unavailable for this received call. {call.unavailable_reason} No conversation recap can be provided.</p>}
      </article>)}
    </section>
  </div>;
}

