from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class College(Base):
    __tablename__ = "colleges"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String)
    city = Column(String)
    state = Column(String)
    official_domain = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sources = relationship("Source", back_populates="college", cascade="all,delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    college_id = Column(String, ForeignKey("colleges.id"))
    source_name = Column(String)
    source_url = Column(String)
    source_type = Column(String)
    authority_level = Column(String)
    last_checked = Column(DateTime)
    last_changed = Column(DateTime)
    content_hash = Column(String)
    status = Column(String, default="ACTIVE")  # ACTIVE | DEMO_READY | FETCH_FAILED | DISABLED
    last_error = Column(Text)  # Phase 5: why the last fetch failed (source kept, marked missing)
    is_demo = Column(Boolean, default=False)  # Phase 5: DEMO DATA label kept explicit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    college = relationship("College", back_populates="sources")


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"))
    status = Column(String)
    document_title = Column(String)
    chunks_created = Column(Integer, default=0)
    message = Column(Text)
    monitor_run_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentVersion(Base):
    """Phase 5: every distinct version of a source's extracted text."""

    __tablename__ = "content_versions"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), index=True)
    version_no = Column(Integer)
    content_hash = Column(String)
    text = Column(Text)
    char_count = Column(Integer)
    document_title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class UpdateEvent(Base):
    __tablename__ = "update_events"
    id = Column(Integer, primary_key=True)
    college_id = Column(String)
    source_id = Column(Integer)
    detected_date = Column(DateTime, default=datetime.utcnow)
    change_type = Column(String)  # NEW_SOURCE_CONTENT | CONTENT_UPDATED
    old_hash = Column(String)
    new_hash = Column(String)
    # Phase 5 change intelligence
    old_version_id = Column(Integer)
    new_version_id = Column(Integer)
    summary = Column(Text)
    summary_mode = Column(String)  # groq | deterministic
    diff = Column(Text)
    added_count = Column(Integer, default=0)
    removed_count = Column(Integer, default=0)
    monitor_run_id = Column(Integer, nullable=True)


class MonitorRun(Base):
    """Phase 5: one execution of the source-monitoring job."""

    __tablename__ = "monitor_runs"
    id = Column(Integer, primary_key=True)
    trigger = Column(String)  # scheduled | manual | startup | test
    status = Column(String)  # RUNNING | SUCCESS | PARTIAL | FAILED
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    duration_ms = Column(Integer)
    sources_checked = Column(Integer, default=0)
    changes_found = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    details = Column(Text)  # JSON list of per-source results


class QueryLog(Base):
    """Phase 5 analytics: every question asked through /api/ask."""

    __tablename__ = "query_logs"
    id = Column(Integer, primary_key=True)
    query = Column(Text)
    normalized_query = Column(String, index=True)
    intent = Column(String)
    college_ids = Column(String)
    hits = Column(Integer)
    answered = Column(Boolean)
    mode = Column(String)
    retrieval_ms = Column(Float)
    total_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class LiveLookup(Base):
    """On-demand lookup cache: one row per college + topic search (24 h reuse)."""

    __tablename__ = "live_lookups"
    id = Column(Integer, primary_key=True)
    college_id = Column(String, index=True)
    topic = Column(String)
    outcome = Column(String)  # official | nirf | third_party | none
    result = Column(Text)  # JSON: label, checked, fetched, links
    created_at = Column(DateTime, default=datetime.utcnow)


class CollegeFact(Base):
    """Structured, cited facts (e.g. NIRF rank, median salary) used by comparisons."""

    __tablename__ = "college_facts"
    id = Column(Integer, primary_key=True)
    college_id = Column(String, index=True)
    field = Column(String)  # nirf_rank | nirf_band | nirf_score | median_salary_ug | ug_intake
    value = Column(String)
    num = Column(Float)
    year = Column(String)
    source_id = Column(Integer)
    source_url = Column(String)
    source_name = Column(String)
    evidence = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
