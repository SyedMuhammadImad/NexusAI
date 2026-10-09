import { useEffect, useState } from "react";
import { Play, Pause, RotateCcw, ShieldOff, Check, ChevronRight } from "lucide-react";
import "./tournament.css";

const BASE = "/api/core/tournament";
const COLORS = ["#67dac5", "#ebbb60", "#f38d99", "#a9c6f2"];
const number = (v, suffix = "") => v == null ? "—" : `${Number(v).toFixed(2)}${suffix}`;
const time = v => v ? new Date(v).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "—";
const label = v => v?.replaceAll("_", " ") || "—";
function Badge({ value }) { return <span className={`arena-badge ${value}`}>{label(value)}</span>; }

function Curve({ snapshot, selected, strategies, split }) {
  const series = selected.map(id => ({ id, points: (snapshot?.curves[id] || []).filter(p => p.r != null) }));
  const points = series.flatMap(s => s.points);
  const values = points.map(p => Number(p.r));
  const low = Math.min(-1, ...values), high = Math.max(1, ...values);
  const first = points.length ? Math.min(...points.map(p => Date.parse(p.at))) : 0;
  const last = Math.max(first + 1, ...points.map(p => Date.parse(p.at)));
  const x = at => 48 + (Date.parse(at) - first) / (last - first) * 800;
  const y = r => 18 + (high - Number(r)) / (high - low) * 180;
  return <div className="arena-chart"><svg viewBox="0 0 880 230" role="img" aria-label="Cumulative research R chart">
    {[low, 0, high].map((v,i) => <g key={i}><line x1="48" x2="848" y1={y(v)} y2={y(v)} stroke="#37393b"/><text x="4" y={y(v)+4} fill="#a1a1aa" fontSize="11">{v.toFixed(1)}R</text></g>)}
    {Date.parse(split) <= last && <g><line x1={x(split)} x2={x(split)} y1="18" y2="198" stroke="#ebbb60" strokeDasharray="4 5"/><text x={Math.min(x(split)+6,790)} y="15" fill="#ebbb60" fontSize="11">OOS</text></g>}
    {series.map((s,i) => <g key={s.id}><polyline fill="none" stroke={COLORS[i%4]} strokeWidth="2" points={s.points.map(p => `${x(p.at)},${y(p.r)}`).join(" ")}/>{s.points.length===1 && <circle cx={x(s.points[0].at)} cy={y(s.points[0].r)} r="3" fill={COLORS[i%4]}/>}</g>)}
    <text x="48" y="222" fill="#a1a1aa" fontSize="11">{points[0]?.at.slice(0,10)}</text><text x="848" y="222" textAnchor="end" fill="#a1a1aa" fontSize="11">{snapshot?.at.slice(0,10)}</text>
  </svg><div className="arena-legend">{series.map((s,i) => <span key={s.id}><i style={{background:COLORS[i%4]}}/>{strategies[s.id]?.name}</span>)}</div></div>;
}

