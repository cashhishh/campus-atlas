import re
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..analytics import build_analytics
from ..live import lookup as live_lookup
from ..qa import engine as qa_engine
from ..database import get_db
from ..ingestion.pipeline import DEMO_TEXT, ingest, latest_version, process_text
from ..models.models import College, ContentVersion, IngestionEvent, MonitorRun, QueryLog, Source, UpdateEvent
from ..monitoring.scheduler import run_monitoring_cycle, scheduler_status, serialize_run
from ..recommendations.engine import compare_evidence, recommend
from ..retrieval.rag import answer, retrieve
from ..services.vector_store import count, count_by_source
from ..verification.rules import classify_source, freshness

router = APIRouter()


# ------------------------------------------------------------- serializers
def college(c):
    return {'id': c.id, 'name': c.name, 'category': c.category, 'city': c.city, 'state': c.state,
            'official_domain': c.official_domain}


def source(s, chunk_counts=None):
    domain = s.college.official_domain if s.college else None
    return {'id': s.id, 'college_id': s.college_id, 'source_name': s.source_name, 'source_url': s.source_url,
            'source_type': s.source_type, 'authority_level': s.authority_level, 'status': s.status,
            'last_checked': s.last_checked, 'last_changed': s.last_changed, 'content_hash': s.content_hash,
            'last_error': s.last_error, 'is_demo': bool(s.is_demo or s.status == 'DEMO_READY'),
            'verification': classify_source(s.source_url or '', domain),
            'freshness': freshness(s.last_checked, s.last_changed),
            'chunks': (chunk_counts or {}).get(s.id) if chunk_counts is not None else None}


def update_event(u, sources_by_id=None, include_diff=False):
    s = (sources_by_id or {}).get(u.source_id)
    data = {'id': u.id, 'college_id': u.college_id, 'source_id': u.source_id, 'change_type': u.change_type,
            'detected_date': u.detected_date, 'summary': u.summary, 'summary_mode': u.summary_mode,
            'added_count': u.added_count, 'removed_count': u.removed_count, 'old_hash': u.old_hash,
            'new_hash': u.new_hash, 'monitor_run_id': u.monitor_run_id,
            'source_name': s.source_name if s else None, 'source_url': s.source_url if s else None,
            'is_demo': bool(s and (s.is_demo or s.status == 'DEMO_READY')),
            'verification': classify_source(s.source_url, s.college.official_domain if s.college else None) if s else None}
    if include_diff:
        data['diff'] = u.diff
    return data


def _registry(db):
    return [(c.id, c.name) for c in db.query(College).all()]


# ------------------------------------------------------------- colleges
@router.get('/colleges')
def colleges(q: str = '', category: str = '', db: Session = Depends(get_db)):
    x = db.query(College)
    if q:
        x = x.filter(College.name.ilike(f'%{q}%'))
    if category:
        x = x.filter(College.category == category)
    return [college(v) for v in x.all()]


@router.get('/colleges/{id}')
def one(id: str, db: Session = Depends(get_db)):
    c = db.get(College, id)
    if not c:
        raise HTTPException(404, 'College not found')
    counts = count_by_source()
    updates = db.query(UpdateEvent).filter(UpdateEvent.college_id == id).order_by(desc(UpdateEvent.detected_date)).limit(5).all()
    by_id = {s.id: s for s in c.sources}
    return {**college(c), 'sources': [source(s, counts) for s in c.sources],
            'chunks': sum(counts.get(s.id, 0) for s in c.sources),
            'recent_updates': [update_event(u, by_id) for u in updates]}


# ------------------------------------------------------------- sources
@router.get('/sources')
def sources(college_id: str = '', db: Session = Depends(get_db)):
    q = db.query(Source)
    if college_id:
        q = q.filter(Source.college_id == college_id)
    counts = count_by_source()
    return [source(s, counts) for s in q.order_by(Source.id).all()]


class NewSource(BaseModel):
    college_id: str
    source_name: str
    source_url: str
    source_type: str = 'PUBLIC_SOURCE'
    authority_level: str = 'MEDIUM'


@router.post('/sources')
def add_source(p: NewSource, db: Session = Depends(get_db)):
    if not re.match(r'^https?://', p.source_url):
        raise HTTPException(422, 'source_url must start with http:// or https://')
    if not db.get(College, p.college_id):
        raise HTTPException(404, 'College not found')
    s = Source(**p.model_dump(), status='ACTIVE')
    db.add(s)
    db.commit()
    db.refresh(s)
    return source(s)


