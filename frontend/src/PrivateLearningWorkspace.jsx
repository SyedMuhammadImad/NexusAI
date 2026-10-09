import { useState, useEffect, useCallback } from "react";

async function apiFetch(path, options = {}) {
  try {
    const response = await fetch("/api" + path, options);
    const data = await response.json();
    if (!response.ok) return { detail: typeof data.detail === "string" ? data.detail : "Request failed" };
    return data;
  } catch { return { detail: "Backend unavailable. Please retry." }; }
}

function Panel({ title, children }) {
  return <section className="private-learning-panel"><h3>{title}</h3><div>{children}</div></section>;
}

function PrivateSignalsPanel({ signals }) {
  const rows = signals || [];
  return (
    <Panel title="Private Signals">
      <div className="overflow-y-auto max-h-56 font-mono text-[11px]">
        {rows.map(signal => (
          <div key={signal.signal_id} className="grid grid-cols-[1fr_auto_auto] gap-2 px-4 py-2 border-b border-zinc-900 hover:bg-zinc-900/40">
            <div className="min-w-0">
              <div className="text-zinc-200 truncate">
                {signal.instrument || "--"} {signal.direction || ""}
              </div>
              <div className="text-zinc-600 truncate">
                SL {signal.stop_loss ?? "--"} / TP {signal.take_profit_1 ?? signal.take_profit ?? "--"}
              </div>
            </div>
            <div className={signal.validation_status === "ACCEPTED" ? "text-emerald-400" : "text-red-400"}>
              {signal.validation_status || "--"}
            </div>
            <div className="text-zinc-500">
              {signal.parser_confidence ? `${(signal.parser_confidence * 100).toFixed(0)}%` : "--"}
            </div>
          </div>
        ))}
        {!rows.length && (
          <div className="text-center text-zinc-600 py-8">No private signals recorded</div>
        )}
      </div>
    </Panel>
  );
}

