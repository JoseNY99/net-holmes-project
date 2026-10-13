from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class NoteCreate(BaseModel):
    contenido: str

class NoteResponse(BaseModel):
    id: int
    suspect_id: int
    user_id: int
    contenido: str
    created_at: datetime

    model_config = {"from_attributes": True}
