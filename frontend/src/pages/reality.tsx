// Reality Check: what a student actually gets at a college.
// Numbers come from the college's own NIRF data filing (cited); campus life comes from a cited web search
// of official pages + student discussions, clearly labelled.
import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ExternalLink, LoaderCircle, RefreshCw } from 'lucide-react';
import { VerificationBadge } from '../components/badges';
import { timeAgo } from '../services/api';

async function getJson(path: string): Promise<any> {
  const r = await fetch('/api' + path);
  if (!r.ok) {
    let detail = String(r.status);
    try { detail = (await r.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}

const lakh = (n: number) => '₹' + (n / 100000).toFixed(1).replace('.0', '') + ' L';

function Stat({ value, label, tone }: { value: string; label: string; tone?: 'good' | 'bad' | 'mid' }) {
  return <div className={'rc-stat ' + (tone || '')}><b>{value}</b><span>{label}</span></div>;
}

function SourceLine({ s }: { s: any }) {
  if (!s) return null;
  return <a className="rc-source" href={s.url} target="_blank" rel="noreferrer"><VerificationBadge v={s.verification} /> {s.name} <ExternalLink size={11} /></a>;
}

function Placements({ p }: { p: any }) {
  if (!p) return <div className="rc-card"><h2>Placements</h2><p className="muted">No NIRF data filing indexed for this college yet.</p></div>;
  const L = p.latest;
  const placedTone = L.placement_pct >= 75 ? 'good' : L.placement_pct >= 60 ? 'mid' : 'bad';
  return <div className="rc-card">
    <h2>Placements — the real numbers <small>{L.year} batch</small></h2>
    <div className="rc-stats">
      <Stat value={L.placement_pct + '%'} label={`placed (${L.placed.toLocaleString()} of ${L.graduating.toLocaleString()})`} tone={placedTone} />
      <Stat value={lakh(L.median)} label="median salary (typical placed student)" />
      <Stat value={L.neither_pct + '%'} label="neither placed nor in higher studies" tone={L.neither_pct > 25 ? 'bad' : L.neither_pct > 12 ? 'mid' : 'good'} />
      <Stat value={L.higher_pct + '%'} label="went for higher studies" />
    </div>
    {p.highest_package_claim && <div className="rc-claim">
      <span>College website says</span><b>Highest package ₹{p.highest_package_claim.lakh} L</b>
      <span>Reality</span><b>Median {lakh(L.median)}</b>
      <em>The highest offer goes to one student. The median is what a typical placed student gets.</em>
    </div>}
    <div className="rc-bars">{p.rows.map((r: any) => <div className="rc-bar" key={r.year}>
      <span>{r.year}</span>
      <div className="rc-track"><i style={{ width: r.placement_pct + '%' }} className="placed" /><i style={{ width: r.higher_pct + '%' }} className="higher" /></div>
      <small>{r.placement_pct}% placed · {lakh(r.median)}</small>
    </div>)}</div>
    <div className="rc-legend"><i className="placed" /> placed <i className="higher" /> higher studies <i /> neither</div>
    <SourceLine s={p.source} />
  </div>;
}

function Teachers({ c }: { c: any }) {
  if (!c || (!c.faculty && !c.students)) return <div className="rc-card"><h2>Teachers & students</h2><p className="muted">Faculty details are not in the indexed NIRF filing for this college.</p></div>;
  const f = c.faculty, s = c.students, sp = c.spend;
  return <div className="rc-card">
    <h2>Teachers & classmates <small>from the official NIRF filing</small></h2>
    {f && <div className="rc-stats">
      <Stat value={String(f.count)} label="current faculty" />
      <Stat value={f.phd_pct + '%'} label="hold a PhD" tone={f.phd_pct >= 60 ? 'good' : f.phd_pct >= 40 ? 'mid' : 'bad'} />
      <Stat value={f.senior_pct + '%'} label="Professors / Associate Profs" tone={f.senior_pct >= 25 ? 'good' : f.senior_pct >= 15 ? 'mid' : 'bad'} />
      <Stat value={f.adhoc_pct + '%'} label="ad-hoc / contractual" tone={f.adhoc_pct <= 5 ? 'good' : f.adhoc_pct <= 15 ? 'mid' : 'bad'} />
      {f.student_ratio && <Stat value={f.student_ratio + ':1'} label="students per teacher (norm 20:1)" tone={f.student_ratio <= 20 ? 'good' : f.student_ratio <= 25 ? 'mid' : 'bad'} />}
      <Stat value={f.median_experience_years + ' yrs'} label="median teaching experience" />
    </div>}
    {s && <div className="rc-stats">
      <Stat value={s.total.toLocaleString()} label="UG students" />
      <Stat value={s.female_pct + '%'} label="women in UG" tone={s.female_pct >= 25 ? 'good' : s.female_pct >= 15 ? 'mid' : 'bad'} />
      <Stat value={s.outside_state_pct + '%'} label="from outside the state" />
      {sp?.lab_per_student != null && <Stat value={'₹' + sp.lab_per_student.toLocaleString()} label="new lab equipment / student / yr" />}
      {sp?.library_per_student != null && <Stat value={'₹' + sp.library_per_student.toLocaleString()} label="library / student / yr" />}
    </div>}
    <SourceLine s={c.source} />
  </div>;
}

function Life({ id }: { id: string }) {
  const [data, setData] = useState<any>(), [err, setErr] = useState(''), [loading, setLoading] = useState(false);
  const load = (refresh = false) => {
    setLoading(true); setErr('');
    getJson(`/reality/${id}/life${refresh ? '?refresh=true' : ''}`).then(setData).catch(e => setErr(e.message)).finally(() => setLoading(false));
  };
  useEffect(() => { setData(undefined); load() }, [id]);
  return <div className="rc-card rc-life">
    <h2>Campus life — what students actually say <small>official pages + student discussions, live web search</small></h2>
    {loading && !data && <div className="empty"><LoaderCircle className="spin" size={14} /> Reading official pages and student discussions… (first time takes ~20 s, then cached)</div>}
    {err && <div className="notice">{err}</div>}
    {data && <>
      {data.sections.verdict && <div className="rc-verdict"><b>Verdict</b> {data.sections.verdict}</div>}
      <div className="rc-grid">{Object.entries(data.labels as Record<string, string>).map(([k, label]) =>
        <div className={'rc-sec' + (k === 'watch_out' ? ' warn' : '')} key={k}><h3>{label}</h3><p>{data.sections[k] || 'Not enough reliable information.'}</p></div>)}</div>
      <p className="rc-note">Student opinions are experiences, not verified facts. Official numbers above come from the college's own NIRF filing.</p>
      <h3 className="rc-h3">Sources ({data.sources.length}) · checked {timeAgo(data.checked_at)}
        <button className="link-button" onClick={() => load(true)} disabled={loading}><RefreshCw size={11} /> refresh</button></h3>
      <div className="rc-sources">{data.sources.map((s: any) => <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="rc-source">
        <VerificationBadge v={s.verification} /> {s.title || s.domain} <ExternalLink size={11} /></a>)}</div>
    </>}
  </div>;
}

export function RealityPage() {
  const [params, setParams] = useSearchParams();
  const [list, setList] = useState<any[]>([]), [data, setData] = useState<any>(), [err, setErr] = useState('');
  const id = params.get('college') || 'mait';
  useEffect(() => { getJson('/reality').then(setList).catch(() => setList([])) }, []);
  useEffect(() => { setData(undefined); setErr(''); getJson('/reality/' + id).then(setData).catch(e => setErr(e.message)) }, [id]);
  return <section className="reality">
    <div className="eyebrow">Ground reality, not brochures</div>
    <h1>Reality Check</h1>
    <p className="rc-lead">What you actually get: real placement numbers, who teaches you, who your classmates are, and what students say about campus life, fests and hostels — every number linked to the college's own official filing.</p>
    <div className="rc-pick">{list.map(c => <button key={c.id} className={c.id === id ? 'on' : ''} onClick={() => setParams({ college: c.id })}>{c.name.replace(/\s*\(.*?\)/, '')}</button>)}</div>
    {err && <div className="notice">{err}</div>}
    {!data && !err && <div className="empty"><LoaderCircle className="spin" size={14} /> Loading…</div>}
    {data && <>
      <h2 className="rc-name">{data.college} <small>{data.city}{data.nirf ? ` · NIRF ${data.nirf.year}: ${data.nirf.text}` : ''}</small></h2>
      <Placements p={data.placements} />
      <Teachers c={data.campus} />
      <Life id={id} />
    </>}
  </section>;
}
