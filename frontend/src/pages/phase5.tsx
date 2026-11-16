// Phase 5 pages: Change Feed, Analytics dashboard and the Monitoring panel used on Data management.
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Activity, FileDiff, Database, Building2, Layers, GitCommitHorizontal, MessageSquare, Timer, LoaderCircle, Wand2, ExternalLink } from 'lucide-react';
import { api, ApiSource, MonitorRun, MonitorStatus, UpdateEvent, fmtDate, timeAgo } from '../services/api';
import { DemoBadge, FreshnessBadge, VerificationBadge } from '../components/badges';
import { colleges } from '../data/colleges';

const collegeName = (id: string) => colleges.find(c => c.id === id)?.name || id;

export function BackendOffline({ what }: { what: string }) {
  return <div className="offline">The CampusAtlas API is not reachable, so {what} cannot be shown. Start it with <code>cd backend &amp;&amp; .venv\Scripts\python -m uvicorn app.main:app --port 8000</code>.</div>;
}

// ------------------------------------------------------------------ Change feed
export function ChangeFeed() {
  const [items, setItems] = useState<UpdateEvent[]>(), [error, setError] = useState(false), [open, setOpen] = useState<number>(), [diff, setDiff] = useState<Record<number, string | null>>({}), [type, setType] = useState('');
  useEffect(() => { api.updates().then(setItems).catch(() => setError(true)) }, []);
  async function toggle(u: UpdateEvent) {
    if (open === u.id) return setOpen(undefined);
    setOpen(u.id);
    if (!(u.id in diff)) { const d = await api.update(u.id).catch(() => null); setDiff(x => ({ ...x, [u.id]: d?.diff ?? null })) }
  }
  const shown = (items || []).filter(u => !type || u.change_type === type);
  return <>
    <section className="page-head"><div className="eyebrow">Change intelligence</div><h1>Updates</h1><p>Every time a monitored source changes, CampusAtlas stores a new version, computes a diff and writes a short summary.</p></section>
    {error ? <BackendOffline what="the change feed" /> : !items ? <div className="empty"><LoaderCircle className="spin" size={14} /> Loading updates…</div> : <>
      <div className="feed-filters">{[['', 'All'], ['CONTENT_UPDATED', 'Content updated'], ['NEW_SOURCE_CONTENT', 'New source content']].map(([v, l]) => <button key={v} className={type === v ? 'on' : ''} onClick={() => setType(v)}>{l}</button>)}<span>{shown.length} event(s)</span></div>
      {shown.length ? <div className="feed">{shown.map(u => <article key={u.id} className="feed-item">
        <div className="feed-meta"><span className={'event-type ' + (u.change_type === 'CONTENT_UPDATED' ? 'updated' : 'new')}>{u.change_type === 'CONTENT_UPDATED' ? 'Content updated' : 'New source content'}</span><time title={fmtDate(u.detected_date)}>{timeAgo(u.detected_date)}</time></div>
        <h3><Link to={'/college/' + u.college_id}>{collegeName(u.college_id)}</Link> · <a href={u.source_url || '#'} target="_blank" rel="noreferrer">{u.source_name} <ExternalLink size={11} /></a></h3>
        <div className="badges"><VerificationBadge v={u.verification} /><DemoBadge show={u.is_demo} /><span className="badge plain">{u.summary_mode === 'gemini' ? 'AI summary (Gemini)' : u.summary_mode === 'groq' ? 'AI summary (Groq)' : 'Diff-based summary'}</span>{u.change_type === 'CONTENT_UPDATED' && <span className="badge plain">+{u.added_count} / −{u.removed_count} passages</span>}</div>
        <p>{u.summary || 'No summary recorded (event created before Phase 5).'}</p>
        {u.change_type === 'CONTENT_UPDATED' && <button className="link-button" onClick={() => toggle(u)}><FileDiff size={13} />{open === u.id ? 'Hide diff' : 'View diff'}</button>}
        {open === u.id && <pre className="diff">{diff[u.id] === undefined ? 'Loading…' : diff[u.id] ? diff[u.id]!.split('\n').map((l, i) => <span key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'add' : l.startsWith('-') && !l.startsWith('---') ? 'del' : ''}>{l + '\n'}</span>) : 'No stored diff for this event.'}</pre>}
      </article>)}</div> : <div className="empty">No change events yet. Run a monitoring check from Data management.</div>}
    </>}
  </>;
}

