from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class ReporteInstagramData(Base):
    __tablename__ = "reporte_instagram_data"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    username = Column(String(100), nullable=True)
    user_id_ig = Column(String(100), nullable=True)
    hashtags = Column(Text, nullable=True) # JSON array
    likes_count = Column(Integer, nullable=True)
    comments_count = Column(Integer, nullable=True)
    followers = Column(Integer, nullable=True)
    following = Column(Integer, nullable=True)
    bio_text = Column(Text, nullable=True)
    bio_links = Column(Text, nullable=True) # JSON array
    profile_pic_url = Column(Text, nullable=True)
    profile_pic_hash = Column(String(255), nullable=True)
    is_business_account = Column(Boolean, nullable=True)
    post_type = Column(String(50), nullable=True)
    post_date = Column(DateTime(timezone=True), nullable=True)
    mentioned_accounts = Column(Text, nullable=True) # JSON array
    image_urls = Column(Text, nullable=True) # JSON string
    image_hashes = Column(Text, nullable=True) # JSON string
    caption_full = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    reporte = relationship("ReporteBrandDefense", backref="instagram_data", uselist=False)