function TraderLearningPanel({ learning }) {
  const totals = learning?.totals || {};
  const recent = learning?.recent_signals || [];
  return (
    <Panel title="Trader Learning">
      <div className="p-4 space-y-3 font-mono text-xs">
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Signals</div>
            <div className="text-zinc-200">{totals.tracked_signals ?? 0}</div>
          </div>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Raw Local</div>
            <div className="text-zinc-200">{totals.raw_examples ?? 0}</div>
          </div>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Closed</div>
            <div className="text-zinc-200">{totals.closed_signals ?? 0}</div>
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-zinc-800 pt-3">
          <span className="text-zinc-500">Mode</span>
          <span className="text-amber-400">{learning?.learning_mode || "observation_only"}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-zinc-500">Shadow Ready</span>
          <span className={learning?.shadow_ready ? "text-emerald-400" : "text-zinc-500"}>
            {learning?.shadow_ready ? "YES" : "NO"}
          </span>
        </div>
        <div className="text-[11px] text-zinc-500 leading-relaxed">
          {learning?.recommendation || "Waiting for imported or observed provider signals."}
        </div>
        {recent.length > 0 && (
          <div className="space-y-1 border-t border-zinc-800 pt-3">
            {recent.slice(0, 4).map(signal => (
              <div key={signal.signal_id} className="flex items-center justify-between gap-2">
                <span className="text-zinc-300 truncate">{signal.instrument || "--"} {signal.direction || ""}</span>
                <span className="text-zinc-600">{signal.validation_status || "--"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function ImageExecutionUploadPanel() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const parseImage = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    const data = await apiFetch("/private/signals/image/parse", {
      method: "POST",
      body,
    });
    setBusy(false);
    if (data?.detail) {
      setError(String(data.detail));
      return;
    }
    setResult(data);
  };

  const submitImageSignal = async () => {
    if (!result?.image_id) return;
    setBusy(true);
    setError("");
    const data = await apiFetch("/private/signals/image/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: result.image_id }),
    });
    setBusy(false);
    if (data?.detail) {
      setError(String(data.detail));
      return;
    }
    setResult(prev => ({ ...prev, submit_result: data }));
  };

  const signal = result?.signal || {};
  const parsed = result?.status === "PARSED";

  return (
    <Panel title="Execution Upload">
      <div className="p-4 space-y-3 font-mono text-xs">
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          onChange={e => {
            setFile(e.target.files?.[0] || null);
            setResult(null);
            setError("");
          }}
          className="block w-full text-[11px] text-zinc-400 file:mr-3 file:rounded file:border file:border-zinc-700 file:bg-zinc-900 file:px-3 file:py-1.5 file:text-zinc-300 hover:file:bg-zinc-800"
        />
        <button
          onClick={parseImage}
          disabled={!file || busy}
          className="w-full py-2 bg-cyan-900/30 border border-cyan-500/30 text-cyan-300 rounded hover:bg-cyan-900/50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Working..." : "Parse Image"}
        </button>

        {error && (
          <div className="text-[11px] text-red-300 bg-red-950/30 border border-red-900/50 rounded p-2">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-3 border-t border-zinc-800 pt-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
                <div className="text-zinc-600">Symbol</div>
                <div className="text-zinc-200">{signal.instrument || "--"}</div>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
                <div className="text-zinc-600">Side</div>
                <div className={signal.direction === "BUY" ? "text-emerald-400" : "text-red-400"}>
                  {signal.direction || "--"}
                </div>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
                <div className="text-zinc-600">Stop</div>
                <div className="text-zinc-200">{signal.stop_loss ?? "--"}</div>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
                <div className="text-zinc-600">Target</div>
                <div className="text-zinc-200">{signal.take_profit_1 ?? "--"}</div>
              </div>
            </div>
            <div className="text-[11px] text-zinc-500 break-words">
              {result.normalized_text || "--"}
            </div>
            {result.rejection_reasons?.length > 0 && (
              <div className="text-[11px] text-amber-300">
                {result.rejection_reasons.join("; ")}
              </div>
            )}
            <button
              onClick={submitImageSignal}
              disabled={!parsed || busy || result.submit_result}
              className="w-full py-2 bg-emerald-900/30 border border-emerald-500/30 text-emerald-300 rounded hover:bg-emerald-900/50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {result.submit_result ? "Submitted" : "Submit To Risk"}
            </button>
            {result.submit_result && (
              <div className="text-[11px] text-zinc-400">
                {result.submit_result.status || "--"}
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

function BulkLearningUploadPanel({ onDone }) {
  const [files, setFiles] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const upload = async () => {
    if (!files.length) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    files.slice(0, 50).forEach(file => body.append("files", file));
    const data = await apiFetch("/private/signals/image/bulk-learning", {
      method: "POST",
      body,
    });
    setBusy(false);
    if (data?.detail) {
      setError(String(data.detail));
      return;
    }
    setResult(data);
    onDone?.();
  };

  return (
    <Panel title="Learning Upload">
      <div className="p-4 space-y-3 font-mono text-xs">
        <input
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp,image/gif"
          onChange={e => {
            setFiles(Array.from(e.target.files || []));
            setResult(null);
            setError("");
          }}
          className="block w-full text-[11px] text-zinc-400 file:mr-3 file:rounded file:border file:border-zinc-700 file:bg-zinc-900 file:px-3 file:py-1.5 file:text-zinc-300 hover:file:bg-zinc-800"
        />
        <button
          onClick={upload}
          disabled={!files.length || busy}
          className="w-full py-2 bg-zinc-900 border border-zinc-700 text-zinc-200 rounded hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Importing..." : `Import ${files.length || ""} For Learning`}
        </button>
        {error && (
          <div className="text-[11px] text-red-300 bg-red-950/30 border border-red-900/50 rounded p-2">
            {error}
          </div>
        )}
        {result && (
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
              <div className="text-zinc-600">Processed</div>
              <div className="text-zinc-200">{result.processed}</div>
            </div>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
              <div className="text-zinc-600">Parsed</div>
              <div className="text-emerald-400">{result.parsed_count}</div>
            </div>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
              <div className="text-zinc-600">Rejected</div>
              <div className="text-amber-400">{result.rejected_count}</div>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

function ImitationModelPanel({ model, onTrained }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const metrics = result?.metrics || model?.metrics || {};
  const dataset = result?.dataset || model?.dataset || {};

  const train = async () => {
    setBusy(true);
    setError("");
    const data = await apiFetch("/private/trader-learning/train", { method: "POST" });
    setBusy(false);
    if (data?.detail) {
      setError(String(data.detail));
      return;
    }
    setResult(data);
    onTrained?.();
  };

  return (
    <Panel title="Imitation Model">
      <div className="p-4 space-y-3 font-mono text-xs">
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Trained</div>
            <div className={model?.trained || result?.trained ? "text-emerald-400" : "text-zinc-500"}>
              {model?.trained || result?.trained ? "YES" : "NO"}
            </div>
          </div>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Examples</div>
            <div className="text-zinc-200">{dataset.examples ?? 0}</div>
          </div>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Exec</div>
            <div className="text-amber-400">OFF</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Train Acc</div>
            <div className="text-zinc-300">{metrics.train_accuracy ?? "--"}</div>
          </div>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded p-2">
            <div className="text-zinc-600">Val Acc</div>
            <div className="text-zinc-300">{metrics.validation_accuracy ?? "--"}</div>
          </div>
        </div>
        {(result?.reason || model?.reason) && (
          <div className="text-[11px] text-zinc-500 leading-relaxed">{result?.reason || model?.reason}</div>
        )}
        {error && (
          <div className="text-[11px] text-red-300 bg-red-950/30 border border-red-900/50 rounded p-2">
            {error}
          </div>
        )}
        <button
          onClick={train}
          disabled={busy}
          className="w-full py-2 bg-cyan-900/30 border border-cyan-500/30 text-cyan-300 rounded hover:bg-cyan-900/50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Training..." : "Train Shadow Model"}
        </button>
      </div>
    </Panel>
  );
}


export default function PrivateLearningWorkspace({ revision }) {
  const [signals, setSignals] = useState([]);
  const [learning, setLearning] = useState(null);
  const [model, setModel] = useState(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    const [journal, summary, status] = await Promise.all([
      apiFetch("/private/journal/signals?limit=12"),
      apiFetch("/private/trader-learning/summary?limit=12"),
      apiFetch("/private/trader-learning/model"),
    ]);
    setError(journal.detail || summary.detail || status.detail || "");
    if (journal.signals) setSignals(journal.signals);
    if (summary.totals) setLearning(summary);
    if (!status.detail) setModel(status);
  }, []);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 5000); return () => clearInterval(timer); }, [refresh, revision]);
  return <section className="private-learning-workspace" aria-label="Private signals and learning">
    <h2>Private signals and learning</h2>
    {error && <p role="alert" className="chat-error">{error}</p>}
    <div className="private-learning-grid">
      <PrivateSignalsPanel signals={signals} />
      <TraderLearningPanel learning={learning} />
      <ImitationModelPanel model={model} onTrained={refresh} />
      <ImageExecutionUploadPanel />
      <BulkLearningUploadPanel onDone={refresh} />
    </div>
  </section>;
}

