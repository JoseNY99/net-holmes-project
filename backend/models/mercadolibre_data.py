from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class ReporteMercadoLibreData(Base):
    __tablename__ = "reporte_mercadolibre_data"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    seller_id = Column(String(100), nullable=True)
    seller_nickname = Column(String(200), nullable=True)
    seller_reputation_level = Column(String(100), nullable=True)
    seller_reputation_score = Column(String(50), nullable=True)
    seller_transactions_completed = Column(Integer, nullable=True)
    item_id = Column(String(100), nullable=True)
    item_condition = Column(String(50), nullable=True)
    category_id = Column(String(100), nullable=True)
    category_name = Column(String(200), nullable=True)
    shipping_mode = Column(String(100), nullable=True)
    available_stock = Column(Integer, nullable=True)
    sold_quantity = Column(Integer, nullable=True)
    questions_count = Column(Integer, nullable=True)
    warranty_text = Column(Text, nullable=True)
    official_store_id = Column(String(100), nullable=True)
    image_urls = Column(Text, nullable=True) # JSON string
    image_hashes = Column(Text, nullable=True) # JSON string
    post_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    reporte = relationship("ReporteBrandDefense", backref="mercadolibre_data", uselist=False)
