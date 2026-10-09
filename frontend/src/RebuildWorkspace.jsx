import { useEffect, useState } from "react";
import ChatLearningPage from "./ChatLearningPage";
import TournamentArena from "./TournamentArena";
import OperationsWorkspace from "./OperationsWorkspace";
import "./chat-learning.css";

export default function RebuildWorkspace() {
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(window.location.hash);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const update = () => setPage(window.location.hash);
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  async function readStatus(value) {
    const response = await fetch("/api/core/status", { headers: { "X-Control-Token": value } });
    if (!response.ok) throw new Error(response.status === 403 ? "Access denied. Check the local control token." : "Backend unavailable.");
    return response.json();
  }
  async function unlock(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { setStatus(await readStatus(draft)); setToken(draft); setDraft(""); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!token) return;
    let active = true;
    const timer = setInterval(() => readStatus(token).then(data => { if (active) {setStatus(data); setError("");} })
      .catch(e => { if (active) {setStatus(null); setError(e.message);} }), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [token]);

  if (!token) return <div className="chat-page"><main className="rebuild-login">
    <h1>NexusAI</h1><p className="rebuild-warning">Controlled rebuild / trading disabled</p>
    <form onSubmit={unlock}><label>Local control token<input type="password" autoComplete="off" value={draft} onChange={e => setDraft(e.target.value)} required /></label>
      <button disabled={busy}>{busy ? "Checking..." : "Unlock workspace"}</button></form>
    {error && <p role="alert" className="chat-error">{error}</p>}
  </main></div>;

  if (page.startsWith("#/chat-learning")) return <ChatLearningPage token={token} />;
  if (page.startsWith("#/tournament")) return <TournamentArena token={token} />;
  if (!page.startsWith("#/rebuild")) return <OperationsWorkspace token={token} page={page} onLock={() => {setToken("");setStatus(null);}} />;
  return <div className="chat-page">
    <nav className="chat-nav"><a href="#/">NEXUS<span>AI</span></a><a href="#/" aria-current="page">Rebuild status</a><a href="#/chat-learning">Historical review</a><a href="#/tournament">Strategy Tournament</a>
      <button onClick={() => {setToken(""); setStatus(null);}}>Lock workspace</button></nav>
    <main>
      <div className="chat-heading"><div><h1>NexusAI Core</h1><p>Controlled rebuild / demo-only target</p></div><strong className="rebuild-warning">{status?.halt?.state || "UNAVAILABLE"}</strong></div>
      <p className="rebuild-warning">Execution disabled. Existing broker positions have not been closed or reconciled.</p>
      {error && <p role="alert" className="chat-error">{error}</p>}
      <dl className="chat-stats rebuild-stats"><div><dt>Broker equity</dt><dd>Unavailable</dd></div><div><dt>Confirmed P&amp;L</dt><dd>Unavailable</dd></div><div><dt>Active agents</dt><dd>{status?.agents_running ?? "Unknown"}</dd></div><div><dt>Qualification</dt><dd>Not qualified</dd></div></dl>
      <section className="rebuild-section"><h2>Lifecycle ledger</h2><dl className="rebuild-ledger">{Object.entries(status?.counts || {}).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl></section>
      <section className="rebuild-section"><h2>Execution gates</h2><table className="rebuild-table"><thead><tr><th>Workstream</th><th>Status</th></tr></thead><tbody>
        <tr><td>Parser and source integrity</td><td>Local integrity checks passed</td></tr>
        <tr><td>Durable identity</td><td>Identity and crash checks passed</td></tr>
        <tr><td>Risk, execution and recovery</td><td>Blocked / replacement pending</td></tr>
        <tr><td>Research and forward demo</td><td>Not qualified</td></tr>
        <tr><td>ML and automated sources</td><td>Disabled</td></tr>
      </tbody></table></section>
    </main>
  </div>;
}
