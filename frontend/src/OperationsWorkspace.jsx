import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, Check, CircleStop, Database, LayoutDashboard, ListOrdered, Lock, MessageSquare, Plus, RefreshCw, ShieldCheck, Workflow } from 'lucide-react';
import './operations.css';

const pages = [['dashboard','Dashboard',LayoutDashboard],['trade','New trade',Plus],['positions','Positions / execution',ListOrdered],['safety','Safety / risk',ShieldCheck],['whatsapp','WhatsApp',MessageSquare],['strategies','Automated strategies',Workflow],['monitoring','Monitoring / alerts',Activity]];
const fmt = value => value === null || value === undefined ? 'Unavailable' : String(value);
const words = value => String(value || 'NOT_AVAILABLE').replaceAll('_',' ');
const percent = value => value === null || value === undefined ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;

function Badge({ value }) {
  const text=String(value || 'NOT_AVAILABLE');
  const tone=/ERROR|AMBIGUOUS|REJECTED|HALT|CRITICAL/.test(text)?'red':/HEALTHY|APPROVED|OBSERVED/.test(text)?'green':'amber';
  return <span className={`op-badge ${tone}`}>{words(text)}</span>;
}
function Table({ headings, rows, empty='No recorded evidence in this window.' }) {
  return rows.length ? <div className="op-table-scroll"><table><thead><tr>{headings.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div> : <p className="op-empty">{empty}</p>;
}
function Stats({ entries }) {
  return <dl className="op-stats">{entries.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{fmt(v)}</dd></div>)}</dl>;
}
function Evidence({ value }) {
  return <details><summary>Inspect evidence</summary><pre>{JSON.stringify(value,null,2)}</pre></details>;
}

