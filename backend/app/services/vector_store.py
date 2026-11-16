import os, json, hashlib
from pathlib import Path
DATA=Path('data/chunks.json')
def _load():
 DATA.parent.mkdir(exist_ok=True)
 return json.loads(DATA.read_text()) if DATA.exists() else []
def upsert(chunks):
 try:
  import chromadb
  client=chromadb.PersistentClient(path=os.getenv('CHROMA_PATH','./chroma')); col=client.get_or_create_collection('campusatlas')
  col.upsert(ids=[c['id'] for c in chunks],documents=[c['text'] for c in chunks],metadatas=[c['metadata'] for c in chunks]); return 'chromadb'
 except Exception:
  old=[c for c in _load() if c['metadata']['source_id'] != chunks[0]['metadata']['source_id']]; DATA.write_text(json.dumps(old+chunks)); return 'local fallback'
def query(text, college_ids=None, n=8):
 try:
  import chromadb
  col=chromadb.PersistentClient(path=os.getenv('CHROMA_PATH','./chroma')).get_or_create_collection('campusatlas'); r=col.query(query_texts=[text],n_results=n,include=['documents','metadatas','distances'])
  return [{'text':d,'metadata':m,'score':1-(dist or 0)} for d,m,dist in zip(r['documents'][0],r['metadatas'][0],r['distances'][0]) if not college_ids or m['college_id'] in college_ids]
 except Exception:
  terms=set(text.lower().split()); out=[]
  for c in _load():
   if college_ids and c['metadata']['college_id'] not in college_ids: continue
   out.append({**c,'score':len(terms & set(c['text'].lower().split()))})
  return sorted(out,key=lambda x:x['score'],reverse=True)[:n]
def count():
 try:
  import chromadb
  return chromadb.PersistentClient(path=os.getenv('CHROMA_PATH','./chroma')).get_or_create_collection('campusatlas').count(),'ChromaDB'
 except Exception: return len(_load()),'Local JSON fallback'
