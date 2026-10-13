from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from schemas.reporte import ReporteResponse

class CorrelationLinkBase(BaseModel):
    tipo_correlacion: str
    subtipo: str
    score: float
    evidencia: Optional[str] = None
    detectado_por: Optional[str] = "automatico"

class CorrelationLinkResponse(CorrelationLinkBase):
    id: int
    cluster_id: int
    reporte_a_id: int
    reporte_b_id: int
    created_at: datetime
    # We will include basic reporter data
    reporte_a: Optional[ReporteResponse] = None
    reporte_b: Optional[ReporteResponse] = None

class CorrelationClusterBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    total_cuentas: int = 0
    score_promedio: float = 0.0
    estado: str = "activo"

class CorrelationClusterResponse(CorrelationClusterBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    links: List[CorrelationLinkResponse] = []

class CorrelationAnalysisRequest(BaseModel):
    dimensiones: List[str] = ["temporal", "linguistico", "contenido", "identificador"]

class CorrelationAnalysisResult(BaseModel):
    links_encontrados: int
    clusters_afectados: int
    resumen: str