export default function OperationsWorkspace({ token, onLock, page }) {
  const selected=page.replace('#/','').split('/')[0] || 'dashboard';
  const section=pages.some(p=>p[0]===selected)?selected:'dashboard';
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState(null);
  const [start,setStart]=useState(''),[form,setForm]=useState({instrument:'XAUUSDm',direction:'BUY',entry_type:'MARKET',entry:'',stop_loss:'',take_profit:'',risk:'0.25',source_id:''});
  const [deployment,setDeployment]=useState({strategy_id:'p6-01',instrument:'XAUUSD',timeframe:'1H'});
  const retry=useRef(null);
  const api=useCallback(async(path,body)=>{
    const response=await fetch(path,{method:body?'POST':'GET',headers:{'X-Control-Token':token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
    let value; try {value=await response.json();} catch {throw new Error('Backend response unavailable.');}
    if(!response.ok) throw new Error(typeof value.detail==='string'?value.detail:'Request rejected.');
    return value;
  },[token]);
  const refresh=useCallback(async()=>{
    try {
      const query=start?`?start=${encodeURIComponent(new Date(`${start}T00:00:00Z`).toISOString())}`:'';
      setData(await api(`/api/core/operations/snapshot${query}`)); setError('');
    } catch(e) {setError(e.message);setData(null);}
  },[api,start]);
  useEffect(()=>{let active=true;const run=()=>{if(active)refresh();};run();const timer=setInterval(run,5000);return()=>{active=false;clearInterval(timer);};},[refresh]);
  async function action(callback) {setBusy(true);setError('');try {await callback();await refresh();} catch(e){setError(e.message);}finally{setBusy(false);}}
  async function halt() {await action(()=>api('/api/controls/kill-switch',{}));}
  function change(key,value) {setForm(f=>({...f,[key]:value}));retry.current=null;setResult(null);}
  async function propose(event) {
    event.preventDefault();
    await action(async()=>{
      if(!retry.current) {
        const targets=form.take_profit.split(',').map(x=>Number(x.trim()));
        if(!targets.length || targets.length>3 || targets.some(x=>!Number.isFinite(x)||x<=0)) throw new Error('Enter one to three positive targets.');
        retry.current={source_type:'MANUAL',source_id:form.source_id || data?.manual_sources?.[0],message_id:crypto.randomUUID(),
          original_timestamp:new Date().toISOString(),timezone_evidence:'UTC',provenance:{origin:'v1-operator-workspace'},
          signal:{instrument:form.instrument,direction:form.direction,entry_type:form.entry_type,
            entry:form.entry?Number(form.entry):null,stop_loss:Number(form.stop_loss),take_profit:targets,requested_risk_pct:Number(form.risk)}};
      }
      setResult(await api('/api/core/operations/proposals',retry.current));
    });
  }
  async function download() {
    await action(async()=>{
      const query=start?`?start=${encodeURIComponent(new Date(`${start}T00:00:00Z`).toISOString())}`:'';
      const report=await api(`/api/core/operations/export${query}`);
      const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download=`nexusai-evidence-${report.report_id.slice(0,12)}.json`;link.click();URL.revokeObjectURL(url);
    });
  }
  const title=pages.find(p=>p[0]===section)?.[1];
  return <div className="op-app">
    <aside className="op-sidebar"><a href="#/" className="op-brand">NEXUS<span>AI</span><small>Operator workspace</small></a>
      <nav aria-label="Operations">{pages.map(([id,label,Icon])=><a href={`#/${id}`} key={id} aria-current={section===id?'page':undefined}><Icon size={17}/>{label}</a>)}
        <a href="#/tournament"><Activity size={17}/>Tournament Arena</a><a href="#/chat-learning"><Database size={17}/>Historical review</a></nav>
      <div className="op-sidebar-foot"><Lock size={15}/><span>LIVE LOCKED</span><span>P8 active work deferred</span></div>
    </aside>
    <div className="op-content"><header className="op-topbar"><div className="op-mode"><ShieldCheck size={17}/><strong>{data?.scope==='FIXTURE'?'FIXTURE PREVIEW':'RESEARCH'}</strong><Badge value={data?.broker_execution || 'UNAVAILABLE'}/></div>
      <div className="op-actions"><button aria-label="Refresh evidence" title="Refresh evidence" disabled={busy} onClick={refresh}><RefreshCw size={17}/></button><button aria-label="Export evidence" title="Export evidence" disabled={!data||busy} onClick={download}><ArrowDownToLine size={17}/></button><button aria-label="Lock workspace" title="Lock workspace" onClick={onLock}><Lock size={17}/></button><button className="op-halt" disabled={busy} onClick={halt}><CircleStop size={16}/>HALT</button></div>
    </header>
    <main><div className="op-heading"><div><p className="op-eyebrow">NEXUSAI / V1</p><h1>{title}</h1></div><label className="op-date">Activity from (UTC)<input aria-label="Activity start date" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label></div>
      {error&&<div role="alert" className="op-error">{error}</div>}
      <div className="op-boundary"><Lock size={17}/><div><strong>Broker execution disabled</strong><span>Operator demo verification pending. No live-money route.</span></div><Badge value={data?.halt?.state || 'NOT_AVAILABLE'}/></div>
      {!data?<p role="status" className="op-empty">{error?'Evidence unavailable.':'Loading evidence...'}</p>:<>
      {section==='dashboard'&&<>
        <Stats entries={['balance','equity','floating_pnl','free_margin','daily_pnl','weekly_pnl'].map(k=>[words(k),data.portfolio[k]])}/>
        <section><div className="op-section-heading"><h2>Execution controls</h2><Badge value="OPERATOR_NOT_QUALIFIED"/></div><div className="op-switches">{['manual','whatsapp','automated'].map(k=><label key={k}><span>{words(k)} execution</span><input type="checkbox" role="switch" checked={!!data.controls[k]} disabled title="Requires actual P3 operator qualification"/><small>Blocked</small></label>)}</div></section>
        <section><h2>System health</h2><Table headings={['Component','State','Observed at']} rows={data.health.map(h=>[words(h.component),<Badge value={h.state}/>,fmt(h.observed_at)])}/></section>
        <section><h2>Source activity</h2><Table headings={['Source','Received via V1','Canonical events','Statuses']} rows={Object.entries(data.sources).map(([k,v])=>[k,v.received,v.canonical_sources,Object.entries(v.statuses).map(([s,n])=>`${words(s)}: ${n}`).join(', ')||'None'])}/></section>
        <section><h2>Source admission / execution</h2><Table headings={['Source','Received','Validated','Quarantined','Approved','Rejected','Executed','Duplicates blocked']} rows={Object.entries(data.source_metrics?.counts||{}).map(([source,c])=>[source,c.received,c.validated,c.quarantined,c.approved,c.rejected,c.executed,c.duplicates_blocked])}/></section>
      </>}
      {section==='trade'&&<div className="op-trade-grid"><form onSubmit={propose}><h2>Manual proposal</h2><label>Authorized manual source<select value={form.source_id||data.manual_sources[0]||''} onChange={e=>change('source_id',e.target.value)} disabled={!data.manual_sources.length}>{!data.manual_sources.length&&<option value="">Not configured</option>}{data.manual_sources.map(s=><option key={s}>{s}</option>)}</select></label>
        <label>Policy instrument<select value={form.instrument} onChange={e=>change('instrument',e.target.value)}>{['XAUUSDm','XAGUSDm','USOILm'].map(s=><option key={s}>{s}</option>)}</select></label>
        <fieldset className="op-segment"><legend>Direction</legend>{['BUY','SELL'].map(d=><label key={d}><input type="radio" name="direction" checked={form.direction===d} onChange={()=>change('direction',d)}/>{d}</label>)}</fieldset>
        <label>Order semantics<select value={form.entry_type} onChange={e=>change('entry_type',e.target.value)}><option>MARKET</option><option>LIMIT</option></select></label>
        <label>{form.entry_type==='LIMIT'?'Limit entry':'Source entry (optional)'}<input type="number" step="any" min="0.00000001" required={form.entry_type==='LIMIT'} value={form.entry} onChange={e=>change('entry',e.target.value)}/></label>
        <label>Stop loss<input type="number" step="any" min="0.00000001" required value={form.stop_loss} onChange={e=>change('stop_loss',e.target.value)}/></label>
        <label>Take profit(s)<input required placeholder="Comma-separated levels" value={form.take_profit} onChange={e=>change('take_profit',e.target.value)}/></label>
        <label>Requested risk (%)<input type="number" step="0.01" min="0.01" max="0.5" required value={form.risk} onChange={e=>change('risk',e.target.value)}/></label>
        <button className="op-primary" disabled={busy||!data.manual_sources.length}><ShieldCheck size={17}/>Evaluate proposal</button></form>
        <section><h2>P2 decision</h2>{result?<><Badge value={result.status}/><p>{words(result.reason)}</p><Stats entries={Object.entries(result.allocation||{})}/><Evidence value={result}/></>:<p className="op-empty">No proposal evaluated.</p>}<h2>Execution status</h2><Badge value="HARD_DISABLED"/><p className="op-muted">Instrument mapping and demo account are not attested.</p></section></div>}
      {section==='positions'&&<><Stats entries={[["Attempts",data.execution.attempts.length],["Observed positions",data.execution.positions.length],["Observed entry deals",data.execution.deals.length]]}/><section><h2>Execution attempts</h2><Table headings={['Request','State','Started','Evidence']} rows={data.execution.attempts.map(a=>[a.execution_request_id,<Badge value={a.state}/>,fmt(a.started_at),<Evidence value={a}/>])}/></section><section><h2>Broker position projection</h2><Table headings={['Position','State','Observed','Evidence']} rows={data.execution.positions.map(p=>[p.broker_position_id,<Badge value={p.lifecycle_state}/>,p.observed_at,<Evidence value={p}/>])}/></section><section><h2>Reconciliation</h2><Badge value={data.reconciliation.status}/><Evidence value={data.reconciliation}/><Evidence value={data.execution}/></section></>}
      {section==='safety'&&<><Stats entries={[["Reserved slots",data.safety.reserved_slots],["Reserved risk",data.safety.reserved_risk],["Reserved margin",data.safety.reserved_margin],["Margin utilization",data.portfolio.margin_utilization],["Drawdown",data.portfolio.drawdown]]}/><section><h2>Authoritative P2 policy</h2><p>{data.safety.policy?.version||'Not configured'}</p><Evidence value={data.safety.policy_limits}/><p className="op-muted">Limits are read-only. Current broker exposure is separate from retained reservations.</p></section><section><h2>Reservations</h2><Table headings={['Intent','Instrument','State','Risk','Volume','Expiry']} rows={data.safety.reservations.map(r=>[r.intent_id,r.symbol,<Badge value={r.state}/>,r.risk,r.volume,r.expires_at])}/></section><section><h2>Rejection reasons</h2><Table headings={['Reason','Decisions']} rows={Object.entries(data.safety.rejection_reasons)}/></section><section><h2>Recorded baselines / current exposure</h2><Evidence value={data.safety.recorded_baselines}/><Evidence value={data.safety.current_exposure}/></section></>}
      {section==='whatsapp'&&<><section><h2>Connector</h2><Badge value={data.health.find(h=>h.component==='whatsapp')?.state}/><p className="op-muted">No authenticated live transport has been attested.</p></section><section><h2>Message admission</h2><Table headings={['Received','State','Reason','Lineage']} rows={data.recent_ingress.filter(i=>i.source_type==='WHATSAPP_HUMAN').map(i=>[i.received_at,<Badge value={i.status}/>,words(i.reason),<Evidence value={i}/>])}/></section></>}
      {section==='strategies'&&<><section><div className="op-section-heading"><h2>Demo deployment registry</h2><Badge value="UNQUALIFIED_AUTOMATION"/></div><p className="op-muted">P7: no strategy research-qualified. Deployment does not imply profitability.</p>
        <form className="op-deploy-form" onSubmit={e=>{e.preventDefault();action(()=>api('/api/core/operations/deployments',{...deployment,enabled:false}));}}>
          <label>Strategy<select value={deployment.strategy_id} onChange={e=>setDeployment({...deployment,strategy_id:e.target.value})}>{data.strategy_catalogue.map(s=><option value={s.strategy_id} key={s.strategy_id}>{s.name}</option>)}</select></label>
          <label>Research instrument<select value={deployment.instrument} onChange={e=>setDeployment({...deployment,instrument:e.target.value})}>{['XAUUSD','XAGUSD','USOIL'].map(s=><option key={s}>{s}</option>)}</select></label>
          <label>Timeframe<select value={deployment.timeframe} onChange={e=>setDeployment({...deployment,timeframe:e.target.value})}><option>1H</option><option>4H</option></select></label><button disabled={busy}><Plus size={16}/>Register disabled</button></form>
        <Table headings={['Strategy','Instrument','Frame','Mode','Enabled','Last evaluation']} rows={data.deployments.map(d=>[data.strategy_catalogue.find(s=>s.strategy_id===d.strategy_id)?.name||d.strategy_id,d.instrument,d.timeframe,<Badge value={d.mode}/>,<input aria-label={`Enable ${d.strategy_id}`} type="checkbox" role="switch" checked={!!d.enabled} disabled/>,fmt(d.last_evaluated_at)])}/></section></>}
{section==='monitoring'&&<><section><h2>Health and freshness</h2><Table headings={['Component','State','Observed']} rows={data.health.map(h=>[words(h.component),<Badge value={h.state}/>,fmt(h.observed_at)])}/></section><section><h2>Alerts</h2><Table headings={['Severity','Source','Type','Observed','Acknowledged']} rows={data.alerts.map(a=>[<Badge value={a.severity}/>,a.source,words(a.kind),fmt(a.observed_at),a.acknowledged?<Check size={17}/>:<button title="Acknowledge alert" aria-label="Acknowledge alert" disabled={busy||a.alert_id==='persistent-halt'} onClick={()=>action(()=>api(`/api/core/operations/alerts/${a.alert_id}/acknowledge`,{command_id:crypto.randomUUID()}))}><Check size={17}/></button>])}/></section><section><h2>Market data</h2><Table headings={['Instrument','Mapping','Quote','Spread']} rows={Object.entries(data.instruments).map(([k,v])=>[k,v.mapping_status,fmt(v.quote_at),fmt(v.spread)])}/></section><section><h2>P10 evidence preparation</h2><Badge value={data.p10.status}/><Table headings={['Event','Timestamp','Intent']} rows={data.p10.events.slice(-50).map(e=>[e.event_type,e.timestamp,fmt(e.intent_id)])}/></section><section><h2>Intelligence research</h2><Badge value={data.p8.status}/><Evidence value={data.p8}/></section></>}
      {section==='positions'&&<section><h2>Canonical lifecycle lineage</h2><Table headings={['Source','Signal','Intent','P2','Request','Attempt','Broker evidence']} rows={(data.execution.lineage||[]).map(l=>[l.source_type,l.signal_id,fmt(l.intent_id),<Badge value={l.decision}/>,fmt(l.execution_request_id),fmt(l.attempt_id),<Evidence value={l}/>])}/></section>}
      {section==='monitoring'&&<section><h2>Recorded health coverage</h2><Table headings={['Component','Evidence coverage','Healthy / full window','Unknown / conflicting seconds']} rows={Object.entries(data.health_coverage||{}).map(([component,c])=>[words(component),percent(c.coverage_fraction),percent(c.healthy_fraction),(c.seconds.UNKNOWN||0)+(c.seconds.AMBIGUOUS||0)])}/></section>}
      <footer className="op-footer"><span>Snapshot: {data.snapshot_at}</span><span>Activity window: {data.window.start} to {data.window.end}</span><span>Current economic state; not a historical account replay.</span><code>{data.report_id}</code></footer>
      </>}
    </main></div>
  </div>;
}
