from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, LargeBinary

from database import Base


class ReporteFinal(Base):
    __tablename__ = "reportes_finales"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(
        Integer,
        ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    completion_percentage = Column(Float, nullable=False)
    pdf_data = Column(LargeBinary, nullable=False)
    generated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )