from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class CorrelationLink(Base):
    __tablename__ = "correlation_links"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("correlation_clusters.id", ondelete="CASCADE"), nullable=False)
    reporte_a_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), nullable=False)
    reporte_b_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), nullable=False)
    
    tipo_correlacion = Column(String(50), nullable=False) # temporal, linguistico, contenido, identificador, red
    subtipo = Column(String(100), nullable=False) # username_similar, mismo_telefono, etc.
    score = Column(Float, nullable=False) # 0.0 - 1.0
    evidencia = Column(Text, nullable=True) # JSON string with matched data
    detectado_por = Column(String(50), default="automatico") # automatico / manual
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cluster = relationship("CorrelationCluster", back_populates="links")
    reporte_a = relationship("ReporteBrandDefense", foreign_keys=[reporte_a_id])
    reporte_b = relationship("ReporteBrandDefense", foreign_keys=[reporte_b_id])
