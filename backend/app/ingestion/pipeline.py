import hashlib,re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import fitz
from ..models.models import Source,IngestionEvent,UpdateEvent
from ..services.vector_store import upsert
DEMO_TEXT={
'dtu':'DEMO DATA — Delhi Technological University is a public university in New Delhi. Undergraduate admissions are described through the configured admission source. Applicants should consult the official admission notice for current eligibility, counselling and dates.',
'mait':'DEMO DATA — Maharaja Agrasen Institute of Technology provides academic information through its institutional website. The configured academic source lists Electronics and Communication Engineering among academic offerings. Applicants should verify current intake and eligibility using official notices.',
'bits-pilani':'DEMO DATA — BITS Pilani academic material describes undergraduate academic programmes and campus facilities. Admission and fee details change by cycle; consult the official brochure for current information.',
'nit-trichy':'DEMO DATA — NIT Tiruchirappalli campus information describes student facilities and campus services. Hostel availability, allocation rules and current charges should be verified from current official notices.'}
def clean_html(raw):
 s=BeautifulSoup(raw,'html.parser')
 for tag in s(['nav','footer','script','style','header','aside']): tag.decompose()
 return re.sub(r'\s+',' ',s.get_text(' ',strip=True))
def chunks(text,size=700): return [text[i:i+size] for i in range(0,len(text),size) if len(text[i:i+size].strip())>30]
def ingest(db,source_id):
 src=db.get(Source,source_id)
 if not src: raise ValueError('Source not found')
 try:
  if src.status=='DEMO_READY': text=DEMO_TEXT.get(src.college_id,'DEMO DATA — Indexed information from configured source.') ; title=src.source_name
  else:
   r=httpx.get(src.source_url,timeout=20,follow_redirects=True); r.raise_for_status(); ct=r.headers.get('content-type','')
   if 'pdf' in ct or src.source_url.lower().endswith('.pdf'): text=' '.join(p.get_text() for p in fitz.open(stream=r.content,filetype='pdf')); title=src.source_name
   else: text=clean_html(r.text); title=BeautifulSoup(r.text,'html.parser').title.string if BeautifulSoup(r.text,'html.parser').title else src.source_name
  h=hashlib.sha256(text.encode()).hexdigest(); old=src.content_hash; changed=h!=old
  src.last_checked=datetime.utcnow()
  if changed:
   src.content_hash=h;src.last_changed=datetime.utcnow(); typ='NEW_SOURCE_CONTENT' if not old else 'CONTENT_UPDATED';db.add(UpdateEvent(college_id=src.college_id,source_id=src.id,change_type=typ,old_hash=old,new_hash=h))
   cs=chunks(text); payload=[{'id':f'{src.id}-{i}-{h[:8]}','text':v,'metadata':{'college_id':src.college_id,'source_id':src.id,'source_url':src.source_url,'source_name':src.source_name,'source_type':src.source_type,'authority_level':src.authority_level,'document_title':title or src.source_name,'ingested_at':datetime.utcnow().isoformat()}} for i,v in enumerate(cs)]; upsert(payload)
  else: cs=[]
  db.add(IngestionEvent(source_id=src.id,status='SUCCESS',document_title=title,chunks_created=len(cs),message='Indexed changed content' if changed else 'No content change'));db.commit();return {'status':'success','changed':changed,'chunks':len(cs)}
 except Exception as e:
  db.add(IngestionEvent(source_id=src.id,status='FAILED',chunks_created=0,message=str(e)));db.commit();raise
