// Views that read live data from the FastAPI backend, each with an offline fallback.
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, LoaderCircle } from 'lucide-react';
import { api, ApiSource, CompareEvidence, UpdateEvent, timeAgo } from '../services/api';
import { DemoBadge, FreshnessBadge, VerificationBadge } from '../components/badges';

/** Sources for one college with verification + freshness. Shows `children` if the API is offline. */
export function LiveSources({ id, children }: { id: string; children: React.ReactNode }) {
  const [data, setData] = useState<{ sources: ApiSource[]; recent_updates: UpdateEvent[]; chunks: number } | null>(), [offline, setOffline] = useState(false);
  useEffect(() => { api.college(id).then(setData).catch(() => setOffline(true)) }, [id]);
  if (offline) return <>{children}<h3 className="aside-title">Updates</h3><p className="aside-copy">Start the API to see monitored updates.</p></>;
  if (!data) return <div className="empty"><LoaderCircle className="spin" size={14} /> Loading sources…</div>;
  return <>
    <h3>Indexed sources <small className="muted">· {data.chunks} chunks</small></h3>
    {data.sources.length ? data.sources.map(s => <a className="source" href={s.source_url} target="_blank" rel="noreferrer" key={s.id}>
      <div className="badges"><VerificationBadge v={s.verification} /><FreshnessBadge f={s.freshness} lastChecked={s.last_checked} /><DemoBadge show={s.is_demo} /></div>
      <strong>{s.source_name}</strong>
      <span>{s.status === 'FETCH_FAILED' ? (s.chunks ? 'Last check failed — earlier indexed version still used' : 'Could not be fetched — marked missing') : `Last changed ${timeAgo(s.last_changed)} · ${s.chunks ?? 0} chunks`} <ExternalLink size={12} /></span>
    </a>) : <p className="aside-copy">No configured sources yet.</p>}
    <h3 className="aside-title">Recent updates</h3>
    {data.recent_updates.length ? data.recent_updates.map(u => <div className="mini-update" key={u.id}><b>{u.change_type === 'CONTENT_UPDATED' ? 'Updated' : 'New content'} · {timeAgo(u.detected_date)}</b><span>{u.summary?.slice(0, 160)}</span></div>) : <p className="aside-copy">No changes detected yet.</p>}
    <Link className="aside-link" to="/updates">Open change feed →</Link>
  </>;
}

/** Evidence table (topic x college) built only from indexed chunks. */
export function useCompareEvidence(ids: string[]) {
  const [data, setData] = useState<CompareEvidence | null>(), [offline, setOffline] = useState(false);
  const key = ids.join(',');
  useEffect(() => {
    if (!ids.length) { setData(undefined); return }
    setData(undefined);
    api.compareEvidence(ids).then(d => { setData(d); setOffline(false) }).catch(() => setOffline(true));
  }, [key]);
  return { data, offline };
}

export function EvidenceTable({ ids, names, data }: { ids: string[]; names: Record<string, string>; data: CompareEvidence }) {
  return <table className="evidence"><thead><tr><th>Topic</th>{ids.map(id => <th key={id}>{names[id]}</th>)}</tr></thead><tbody>
    {data.topics.map(t => <tr key={t}><td>{t}</td>{ids.map(id => {
      const cell = data.colleges[id]?.[t];
      return <td key={id}>{cell?.available ? <><p className="cell-text">{cell.text}</p><a className="cell-source" href={cell.source_url} target="_blank" rel="noreferrer">{cell.source_name} <ExternalLink size={10} /></a> <DemoBadge show={cell.is_demo} /></> : <span className="na">Not available in indexed sources.</span>}</td>;
    })}</tr>)}
  </tbody></table>;
}
