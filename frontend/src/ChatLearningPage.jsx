import { useCallback, useEffect, useState } from "react";
import "./chat-learning.css";

const BASE = "/api/private/chat-imports";
async function archiveRequest(path = "", options = {}) {
  const response = await fetch(BASE + path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Check the import settings.");
  return data;
}

function PrivateImage({ url, alt, token }) {
  const [source, setSource] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let disposed = false;
    let objectUrl;
    setSource(null); setError(false);
    const controller = new AbortController();
    fetch(url, { headers: { "X-Control-Token": token }, signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Image unavailable"); return response.blob(); })
      .then(blob => { if (!disposed) { objectUrl = URL.createObjectURL(blob); setSource(objectUrl); } })
      .catch(e => { if (!disposed && e.name !== "AbortError") setError(true); });
    return () => { disposed = true; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, token]);
  return source ? <a href={source} target="_blank" rel="noreferrer"><img src={source} alt={alt} /></a> : <p>{error ? "Image unavailable" : "Loading image..."}</p>;
}

export default function ChatLearningPage({ token }) {
  const request = useCallback((path = "", options = {}) => archiveRequest(path, {
    ...options, headers: { ...options.headers, "X-Control-Token": token },
  }), [token]);
  const [imports, setImports] = useState([]);
  const [active, setActive] = useState("");
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [kind, setKind] = useState("signal");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [file, setFile] = useState(null);
  const [dateOrder, setDateOrder] = useState("DMY");
  const [utcOffset, setUtcOffset] = useState("300");
  const [group, setGroup] = useState("REDACTED_SOURCE");
  const [correction, setCorrection] = useState(null);
  const [revision, setRevision] = useState(0);
  const current = imports.find(item => item.id === active);
  useEffect(() => { setCorrection(null); }, [selected?.id]);

  const refreshImports = useCallback(async () => {
    const data = await request();
    setImports(data.imports);
    setActive(previous => previous || data.imports[0]?.id || "");
  }, [request]);
  useEffect(() => { refreshImports().catch(e => setError(e.message)); }, [refreshImports]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    setRows([]);
    setSelected(null);
    const timer = setTimeout(() => {
      request(`/${active}/messages?${new URLSearchParams({kind, search, offset, limit: 50})}`, {signal: controller.signal})
        .then(data => { setRows(data.messages); setTotal(data.total); })
        .catch(e => { if (e.name !== "AbortError") setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 150);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [active, kind, search, offset, revision, request]);

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) { setError("Maximum upload size is 100 MB."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const form = new FormData();
      form.append("file", file); form.append("date_order", dateOrder);
      form.append("utc_offset", utcOffset); form.append("group", group);
      const result = await request("", {method: "POST", body: form});
      await refreshImports();
      setActive(result.id); setOffset(0);
      setRevision(value => value + 1);
      setNotice(result.duplicate ? "This export is already in the archive." : `${result.messages} messages imported. ${result.counts.signal} signal candidates found.`);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function approve() {
    setBusy(true); setError("");
    try {
      const result = await request(`/${active}/messages/${selected.id}/approve`, {method: "POST"});
      const updated = result.message;
      setSelected(updated); setRows(items => items.map(item => item.id === updated.id ? updated : item));
      setNotice("Signal added to the learning dataset. Outcome remains unverified.");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function saveCorrection(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const updated = await request(`/${active}/messages/${selected.id}/correct`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(correction)
      });
      setSelected(updated); setRows(items => items.map(item => item.id === updated.id ? updated : item));
      setCorrection(null); setNotice("Correction recorded. Original message preserved.");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return <div className="chat-page">
    <nav className="chat-nav" aria-label="Main navigation"><a href="#/">NEXUS<span>AI</span></a><a href="#/">Rebuild status</a><a href="#/chat-learning" aria-current="page">Historical review</a><a href="#/tournament">Strategy Tournament</a></nav>
    <main>
      <div className="chat-heading"><div><h1>Historical review</h1><p>Historical archive{current ? ` / ${current.group}` : ""}</p></div><span className="rebuild-warning">Execution and training disabled</span></div>
      <fieldset disabled={busy}>
      <form onSubmit={upload} className="chat-upload">
        <label>Chat export (.zip or .txt)<input type="file" accept=".zip,.txt" onChange={e => setFile(e.target.files?.[0] || null)} required /></label>
        <label>Group<input value={group} onChange={e => setGroup(e.target.value)} maxLength={120} required /></label>
        <label>Date order<select value={dateOrder} onChange={e => setDateOrder(e.target.value)}><option value="DMY">Day / month / year</option><option value="MDY">Month / day / year</option></select></label>
        <label>UTC offset (minutes)<input type="number" min="-720" max="840" step="15" value={utcOffset} onChange={e => setUtcOffset(e.target.value)} required /></label>
        <button type="submit" disabled={busy || !file}>{busy ? "Processing..." : "Import chat"}</button>
      </form>
      {error && <div className="chat-error" role="alert">{error}<button type="button" onClick={() => {setError(""); setRevision(value => value + 1); refreshImports().catch(e => setError(e.message));}}>Retry</button></div>}
      {notice && <p className="chat-notice" role="status">{notice}</p>}
      <div className="chat-toolbar"><label>Archive<select value={active} onChange={e => {setActive(e.target.value); setOffset(0);}}><option value="" disabled>Select an import</option>{imports.map(item => <option value={item.id} key={item.id}>{item.filename} ({item.messages} messages)</option>)}</select></label></div>
      {current && <dl className="chat-stats">{[["Messages", current.messages], ["Signal candidates", current.counts.signal], ["Updates", current.counts.update], ["Reported results", current.counts.reported_result], ["Images", current.images]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
      <div className="chat-filters"><label>Show<select value={kind} onChange={e => {setKind(e.target.value); setOffset(0);}}>{[["all", "All messages"], ["signal", "Signals"], ["needs_review", "Needs review"], ["approved", "Approved"], ["update", "Updates"], ["reported_result", "Reported results"], ["cancellation", "Cancellations"], ["media", "Media"], ["discussion", "Discussion"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Search<input type="search" placeholder="Message or sender" value={search} onChange={e => {setSearch(e.target.value); setOffset(0);}} /></label><span>{total} matches</span></div>
      <div className="chat-workspace">
        <section aria-label="Chat messages" className="chat-list">
          {loading ? <p className="chat-empty">Loading messages...</p> : !rows.length ? <p className="chat-empty">{active ? "No messages match these filters." : "No chat archive imported yet."}</p> : rows.map(row => <button type="button" className={`chat-message ${selected?.id === row.id ? "selected" : ""}`} key={row.id} onClick={() => setSelected(row)}>
            <span className="chat-message-meta"><time>{row.local_time}</time><span className={`chat-status ${row.review_status}`}>{row.review_status === "context" ? row.kind.replaceAll("_", " ") : row.review_status.replaceAll("_", " ")}</span></span>
            <strong>{row.symbol || row.sender}{row.signal?.direction ? ` / ${row.signal.direction}` : ""}</strong><span className="chat-excerpt">{row.text}</span>
            {row.available_media.length > 0 && <small>{row.available_media.length} attached image{row.available_media.length > 1 ? "s" : ""}</small>}
          </button>)}
          <div className="chat-pagination"><button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><span>{total ? `${offset + 1}-${Math.min(offset + 50, total)} of ${total}` : "0 messages"}</span><button type="button" disabled={offset + 50 >= total || loading} onClick={() => setOffset(offset + 50)}>Next</button></div>
        </section>
        <section aria-label="Message review" className="chat-detail">
          {!selected ? <p className="chat-empty">No message selected</p> : <>
            <div className="chat-detail-heading"><h2>{selected.symbol || "Message review"}</h2><span>{selected.sender}</span></div>
            <p className="chat-muted">{selected.local_time} / UTC {Number(current?.utc_offset) >= 0 ? "+" : ""}{Number(current?.utc_offset) / 60}</p>
            {selected.signal && <dl className="chat-fields">{[["Direction", selected.signal.direction], ["Entry", selected.signal.entry_price], ["Stop loss", selected.signal.stop_loss], ["Take profit", selected.signal.take_profit_1]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value ?? "Missing"}</dd></div>)}</dl>}
            {selected.reasons.length > 0 && <ul className="chat-warnings">{selected.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
            {selected.parser_review_required && <p className="rebuild-warning">Parser comparison differs from this stored record. Original prices and corrections are preserved.</p>}
            {selected.kind === "signal" && <button type="button" className="chat-approve" disabled={busy || selected.review_status !== "ready"} onClick={approve}>{selected.review_status === "approved" ? "Added to learner" : "Approve for learning"}</button>}
            {selected.kind === "signal" && selected.review_status !== "approved" && !correction && <button type="button" className="chat-correct" onClick={() => setCorrection({entry_price: selected.signal.entry_price ?? "", stop_loss: selected.signal.stop_loss ?? "", take_profit_1: selected.signal.take_profit_1 ?? "", note: ""})}>Correct prices</button>}
            {correction && <form className="chat-correction" onSubmit={saveCorrection}>
              {[["entry_price", "Entry"], ["stop_loss", "Stop loss"], ["take_profit_1", "Take profit"]].map(([key, label]) => <label key={key}>{label}<input type="number" min="0" step="any" required value={correction[key]} onChange={e => setCorrection({...correction, [key]: e.target.value})} /></label>)}
              <label>Source note<input required minLength={5} maxLength={1000} value={correction.note} onChange={e => setCorrection({...correction, note: e.target.value})} /></label>
              <div><button type="submit" disabled={busy}>Save correction</button><button type="button" disabled={busy} onClick={() => setCorrection(null)}>Cancel</button></div>
            </form>}
            {selected.review_history?.length > 0 && <div className="chat-muted">{selected.review_history.map((revision, index) => <p key={index}>Correction {index + 1}: {revision.note}</p>)}</div>}
            {selected.candidate_ids.length > 0 && <p className="chat-muted">{selected.candidate_links_truncated ? "At least " : ""}{selected.candidate_ids.length} possible earlier signal{selected.candidate_ids.length > 1 ? "s" : ""}. Link unconfirmed; outcome unverified.</p>}
            <h3>Original message</h3><pre>{selected.text}</pre>
            {selected.available_media.map(name => <PrivateImage key={name} token={token} url={`${BASE}/${active}/media?${new URLSearchParams({name})}`} alt={`Chart attached to ${selected.local_time}`} />)}
          </>}
        </section>
      </div>
      </fieldset>
    </main>
  </div>;
}
