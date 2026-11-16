from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..database import get_db
from ..models.models import College,Source,IngestionEvent,UpdateEvent
from ..ingestion.pipeline import ingest
from ..services.vector_store import count
from ..retrieval.rag import answer
from ..recommendations.engine import recommend
router=APIRouter()
def college(c): return {'id':c.id,'name':c.name,'category':c.category,'city':c.city,'state':c.state,'official_domain':c.official_domain}
def source(s): return {'id':s.id,'college_id':s.college_id,'source_name':s.source_name,'source_url':s.source_url,'source_type':s.source_type,'authority_level':s.authority_level,'status':s.status,'last_checked':s.last_checked,'last_changed':s.last_changed,'content_hash':s.content_hash}
@router.get('/colleges')
def colleges(q:str='',category:str='',db:Session=Depends(get_db)):
 x=db.query(College)
 if q:x=x.filter(College.name.ilike(f'%{q}%'))
 if category:x=x.filter(College.category==category)
 return [college(v) for v in x.all()]
@router.get('/colleges/{id}')
def one(id:str,db:Session=Depends(get_db)):
 c=db.get(College,id)
 if not c:raise HTTPException(404,'College not found')
 return {**college(c),'sources':[source(s) for s in c.sources]}
@router.get('/sources')
def sources(db:Session=Depends(get_db)): return [source(s) for s in db.query(Source).all()]
class NewSource(BaseModel): college_id:str;source_name:str;source_url:str;source_type:str='PUBLIC_SOURCE';authority_level:str='MEDIUM'
@router.post('/sources')
def add_source(p:NewSource,db:Session=Depends(get_db)):
 s=Source(**p.model_dump());db.add(s);db.commit();db.refresh(s);return source(s)
@router.post('/sources/{id}/disable')
def disable(id:int,db:Session=Depends(get_db)):
 s=db.get(Source,id);s.status='DISABLED';db.commit();return source(s)
@router.post('/sources/{id}/ingest')
def run_ingestion(id:int,db:Session=Depends(get_db)):
 try:return ingest(db,id)
 except Exception as e:raise HTTPException(400,str(e))
@router.post('/demo/seed-knowledge')
def seed_knowledge(db:Session=Depends(get_db)):
 results=[]
 for s in db.query(Source).filter(Source.status=='DEMO_READY'): results.append(ingest(db,s.id))
 return results
@router.get('/admin/status')
def status(db:Session=Depends(get_db)):
 n,driver=count();return {'colleges':db.query(College).count(),'sources':db.query(Source).count(),'events':db.query(IngestionEvent).count(),'chunks':n,'vector_driver':driver,'updates':[{'id':u.id,'college_id':u.college_id,'change_type':u.change_type,'detected_date':u.detected_date} for u in db.query(UpdateEvent).order_by(desc(UpdateEvent.detected_date)).limit(8)]}
@router.get('/ingestion-events')
def events(db:Session=Depends(get_db)):return [{'id':e.id,'source_id':e.source_id,'status':e.status,'document_title':e.document_title,'chunks_created':e.chunks_created,'message':e.message,'created_at':e.created_at} for e in db.query(IngestionEvent).order_by(desc(IngestionEvent.created_at)).limit(30)]
class Ask(BaseModel): query:str;intent:str='general';college_ids:list[str]=[]
@router.post('/ask')
def ask(p:Ask): return answer(p.query,p.college_ids or None,p.intent)
@router.post('/compare')
def compare(p:Ask): return answer(p.query,p.college_ids or None,'comparison')
class Rec(BaseModel): branch:str='';location:str='';type:str='';hostel:bool=False;placement:bool=False
@router.post('/recommend')
def rec(p:Rec,db:Session=Depends(get_db)):return recommend([college(c) for c in db.query(College).all()],p.model_dump())
