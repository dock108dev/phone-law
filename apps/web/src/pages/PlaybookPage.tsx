import { type ReactNode, type SubmitEvent, useEffect, useState } from "react";
import { ApiRequestError, apiRequest } from "../api";
import type { DemoPrincipal, Playbook, PlaybookDraftCreate } from "../types";
import { humanize, RequestState } from "../shared";

export function PlaybookPage({ principal }: { principal: DemoPrincipal }): ReactNode {
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
  async function createDraft(event: SubmitEvent<HTMLFormElement>): Promise<void> {
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

