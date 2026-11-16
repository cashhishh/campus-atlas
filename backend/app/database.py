import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv
load_dotenv()
DB_URL=os.getenv('DATABASE_URL','sqlite:///./campusatlas.db')
engine=create_engine(DB_URL, connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine, autocommit=False, autoflush=False)
class Base(DeclarativeBase): pass
def get_db():
 db=SessionLocal()
 try: yield db
 finally: db.close()
def init_db():
 from .models.models import College, Source, IngestionEvent, UpdateEvent
 Base.metadata.create_all(bind=engine)
 from .seed import seed
 db=SessionLocal(); seed(db); db.close()
