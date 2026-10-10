from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class CorrelationCluster(Base):
    __tablename__ = "correlation_clusters"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, index=True, nullable=False) # e.g. "Cluster-YYYY-MM-DD-XXXX"
    descripcion = Column(Text, nullable=True)
    total_cuentas = Column(Integer, default=0)
    score_promedio = Column(Float, default=0.0)
    estado = Column(String(50), default="activo") # activo / archivado / confirmado
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    links = relationship("CorrelationLink", back_populates="cluster", cascade="all, delete-orphan")
