import { type ReactNode, type SubmitEvent, useEffect, useRef, useState } from "react";
import { apiRequest } from "../api";
import type { DemoPrincipal, UploadCapabilities, UploadReceipt } from "../types";
import { humanize } from "../shared";

function localDateTimeValue(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

function localSubmissionId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return `browser-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export function UploadPage({ principal }: { principal: DemoPrincipal }): ReactNode {
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

  async function submit(event: SubmitEvent<HTMLFormElement>): Promise<void> {
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