export default function TournamentArena({ token }) {
  const [meta,setMeta]=useState(null), [snapshot,setSnapshot]=useState(null), [error,setError]=useState("");
  const [index,setIndex]=useState(0), [playing,setPlaying]=useState(false), [speed,setSpeed]=useState("1x");
  const [instrument,setInstrument]=useState("XAGUSD"), [frame,setFrame]=useState("1H"), [family,setFamily]=useState("ALL");
  const [survivors,setSurvivors]=useState(false), [selected,setSelected]=useState("p6-15"), [curves,setCurves]=useState(["p6-15"]);
  const [detail,setDetail]=useState(null), [reload,setReload]=useState(0);
  async function get(path, signal) {
    const res=await fetch(BASE+path,{headers:{"X-Control-Token":token},signal});
    if(!res.ok) throw new Error(res.status===403?"Workspace access expired.":"Verified tournament evidence unavailable.");
    return res.json();
  }
  useEffect(()=>{ const c=new AbortController();
    get("/summary",c.signal).then(setMeta).catch(e=>{if(e.name!=="AbortError")setError(e.message);});
    return ()=>c.abort();
  },[token,reload]);
  useEffect(()=>{ if(!meta)return; const c=new AbortController(); setError("");setSnapshot(null);setDetail(null);
    get(`/snapshot?index=${index}&instrument=${instrument}&timeframe=${frame}`,c.signal).then(data=>{
      if(data.projection_id!==meta.projection_id)throw new Error("Evidence changed. Reload the tournament.");
      setSnapshot(data);
    }).catch(e=>{if(e.name!=="AbortError"){setError(e.message);setPlaying(false);}});
    return ()=>c.abort();
  },[meta,index,instrument,frame,token]);
  useEffect(()=>{if(!meta||!snapshot||!playing)return;
    if(index>=meta.timeline.length-1){setPlaying(false);return;}
    const timer=setTimeout(()=>setIndex(i=>i+1),{"1x":1000,"5x":200,"20x":50,MAX:16}[speed]);
    return ()=>clearTimeout(timer);
  },[snapshot,playing,speed,index,meta]);
  useEffect(()=>{if(!snapshot)return;const c=new AbortController();setDetail(null);
    get(`/inspector?cell_id=${selected}:${instrument}:${frame}&index=${index}`,c.signal).then(setDetail).catch(e=>{if(e.name!=="AbortError")setError(e.message);});
    return ()=>c.abort();
  },[snapshot,selected,token]);
  const all=snapshot?.rows||[];
  const filtered=all.filter(r=>family==="ALL"||meta?.strategies[r.strategy_id].family===family);
  const terminal=r=>["REJECTED","INSUFFICIENT_EVIDENCE","EXCLUDED"].includes(r.status);
  const rows=survivors?filtered.filter(r=>!terminal(r)):filtered;
  const withdrawn=filtered.filter(terminal);
  const current=all.find(r=>r.strategy_id===selected);
  const count=status=>all.filter(r=>status.includes(r.status)).length;
  const choose=id=>{setSelected(id);setCurves(ids=>ids.includes(id)?ids:[id,...ids].slice(0,4));};
  const last=meta?meta.timeline.length-1:0;
  const step=i=>{setPlaying(false);setIndex(i);};
  return <div className="chat-page arena">
    <nav className="chat-nav"><a href="#/">NEXUS<span>AI</span></a><a href="#/">Rebuild status</a><a href="#/chat-learning">Historical review</a><a href="#/tournament" aria-current="page">Strategy Tournament</a></nav>
    <main>
      <header className="arena-heading"><div><p className="arena-eyebrow">RESEARCH / P7</p><h1>Strategy Tournament</h1><p>Historical research replay · parameters frozen · no OOS tuning</p></div><span className="arena-safety"><ShieldOff size={16}/>BROKER EXECUTION HARD DISABLED</span></header>
      <div className="arena-warning">SHORT_SAMPLE_RESEARCH_ONLY <span>Commission NOT_INCLUDED · 02 Sep – 27 Nov 2025 · not execution qualification</span></div>
      {error && <div role="alert" className="chat-error">{error}<button onClick={()=>{setError("");setReload(n=>n+1);}}>Retry</button></div>}
      {!meta && !error && <p role="status">Loading verified research evidence…</p>}
      {meta && <>
      <section className="arena-timeline" aria-label="Replay controls">
        <div className="arena-replay-bar"><button aria-label={playing?"Pause":"Play"} title={playing?"Pause":"Play"} onClick={()=>setPlaying(p=>!p)} disabled={index===last}><>{playing?<Pause size={18}/>:<Play size={18}/>}</></button>
          <button aria-label="Restart" title="Restart" onClick={()=>step(0)}><RotateCcw size={17}/></button>
          <label>Speed<select aria-label="Replay speed" value={speed} onChange={e=>setSpeed(e.target.value)}>{["1x","5x","20x","MAX"].map(v=><option key={v}>{v}</option>)}</select></label>
          <div className="arena-clock"><strong data-testid="replay-time">{time(meta.timeline[index])}</strong><Badge value={snapshot?.phase||"LOADING"}/></div>
          <button aria-label="Final snapshot" title="Final snapshot" onClick={()=>step(last)}><ChevronRight size={18}/><ChevronRight size={18}/></button>
        </div>
        <div className="arena-slider"><input aria-label="Tournament time" type="range" min="0" max={last} value={index} onChange={e=>step(Number(e.target.value))}/><i style={{left:`${meta.timeline.indexOf(meta.configuration.split)/last*100}%`}} title="Development / OOS boundary"/></div>
        <div className="arena-range"><span>DEVELOPMENT · 70% nominal</span><span>OOS starts {time(meta.configuration.split)} · 30% nominal</span></div>
      </section>
      <div className="arena-filters"><label>Instrument<select aria-label="Instrument" value={instrument} onChange={e=>{setPlaying(false);setInstrument(e.target.value);}}>{["XAUUSD","XAGUSD","USOIL"].map(v=><option key={v}>{v}</option>)}</select></label>
        <label>Timeframe<select aria-label="Timeframe" value={frame} onChange={e=>{setPlaying(false);setFrame(e.target.value);}}><option>1H</option><option>4H</option></select></label>
        <label>Family<select aria-label="Family" value={family} onChange={e=>setFamily(e.target.value)}><option value="ALL">All families</option>{[...new Set(meta.configuration.catalogue.map(s=>s.family))].map(v=><option key={v} value={v}>{label(v)}</option>)}</select></label>
        <label className="arena-toggle"><input type="checkbox" checked={survivors} onChange={e=>setSurvivors(e.target.checked)}/>Active / qualified only</label>
        <span>{instrument} · {frame} · independent research cells</span></div>
      <dl className="arena-counters">{[["CATALOGUE",20],["ACTIVE",count(["ACTIVE","AT_RISK"])],["REJECTED",count(["REJECTED"])],["QUALIFIED",count(["RESEARCH_QUALIFIED"])],["INSUFFICIENT",count(["INSUFFICIENT_EVIDENCE"])],["EXCLUDED",count(["EXCLUDED"])]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{snapshot?v:"—"}</dd></div>)}</dl>
      <div className="arena-family-counts">{[...new Set(meta.configuration.catalogue.map(s=>s.family))].map(f=>{const rs=all.filter(r=>meta.strategies[r.strategy_id].family===f);return <span key={f}>{label(f)} <strong>{rs.filter(r=>!terminal(r)).length}/{rs.length}</strong> active/qualified · {rs.filter(r=>r.status==="REJECTED").length} rejected</span>;})}</div>
      {snapshot?.phase==="FINAL" && <section className="arena-final"><h2>{meta.final_counts.RESEARCH_QUALIFIED===0?"NO_STRATEGY_RESEARCH_QUALIFIED":"Final research qualification"}</h2><p>Across all 114 evaluated cells: {meta.final_counts.RESEARCH_QUALIFIED} qualified · {meta.final_counts.REJECTED} rejected · {meta.final_counts.INSUFFICIENT_EVIDENCE} insufficient evidence. 66 cells excluded before evaluation; no pooled qualification.</p></section>}
      <section className="arena-performance"><div className="arena-section-title"><h2>Cumulative research R</h2><span>Development + OOS · independent curves, not a portfolio</span></div><Curve snapshot={snapshot} selected={curves} strategies={meta.strategies} split={meta.configuration.split}/>
        <div className="arena-compare">{curves.map(id=><button key={id} onClick={()=>setCurves(xs=>xs.filter(x=>x!==id))} title="Remove curve"><Check size={13}/>{meta.strategies[id]?.name}</button>)}</div>
      </section>
      <div className="arena-body"><section className="arena-board"><div className="arena-section-title"><h2>Strategy field</h2><span>Performance rank ≠ qualification · {rows.length} visible</span></div>
        <div className="arena-table-scroll"><table><thead><tr>{["Rank","Strategy / family","Status","Trades / open","W / L","Total R","Expectancy","PF","Max DD","OOS resolved"].map(v=><th key={v}>{v}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r.cell_id} className={`${selected===r.strategy_id?"selected":""} ${terminal(r)?"withdrawn":""}`}><td>{all.indexOf(r)+1}</td><td><button className="arena-strategy" onClick={()=>choose(r.strategy_id)}><strong>{meta.strategies[r.strategy_id].name}</strong><small>{label(meta.strategies[r.strategy_id].family)}</small></button></td><td><Badge value={r.status}/></td><td>{r.metrics?.research_trade_count??"—"} / {r.open_trades??"—"}</td><td>{r.metrics?`${r.metrics.outcomes.WIN} / ${r.metrics.outcomes.LOSS}`:"—"}</td><td>{number(r.metrics?.total_r)}</td><td>{number(r.metrics?.expectancy_r)}</td><td>{number(r.metrics?.profit_factor)}</td><td>{number(r.metrics?.max_drawdown_r)}</td><td>{r.oos?.resolved_barrier_denominator??"—"}</td></tr>)}</tbody></table></div>
        {!snapshot && <p role="status">Loading snapshot…</p>}{snapshot&&rows.length===0&&<p>No strategies in this filtered field.</p>}
        <section className="arena-withdrawn"><h3>Retained history <span>{withdrawn.length}</span></h3>{withdrawn.length===0?<p>No final exits at this research timestamp.</p>:withdrawn.map(r=><button key={r.cell_id} onClick={()=>choose(r.strategy_id)}><span>{meta.strategies[r.strategy_id].name}</span><Badge value={r.status}/><small>{r.reason||r.reasons?.join(" · ")}</small></button>)}</section>
      </section>
      <aside className="arena-inspector"><p className="arena-eyebrow">STRATEGY INSPECTOR</p><h2>{meta.strategies[selected]?.name}</h2><p>{meta.strategies[selected]?.version} · {instrument} · {frame}</p><Badge value={current?.status||"LOADING"}/>
        <h3>OOS qualification gates</h3><div className="arena-gates">{Object.entries(current?.gates||{}).map(([k,g])=><div key={k}><strong>{label(k)}</strong><Badge value={g.status==="UNKNOWN"?"INSUFFICIENT_EVIDENCE":g.status}/><small>{g.evidence.value!=null?`${number(g.evidence.value)} / threshold ${g.evidence.threshold}`:g.evidence.total!=null?`${g.evidence.total} total / 50 · ${g.evidence.oos} OOS / 20`:g.evidence.pf_check||"Verified evidence contract"}</small></div>)}</div>
        {current?.status==="EXCLUDED"&&<p>{current.reason}</p>}
        {detail&&<><h3>Development / OOS</h3><dl className="arena-detail-metrics">{["expectancy_r","profit_factor","win_rate","total_r","max_drawdown_r"].map(k=><div key={k}><dt>{label(k)}</dt><dd>{number(detail.state.development?.[k])} / {number(detail.state.oos?.[k])}</dd></div>)}</dl>
        <details><summary>Frozen parameters & provenance</summary><pre>{JSON.stringify({version:detail.strategy.version,parameters:detail.strategy.parameters,instruments:detail.strategy.instruments,timeframes:detail.strategy.timeframes,cost_model:detail.cost_model,dataset_ids:detail.datasets.filter(d=>d.instrument===instrument).map(d=>d.dataset_id)},null,2)}</pre></details>
        <details><summary>Robustness</summary>{detail.robustness?<div>{Object.entries(detail.robustness).map(([k,v])=><p key={k}>{label(k)}: {number((v.metrics||v).expectancy_r)}R expectancy / {number((v.metrics||v).max_drawdown_r)}R DD</p>)}</div>:<p>Pending final snapshot.</p>}</details>
        <details><summary>Correlation & limitations</summary><p>{detail.correlation?.status||"Pending final snapshot"}</p>{detail.correlation?.clusters.map((g,i)=><p key={i}>{g.join(" · ")}</p>)}<ul>{detail.limitations.map(l=><li key={l}>{l}</li>)}</ul></details></>}
      </aside></div>
      <section className="arena-events"><div className="arena-section-title"><h2>Research event stream</h2><span>Latest 40 events in this instrument/timeframe · observation-time evidence</span></div>{snapshot?.events.length===0?<p>No observations yet.</p>:snapshot?.events.slice().reverse().map(e=><div key={e.event_id}><time>{time(e.at)}</time><Badge value={e.type}/><span>{e.text}</span></div>)}</section>
      <footer>Policy {meta.configuration.policy.version} · Result {meta.result_id}<br/>Immutable research evidence. No broker action.</footer>
      </>}
    </main>
  </div>;
}