@router.get('/sources/{id}')
def get_source(id: int, db: Session = Depends(get_db)):
    s = db.get(Source, id)
    if not s:
        raise HTTPException(404, 'Source not found')
    return source(s, count_by_source())


@router.get('/sources/{id}/versions')
def source_versions(id: int, db: Session = Depends(get_db)):
    rows = db.query(ContentVersion).filter(ContentVersion.source_id == id).order_by(desc(ContentVersion.version_no)).all()
    return [{'id': v.id, 'version_no': v.version_no, 'content_hash': v.content_hash, 'char_count': v.char_count,
             'document_title': v.document_title, 'created_at': v.created_at, 'preview': (v.text or '')[:300]} for v in rows]


@router.post('/sources/{id}/disable')
def disable(id: int, db: Session = Depends(get_db)):
    s = db.get(Source, id)
    if not s:
        raise HTTPException(404, 'Source not found')
    s.status = 'DISABLED'
    db.commit()
    return source(s)


@router.post('/sources/{id}/enable')
def enable(id: int, db: Session = Depends(get_db)):
    s = db.get(Source, id)
    if not s:
        raise HTTPException(404, 'Source not found')
    s.status = 'DEMO_READY' if s.is_demo else 'ACTIVE'
    db.commit()
    return source(s)


@router.post('/sources/{id}/ingest')
def run_ingestion(id: int, db: Session = Depends(get_db)):
    try:
        return ingest(db, id)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get('/verification/check')
def verification_check(url: str, college_id: str = '', db: Session = Depends(get_db)):
    c = db.get(College, college_id) if college_id else None
    return classify_source(url, c.official_domain if c else None)


# ------------------------------------------------------------- demo helpers
@router.post('/demo/seed-knowledge')
def seed_knowledge(db: Session = Depends(get_db)):
    results = []
    for s in db.query(Source).filter(Source.status == 'DEMO_READY'):
        results.append(ingest(db, s.id))
    return results


SIMULATED_NOTICES = [
    'DEMO DATA — Simulated notice: the page now links a revised academic calendar. (Generated only to demonstrate change detection; not a real notice.)',
    'DEMO DATA — Simulated notice: a new circular about counselling documents was added. (Generated only to demonstrate change detection; not a real notice.)',
    'DEMO DATA — Simulated notice: the contact section was reorganised. (Generated only to demonstrate change detection; not a real notice.)',
]


@router.post('/demo/sources/{id}/simulate-change')
def simulate_change(id: int, db: Session = Depends(get_db)):
    """Append a clearly-labelled simulated passage to a DEMO source to demonstrate Phase 5."""
    s = db.get(Source, id)
    if not s:
        raise HTTPException(404, 'Source not found')
    if not (s.is_demo or s.status == 'DEMO_READY'):
        raise HTTPException(400, 'Change simulation is only allowed on DEMO DATA sources.')
    prev = latest_version(db, s.id)
    base = prev.text if prev else DEMO_TEXT.get(s.college_id, 'DEMO DATA — Indexed information from configured source.')
    n = db.query(UpdateEvent).filter(UpdateEvent.source_id == s.id, UpdateEvent.change_type == 'CONTENT_UPDATED').count()
    text = f"{base} {SIMULATED_NOTICES[n % len(SIMULATED_NOTICES)]}"
    if not prev:  # make sure there is a baseline version to diff against
        process_text(db, s, base, s.source_name, 'DEMO')
    return process_text(db, s, text, s.source_name, 'DEMO')


# ------------------------------------------------------------- monitoring (Phase 5)
class MonitorRequest(BaseModel):
    source_ids: list[int] | None = None


@router.post('/monitor/run')
def monitor_run(p: MonitorRequest | None = None):
    result = run_monitoring_cycle(trigger='manual', source_ids=(p.source_ids if p else None))
    if result.get('status') == 'ALREADY_RUNNING':
        raise HTTPException(409, result['message'])
    return result


@router.get('/monitor/status')
def monitor_status(db: Session = Depends(get_db)):
    last = db.query(MonitorRun).order_by(desc(MonitorRun.started_at)).first()
    return {**scheduler_status(), 'last_run': serialize_run(last) if last else None}


@router.get('/monitor/runs')
def monitor_runs(limit: int = 20, db: Session = Depends(get_db)):
    return [serialize_run(r) for r in db.query(MonitorRun).order_by(desc(MonitorRun.started_at)).limit(min(limit, 100))]


