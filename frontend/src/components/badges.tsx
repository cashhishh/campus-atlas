import { ShieldCheck, ShieldAlert, ShieldQuestion, Clock, AlertTriangle, ExternalLink } from 'lucide-react';
import { Verification, Freshness, Citation, timeAgo } from '../services/api';

export function VerificationBadge({ v }: { v?: Verification | null }) {
  if (!v) return null;
  const Icon = v.status === 'OFFICIAL' ? ShieldCheck : v.status === 'THIRD_PARTY' ? ShieldAlert : ShieldQuestion;
  return <span className={'badge verify-' + v.status.toLowerCase()} title={v.reason}><Icon size={12} />{v.label}</span>;
}

export function FreshnessBadge({ f, lastChecked }: { f?: Freshness | null; lastChecked?: string | null }) {
  if (!f) return null;
  if (f.state === 'FRESH') return <span className="badge fresh" title={`Checked within the last ${f.stale_after_hours} h`}><Clock size={12} />Checked {timeAgo(lastChecked)}</span>;
  return <span className="badge stale" title={`Not checked within ${f.stale_after_hours} h`}><AlertTriangle size={12} />{f.state === 'NEVER_CHECKED' ? 'Never checked' : 'Stale · ' + timeAgo(lastChecked)}</span>;
}

export function DemoBadge({ show }: { show?: boolean }) {
  return show ? <span className="badge demo">DEMO DATA</span> : null;
}

export function CitationCard({ s }: { s: Citation }) {
  return <a className="source citation" href={s.source_url} target="_blank" rel="noreferrer">
    <div className="badges"><b className="cite-index">S{s.index}</b><VerificationBadge v={s.verification} /><FreshnessBadge f={s.freshness} lastChecked={s.last_checked} /><DemoBadge show={s.is_demo} /></div>
    <strong>{s.source_name}</strong>
    {s.snippet && <em className="snippet">“{s.snippet.slice(0, 220)}{s.snippet.length > 220 ? '…' : ''}”</em>}
    <span>Authority: {s.authority_level.replace('_', ' ')} · last changed {timeAgo(s.last_changed)} <ExternalLink size={12} /></span>
  </a>;
}
