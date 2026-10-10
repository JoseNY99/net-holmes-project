from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class AuditLogResponse(BaseModel):
    id: int
    reporte_id: int
    user_id: int
    user_nombre: Optional[str] = None
    campo: str
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