@router.get('/monitor/runs/{id}')
def monitor_run_detail(id: int, db: Session = Depends(get_db)):
    r = db.get(MonitorRun, id)
    if not r:
        raise HTTPException(404, 'Run not found')
    return serialize_run(r, include_details=True)


# ------------------------------------------------------------- change feed (Phase 5)
@router.get('/updates')
def updates(college_id: str = '', change_type: str = '', limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(UpdateEvent)
    if college_id:
        q = q.filter(UpdateEvent.college_id == college_id)
    if change_type:
        q = q.filter(UpdateEvent.change_type == change_type)
    rows = q.order_by(desc(UpdateEvent.detected_date), desc(UpdateEvent.id)).limit(min(limit, 200)).all()
    by_id = {s.id: s for s in db.query(Source).filter(Source.id.in_({u.source_id for u in rows})).all()}
    return [update_event(u, by_id) for u in rows]


@router.get('/updates/{id}')
def update_detail(id: int, db: Session = Depends(get_db)):
    u = db.get(UpdateEvent, id)
    if not u:
        raise HTTPException(404, 'Update not found')
    s = db.get(Source, u.source_id)
    return update_event(u, {s.id: s} if s else {}, include_diff=True)


# ------------------------------------------------------------- status & analytics
@router.get('/admin/status')
def status(db: Session = Depends(get_db)):
    n, driver = count()
    return {'colleges': db.query(College).count(), 'sources': db.query(Source).count(),
            'events': db.query(IngestionEvent).count(), 'chunks': n, 'vector_driver': driver,
            'updates': [{'id': u.id, 'college_id': u.college_id, 'change_type': u.change_type, 'detected_date': u.detected_date}
                        for u in db.query(UpdateEvent).order_by(desc(UpdateEvent.detected_date)).limit(8)]}


@router.get('/analytics')
def analytics(days: int = 14, db: Session = Depends(get_db)):
    return build_analytics(db, days=max(1, min(days, 90)))


@router.get('/ingestion-events')
def events(limit: int = 30, db: Session = Depends(get_db)):
    names = {s.id: s.source_name for s in db.query(Source).all()}
    return [{'id': e.id, 'source_id': e.source_id, 'source_name': names.get(e.source_id), 'status': e.status,
             'document_title': e.document_title, 'chunks_created': e.chunks_created, 'message': e.message,
             'monitor_run_id': e.monitor_run_id, 'created_at': e.created_at}
            for e in db.query(IngestionEvent).order_by(desc(IngestionEvent.created_at)).limit(min(limit, 200))]


# ------------------------------------------------------------- AI & decision support
class Ask(BaseModel):
    query: str
    intent: str = 'general'
    college_ids: list[str] = []
    live: bool = True  # on-demand lookup (official crawl → NIRF → third-party) when the index has no answer


def _log_query(db, p: Ask, result: dict):
    db.add(QueryLog(query=p.query[:500], normalized_query=re.sub(r'\s+', ' ', p.query.lower()).strip(' ?.!')[:200],
                    intent=result.get('intent'), college_ids=','.join(result.get('college_ids') or []),
                    hits=len(result.get('sources') or []), answered=bool(result.get('grounded')), mode=result.get('mode'),
                    retrieval_ms=result['latency']['retrieval_ms'], total_ms=result['latency']['total_ms']))
    db.commit()


_PROBES: dict = {}  # probe results reused by the live follow-up request (2 min)


@router.post('/ask')
def ask(p: Ask, db: Session = Depends(get_db)):
    if not p.query.strip():
        raise HTTPException(422, 'A question is required.')
    registry = _registry(db)
    key = (p.query.strip().lower(), tuple(p.college_ids), p.intent)
    cached = _PROBES.pop(key, None) if p.live else None
    if cached and time.time() - cached[0] < 120:
        result = cached[1]  # the probe already ran understanding + retrieval + LLM for this question
    elif p.college_ids:  # explicit scope from the UI/API: plain grounded answer
        result = answer(p.query, p.college_ids, p.intent, db=db, registry=registry)
    else:
        result = qa_engine.ask(db, p.query, registry)
    qtype = result.get('query_type', 'FACT')

    if qtype == 'COMPARE':
        missing = any(cell['text'] == qa_engine.NOT_IN_SOURCES for row in result['table']['rows'] for cell in row['cells'])
        topic = 'compare:' + ','.join(sorted(result['understanding'].get('topics') or ['general']))
        plan = live_lookup.fill_plan(db, result['college_ids'][:3], topic) if missing else None
        if plan and not p.live:
            _PROBES[key] = (time.time(), dict(result))
            result['live_available'] = {**plan, 'domain': ', '.join(plan['domains'])}
            return result  # UI shows this table now and "Checking <domains>…" while the follow-up fills gaps
        if plan and p.live:
            report = live_lookup.fill(db, plan['colleges'], topic)
            started = time.perf_counter()
            qu = {**result['understanding'], 'subqueries': result['understanding'].get('subqueries') or []}
            refreshed = qa_engine.compare(db, p.query, qu, started)
            refreshed['latency']['total_ms'] = round(result['latency']['total_ms'] + refreshed['latency']['total_ms'], 1)
            if report['fetched']:
                refreshed['answer_label'] = 'Cited comparison · fetched live from ' + ', '.join(report['domains'])
            refreshed['live'] = {'step': 'official' if report['fetched'] else 'none', 'domain': ', '.join(report['domains']),
                                 'checked': report['checked'], 'fetched': report['fetched'], 'cached': False}
            result = refreshed
    elif not result['grounded'] and qtype == 'FACT':
        if p.live:
            result = live_lookup.resolve(db, p.query, result, registry)
            if not result['grounded'] and result.get('college_ids'):
                cites = qa_engine.Citations(db)
                extra = qa_engine.related_facts(db, result['college_ids'], cites)
                if extra:  # partial evidence: say what IS published, with citations
                    result['answer'] = result['answer'] + ' ' + extra
                    result['sources'] = cites.views
                    result['partial'] = True
        else:
            plan = live_lookup.plan(db, result)
            if plan:
                _PROBES[key] = (time.time(), dict(result))
                result['live_available'] = plan  # UI shows "Checking <domain>…" and repeats with live=true
                return result  # not logged: the follow-up live request is the one that counts
    _log_query(db, p, result)
    return result


@router.post('/compare')
def compare(p: Ask, db: Session = Depends(get_db)):
    return answer(p.query, p.college_ids or None, 'comparison', db=db, registry=_registry(db))


class WebResearch(BaseModel):
    question: str


OFFICIAL_FIRST = {'OFFICIAL': 0, 'UNVERIFIED': 1, 'THIRD_PARTY': 2}


@router.post('/web-research')
def web_research(p: WebResearch):
    """EXPERIMENTAL: Gemini + Google Search grounding. Not limited to indexed sources."""
    from ..ai import gemini_client

    q = re.sub(r'\s+', ' ', p.question or '').strip()[:500]
    if not q:
        raise HTTPException(422, 'A question is required.')
    if not gemini_client.is_configured():
        raise HTTPException(503, 'Live web research needs a Gemini API key. The source-grounded answer above is unaffected.')
    started = time.perf_counter()
    try:
        r = gemini_client.web_research(q)
    except gemini_client.GeminiUnavailable as exc:
        reason = ' (Google Search quota for this API key is used up)' if '429' in str(exc) else ''
        raise HTTPException(503, f'Live web research is temporarily unavailable{reason}. Please use the source-grounded answer above.')
    sources = []
    for s in r['sources']:
        domain_url = f"https://{s['domain']}/" if s.get('domain') else s['url']
        sources.append({**s, 'verification': classify_source(domain_url)})
    sources.sort(key=lambda s: OFFICIAL_FIRST.get(s['verification']['status'], 3))
    return {'answer': r['answer'], 'sources': sources, 'provider': 'gemini', 'model': r['model'], 'mode': 'web',
            'experimental': True, 'latency_ms': round((time.perf_counter() - started) * 1000, 1)}


class CompareRequest(BaseModel):
    college_ids: list[str]


@router.post('/compare/evidence')
def compare_evidence_route(p: CompareRequest, db: Session = Depends(get_db)):
    ids = [c for c in p.college_ids if db.get(College, c)][:3]
    if not ids:
        raise HTTPException(422, 'Select at least one known college.')
    data = compare_evidence(ids, lambda text, cid: retrieve(text, [cid], min_relevance=0.0)['hits'])
    data['generated_at'] = datetime.utcnow()
    return data


class Rec(BaseModel):
    branch: str = ''
    location: str = ''
    type: str = ''
    hostel: bool = False
    placement: bool = False


@router.post('/recommend')
def rec(p: Rec, db: Session = Depends(get_db)):
    return recommend([college(c) for c in db.query(College).all()], p.model_dump(),
                     evidence=lambda cid, text: bool(retrieve(text, [cid])['hits']))
