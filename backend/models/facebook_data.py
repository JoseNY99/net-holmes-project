from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class ReporteFacebookData(Base):
    __tablename__ = "reporte_facebook_data"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    listing_id = Column(String(100), nullable=True)
    seller_profile_url = Column(Text, nullable=True)
    marketplace_category = Column(String(100), nullable=True)
    item_condition = Column(String(50), nullable=True)
    delivery_method = Column(String(100), nullable=True)
    seller_name = Column(String(200), nullable=True)
    seller_location_city = Column(String(100), nullable=True)
    seller_location_province = Column(String(100), nullable=True)
    comments_count = Column(Integer, nullable=True)
    comments_text = Column(Text, nullable=True) # JSON string
    post_date = Column(DateTime(timezone=True), nullable=True)
    image_urls = Column(Text, nullable=True) # JSON string
    image_hashes = Column(Text, nullable=True) # JSON string
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship back to main reporte
    reporte = relationship("ReporteBrandDefense", backref="facebook_data", uselist=False)
