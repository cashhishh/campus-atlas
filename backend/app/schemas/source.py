from pydantic import BaseModel

class SourceCreate(BaseModel):
    college_id: str
    source_name: str
    source_url: str
    source_type: str = 'PUBLIC_SOURCE'
    authority_level: str = 'MEDIUM'
