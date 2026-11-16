from sqlalchemy import Column,Integer,String,DateTime,Text,ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base
class College(Base):
 __tablename__='colleges'; id=Column(String,primary_key=True); name=Column(String,nullable=False); category=Column(String); city=Column(String); state=Column(String); official_domain=Column(String,nullable=True); created_at=Column(DateTime,default=datetime.utcnow); sources=relationship('Source',back_populates='college',cascade='all,delete-orphan')
class Source(Base):
 __tablename__='sources'; id=Column(Integer,primary_key=True); college_id=Column(String,ForeignKey('colleges.id')); source_name=Column(String); source_url=Column(String); source_type=Column(String); authority_level=Column(String); last_checked=Column(DateTime); last_changed=Column(DateTime); content_hash=Column(String); status=Column(String,default='ACTIVE'); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); college=relationship('College',back_populates='sources')
class IngestionEvent(Base):
 __tablename__='ingestion_events'; id=Column(Integer,primary_key=True); source_id=Column(Integer,ForeignKey('sources.id')); status=Column(String); document_title=Column(String); chunks_created=Column(Integer,default=0); message=Column(Text); created_at=Column(DateTime,default=datetime.utcnow)
class UpdateEvent(Base):
 __tablename__='update_events'; id=Column(Integer,primary_key=True); college_id=Column(String); source_id=Column(Integer); detected_date=Column(DateTime,default=datetime.utcnow); change_type=Column(String); old_hash=Column(String); new_hash=Column(String)
