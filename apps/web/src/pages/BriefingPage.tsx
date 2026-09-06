import { type ReactNode, useEffect, useState } from "react";
import { apiRequest } from "../api";
import type { DailyBriefing, DemoPrincipal } from "../types";
import { humanize, RequestState, longDate } from "../shared";

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
  const evidencePath = (callId: string, segmentId: string): string => `/calls/${callId}?briefing=${briefing.business_date}#${segmentId}`;
  const labels = { caller_request: "Caller requested", staff_promise: "Staff promised", analysis_suggestion: "Consider reviewing" };
  return <div className="morning-briefing">
    <section className="briefing-heading">
      <div className="eyebrow">Your morning call briefing</div>
      <h1>Calls from {longDate(briefing.business_date)}</h1>
      {briefing.simulated_morning && <p>Simulated morning: {longDate(briefing.simulated_morning)} — reviewing {longDate(briefing.business_date)}.</p>}
      <p>America/New_York · Invented conversations for engineering review.</p>
      {briefing.scenario_version && <small>Dataset: {briefing.scenario_version}</small>}
      <form onSubmit={(event) => { event.preventDefault(); const value = new FormData(event.currentTarget).get("date"); if (typeof value === "string" && value) window.location.assign(`/briefing/${value}`); }}>
        <label htmlFor="briefing-date">Review another date</label>{" "}
        <input id="briefing-date" name="date" type="date" defaultValue={briefing.business_date} required />{" "}<button type="submit">Open day</button>
      </form>
      <a href={`/months/${briefing.business_date.slice(0, 7)}`}>Browse month history</a>{" · "}<a href={`/reports/${briefing.business_date}`}>Detailed coverage report</a>
    </section>
    <section className="briefing-coverage" aria-label="Call coverage">
      <p><strong>{briefing.calls.length} received {briefing.calls.length === 1 ? "call" : "calls"}.</strong> {briefing.coverage_explanation}</p>
      {counts && <p>{counts.analyzed} analyzed · {counts.failed} received with failed analysis · {counts.missing} expected but missing · {counts.late} late · {counts.duplicate_deliveries} duplicate deliveries counted once.</p>}
      {!!counts?.missing && <p>Expected input has not arrived. There is no recording to retry and no recap to infer.</p>}
      {!!counts?.failed && <p>Some received calls have no usable result. <a href="/failures">Inspect processing failures</a> for attempt history and permitted recovery.</p>}
      {briefing.late_calls.map((late) => <p key={late.call_id}>Late arrival · {late.synthetic_reference}: occurred {new Date(briefing.calls.find((call) => call.call_id === late.call_id)?.occurred_at ?? late.received_at).toLocaleString("en-US", { timeZone: "America/New_York", timeZoneName: "short" })}; arrived {new Date(late.received_at).toLocaleString("en-US", { timeZone: "America/New_York", timeZoneName: "short" })}; coverage cutoff {briefing.cutoff_at && new Date(briefing.cutoff_at).toLocaleString("en-US", { timeZone: "America/New_York", timeZoneName: "short" })}.</p>)}
      {briefing.calls.length === 0 && briefing.latest_activity_date && <a href={`/briefing/${briefing.latest_activity_date}`}>Latest earlier day with activity: {longDate(briefing.latest_activity_date)}</a>}
    </section>
    <section className="briefing-attention" aria-labelledby="briefing-attention-title">
      <h2 id="briefing-attention-title">May need attention</h2>
      <p>These are statements and suggestions to review. Reviewing an analysis does not complete a callback or other action.</p>
      {attention.length === 0 && <p>No supported attention items are available{briefing.completeness?.status === "complete" || briefing.completeness?.status === "zero_activity" ? "." : "; incomplete coverage is not an all-clear."}</p>}
      {attention.map((call) => <div className="briefing-attention-item" key={call.call_id}>
        <a href={`#call-${call.call_id}`}>{call.detail?.identity_label ?? "Caller not identified"} · Go to recap</a>
        {call.attention.map((item, index) => <p key={index}><strong>{labels[item.kind]}:</strong> {item.reason}{" "}{item.evidence[0] && <a href={evidencePath(call.call_id, item.evidence[0].segment_id)}>Supporting passage</a>}</p>)}
      </div>)}
    </section>
    <section aria-labelledby="all-calls-title"><h2 id="all-calls-title">All calls, in time order</h2>
      {briefing.calls.map((call, index) => <article className="briefing-recap" id={`call-${call.call_id}`} tabIndex={-1} key={call.call_id}>
        <div className="eyebrow">Call {index + 1} · {new Date(call.occurred_at).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" })}</div>
        <h3>{call.detail?.identity_label ?? "Caller not identified"}</h3>
        {call.detail ? <>
          {call.detail.identity_label && <small>Name stated in conversation; identity not independently verified.</small>}
          {call.detail.language === "es" && <p className="language-note">English paraphrase of a Spanish conversation. Original Spanish evidence is preserved.</p>}
          <p className="recap-summary">{call.detail.summary}</p>
          {call.attention.map((item, number) => <p key={number}><strong>{labels[item.kind]}:</strong> {item.reason}</p>)}
          {call.detail.uncertainty.length > 0 && <p><strong>Unclear:</strong> {call.detail.uncertainty.join(" ")}</p>}
          <p><a href={`/calls/${call.call_id}?briefing=${briefing.business_date}`}>Inspect call and assess findings</a> · {call.detail.review_history.length} saved assessments</p>
          <div className="briefing-evidence">{call.detail.transcript_segments.map((segment, number) => <a key={segment.segment_id} href={evidencePath(call.call_id, segment.segment_id)}>Passage {number + 1} · {humanize(segment.speaker)}</a>)}</div>
        </> : <p>Result unavailable for this received call. {call.unavailable_reason} No conversation recap can be provided.</p>}
      </article>)}
    </section>
  </div>;
}