// ------------------------------------------------------------------ Monitoring panel
export function MonitorPanel() {
  const [status, setStatus] = useState<MonitorStatus>(), [sources, setSources] = useState<ApiSource[]>(), [runs, setRuns] = useState<MonitorRun[]>([]), [busy, setBusy] = useState(false), [last, setLast] = useState<MonitorRun>(), [error, setError] = useState(''), [offline, setOffline] = useState(false);
  async function load() {
    try { const [st, so, ru] = await Promise.all([api.monitorStatus(), api.sources(), api.monitorRuns()]); setStatus(st); setSources(so); setRuns(ru); setOffline(false) } catch { setOffline(true) }
  }
  useEffect(() => { load() }, []);
  async function runNow() { setBusy(true); setError(''); try { setLast(await api.runCheck()) } catch (e: any) { setError(e.message) } finally { setBusy(false); load() } }
  async function simulate(id: number) { setBusy(true); try { await api.simulateChange(id) } catch (e: any) { setError(e.message) } finally { setBusy(false); load() } }
  if (offline) return <BackendOffline what="live monitoring" />;
  return <section className="monitor">
    <div className="monitor-head">
      <div><h2>Source monitoring</h2><p>{status ? <>Scheduler {status.enabled && status.running ? <b className="ok">running</b> : <b className="warn">disabled</b>} · every {status.interval_minutes} min · next run {status.next_run_at ? fmtDate(status.next_run_at) : '—'} · sources stale after {status.stale_after_hours} h</> : 'Loading…'}</p></div>
      <button className="button" onClick={runNow} disabled={busy}>{busy ? <><LoaderCircle className="spin" size={15} /> Checking sources…</> : <><RefreshCw size={15} /> Run check now</>}</button>
    </div>
    {error && <div className="notice">{error}</div>}
    {last && <div className="run-result"><b>Run #{last.id} · {last.status}</b> {last.sources_checked} sources checked · {last.changes_found} changed · {last.errors} error(s) · {((last.duration_ms || 0) / 1000).toFixed(1)} s {last.changes_found > 0 && <Link to="/updates">View in Updates →</Link>}</div>}
    <div className="table-wrap"><table className="source-table"><thead><tr><th>Source</th><th>Verification</th><th>Freshness</th><th>Last changed</th><th>Chunks</th><th>Status</th><th></th></tr></thead><tbody>
      {(sources || []).map(s => <tr key={s.id}>
        <td><strong>{s.source_name}</strong><br /><small>{collegeName(s.college_id)} · <a href={s.source_url} target="_blank" rel="noreferrer">{s.source_url.replace(/^https?:\/\//, '').slice(0, 48)}</a></small></td>
        <td><VerificationBadge v={s.verification} /> <DemoBadge show={s.is_demo} /></td>
        <td><FreshnessBadge f={s.freshness} lastChecked={s.last_checked} /></td>
        <td>{timeAgo(s.last_changed)}</td>
        <td>{s.chunks ?? 0}</td>
        <td>{s.status === 'FETCH_FAILED' ? <span className="badge stale" title={s.last_error || ''}>{s.chunks ? 'Last check failed' : 'Missing · no text'}</span> : <span className="badge plain">{s.status.replace('_', ' ')}</span>}</td>
        <td>{s.is_demo && <button className="link-button" disabled={busy} onClick={() => simulate(s.id)} title="Append a clearly-labelled simulated notice to demonstrate change detection"><Wand2 size={13} />Simulate change</button>}</td>
      </tr>)}
    </tbody></table></div>
    <h2 className="soon-h">Monitoring run log</h2>
    {runs.length ? <div className="table-wrap"><table><thead><tr><th>Run</th><th>Trigger</th><th>Started</th><th>Duration</th><th>Checked</th><th>Changes</th><th>Errors</th><th>Status</th></tr></thead><tbody>
      {runs.map(r => <tr key={r.id}><td>#{r.id}</td><td>{r.trigger}</td><td>{fmtDate(r.started_at)}</td><td>{r.duration_ms != null ? (r.duration_ms / 1000).toFixed(1) + ' s' : '—'}</td><td>{r.sources_checked}</td><td>{r.changes_found}</td><td>{r.errors}</td><td><span className={'badge ' + (r.status === 'SUCCESS' ? 'fresh' : r.status === 'RUNNING' ? 'plain' : 'stale')}>{r.status}</span></td></tr>)}
    </tbody></table></div> : <div className="empty">No monitoring runs yet. Press “Run check now”.</div>}
  </section>;
}

// ------------------------------------------------------------------ Analytics
const SERIES = { a: '#2a78d6', b: '#eb6834', c: '#1baf7a' };

function BarList({ rows, unit = '' }: { rows: { label: string; value: number }[]; unit?: string }) {
  const max = Math.max(1, ...rows.map(r => r.value));
  if (!rows.length) return <div className="empty">No data yet.</div>;
  return <div className="barlist">{rows.map(r => <div className="bar-row" key={r.label} title={`${r.label}: ${r.value}${unit}`}>
    <span className="bar-label">{r.label}</span>
    <span className="bar-track"><span className="bar-fill" style={{ width: `${(r.value / max) * 100}%`, background: SERIES.a }} /></span>
    <span className="bar-value">{r.value}{unit}</span>
  </div>)}</div>;
}

function Timeline({ data }: { data: { date: string; new_content: number; content_updated: number }[] }) {
  const [hover, setHover] = useState<number>();
  const max = Math.max(1, ...data.map(d => d.new_content + d.content_updated));
  const H = 140;
  return <div className="timeline">
    <div className="legend"><span><i style={{ background: SERIES.a }} />New source content</span><span><i style={{ background: SERIES.b }} />Content updated</span></div>
    <div className="cols" style={{ height: H }}>{data.map((d, i) => {
      const a = (d.new_content / max) * H, b = (d.content_updated / max) * H;
      return <div className="col" key={d.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(undefined)}>
        {hover === i && <div className="tip"><b>{d.date}</b><br />New: {d.new_content}<br />Updated: {d.content_updated}</div>}
        <div className="stack">{b > 0 && <span style={{ height: b, background: SERIES.b }} />}{a > 0 && <span style={{ height: a, background: SERIES.a }} />}</div>
      </div>;
    })}</div>
    <div className="axis"><span>{data[0]?.date.slice(5)}</span><span>{data[data.length - 1]?.date.slice(5)}</span></div>
  </div>;
}

function Segmented({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((n, p) => n + p.value, 0) || 1;
  return <div><div className="segmented">{parts.filter(p => p.value).map(p => <span key={p.label} title={`${p.label}: ${p.value}`} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />)}</div>
    <div className="legend">{parts.map(p => <span key={p.label}><i style={{ background: p.color }} />{p.label} · {p.value}</span>)}</div></div>;
}

export function AnalyticsPage() {
  const [data, setData] = useState<any>(), [error, setError] = useState(false);
  useEffect(() => { api.analytics().then(setData).catch(() => setError(true)) }, []);
  if (error) return <><Head /><BackendOffline what="analytics" /></>;
  if (!data) return <><Head /><div className="empty"><LoaderCircle className="spin" size={14} /> Loading analytics…</div></>;
  const t = data.totals, v = data.verification_breakdown, f = data.freshness_breakdown;
  const tiles: [any, string | number, string][] = [
    [Building2, t.colleges, 'Colleges in registry'], [Database, `${t.colleges_indexed}`, 'Colleges with indexed sources'], [Layers, t.sources, 'Registered sources'], [Database, t.chunks, 'Indexed chunks'],
    [Activity, t.ingestion_runs, `Ingestion runs (${t.ingestion_failures} failed)`], [GitCommitHorizontal, t.change_events, `Change events (${t.content_updates} updates)`], [RefreshCw, t.monitor_runs, 'Monitoring runs'], [MessageSquare, t.queries, `Questions asked${t.answered_rate != null ? ` (${Math.round(t.answered_rate * 100)}% answered)` : ''}`],
  ];
  return <>
    <Head />
    <div className="metrics metrics-8">{tiles.map(([I, n, l]) => <div key={l}><I /><b>{n}</b><span>{l}</span></div>)}</div>
    <div className="latency"><Timer size={14} /> Average retrieval {t.avg_retrieval_ms ?? '—'} ms · average end-to-end answer {t.avg_answer_ms ?? '—'} ms · vector store: {t.vector_driver} · AI: <span className="badge plain">{[...(data.ai_providers?.order || []).filter((p: string) => p !== 'demo').map((p: string) => p === 'gemini' ? 'Gemini' : 'Groq'), 'Demo'].join(' → ')}</span></div>
    <section className="charts">
      <article className="chart-card wide"><h3>Change events, last 14 days</h3><Timeline data={data.timeline} /></article>
      <article className="chart-card"><h3>Source verification</h3><Segmented parts={[{ label: 'Official', value: v['Official'] || 0, color: SERIES.c }, { label: 'Third-party', value: v['Third-party'] || 0, color: SERIES.b }, { label: 'Unverified', value: v['Unverified'] || 0, color: '#a3a29b' }]} />
        <h3 className="mt">Freshness</h3><Segmented parts={[{ label: 'Fresh', value: f.FRESH || 0, color: SERIES.a }, { label: 'Stale', value: f.STALE || 0, color: SERIES.b }, { label: 'Never checked', value: f.NEVER_CHECKED || 0, color: '#a3a29b' }]} /></article>
      <article className="chart-card"><h3>Source authority levels</h3><BarList rows={Object.entries(data.authority_breakdown).map(([label, value]) => ({ label: label.replace('_', ' '), value: value as number }))} /></article>
      <article className="chart-card"><h3>Indexed chunks by college</h3><BarList rows={data.chunks_by_college.map((c: any) => ({ label: c.name.length > 28 ? c.name.slice(0, 27) + '…' : c.name, value: c.chunks }))} /></article>
      <article className="chart-card"><h3>Most asked questions</h3>{data.top_queries.length ? <ol className="top-q">{data.top_queries.map((q: any) => <li key={q.query}><span>{q.query}</span><b>{q.count}×</b></li>)}</ol> : <div className="empty">No questions logged yet.</div>}</article>
      <article className="chart-card"><h3>Answers by AI provider</h3><BarList rows={Object.entries(data.provider_breakdown || {}).map(([label, value]) => ({ label, value: value as number })).sort((a, b) => b.value - a.value)} /></article>
      <article className="chart-card"><h3>Question intents</h3><BarList rows={Object.entries(data.intent_breakdown).map(([label, value]) => ({ label, value: value as number })).sort((a, b) => b.value - a.value)} /></article>
      <article className="chart-card"><h3>Recent monitoring runs</h3><BarList unit=" changed" rows={data.recent_runs.map((r: any) => ({ label: `#${r.id} · ${r.trigger} · ${r.sources_checked} checked`, value: r.changes_found }))} /></article>
    </section>
  </>;
}
function Head() { return <section className="page-head"><div className="eyebrow">Analytics</div><h1>Platform analytics</h1><p>Live numbers from the registry, ingestion log, change detector and query log.</p></section> }
