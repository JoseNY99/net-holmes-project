"""Modelos aislados del módulo Informes de Allanamiento."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class SeizureReport(Base):
    __tablename__ = "seizure_reports"

    id = Column(Integer, primary_key=True)
    internal_reference = Column(String(30), unique=True, nullable=True, index=True)
    client_case_number = Column(String(100), nullable=True)
    status = Column(String(40), nullable=False, default="BORRADOR", index=True)
    country = Column(String(100), nullable=False, default="Argentina")
    province = Column(String(120), nullable=True)
    city = Column(String(120), nullable=True)
    operation_date = Column(Date, nullable=True)
    case_origin = Column(String(200), nullable=True)
    action_type = Column(String(120), nullable=True)
    report_type = Column(String(30), nullable=False, default="ALLANAMIENTO", index=True)
    client_name = Column(String(200), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True, index=True)
    brand_name = Column(String(200), nullable=True)
    brand_code = Column(String(10), nullable=True)
    investigator = Column(String(200), nullable=True)
    general_notes = Column(Text, nullable=True)
    police_agency = Column(Text, nullable=True)
    police_unit = Column(Text, nullable=True)
    court = Column(Text, nullable=True)
    judge = Column(Text, nullable=True)
    prosecution = Column(Text, nullable=True)
    prosecutor = Column(Text, nullable=True)
    court_case_number = Column(String(100), nullable=True)
    authorities_notes = Column(Text, nullable=True)
    media_impact = Column(Text, nullable=True)
    political_impact = Column(Text, nullable=True)
    proposed_fees = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=True, default="USD")
    internal_comments = Column(Text, nullable=True)
    background = Column(Text, nullable=True)
    operation_summary = Column(Text, nullable=True)
    seized_goods_total = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    brand = relationship("Brand", lazy="joined")
    creator = relationship("User", lazy="joined")
    targets = relationship("SeizureTarget", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureTarget.id")
    products = relationship("SeizureProduct", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureProduct.id")
    files = relationship("SeizureFile", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureFile.position")
    history = relationship("SeizureHistory", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureHistory.created_at")
    versions = relationship("SeizureDocumentVersion", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureDocumentVersion.version")
    audit_events = relationship("SeizureAuditEvent", cascade="all, delete-orphan", lazy="selectin", order_by="SeizureAuditEvent.created_at")


class SeizureTarget(Base):
    __tablename__ = "seizure_targets"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    establishment_name = Column(String(250), nullable=True)
    address = Column(String(350), nullable=False)
    city = Column(String(120), nullable=True)
    province = Column(String(120), nullable=True)
    country = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    investigated_party = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)


class SeizureProduct(Base):
    __tablename__ = "seizure_products"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_name = Column(String(200), nullable=False)
    client_name = Column(String(200), nullable=True)
    category = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    unit = Column(String(50), nullable=False, default="unidades")
    establishment = Column(String(250), nullable=True)
    notes = Column(Text, nullable=True)


class SeizureFile(Base):
    __tablename__ = "seizure_files"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)  # photo/document
    document_type = Column(String(80), nullable=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    caption = Column(Text, nullable=True)
    brand_name = Column(String(200), nullable=True)
    establishment = Column(String(250), nullable=True)
    include_in_report = Column(Boolean, nullable=False, default=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class SeizureHistory(Base):
    __tablename__ = "seizure_history"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(40), nullable=True)
    to_status = Column(String(40), nullable=False)
    comment = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class SeizureSequence(Base):
    __tablename__ = "seizure_sequences"
    id = Column(Integer, primary_key=True)
    scope = Column(String(30), nullable=False, unique=True)
    last_value = Column(Integer, nullable=False, default=0)


class SeizureDocumentVersion(Base):
    __tablename__ = "seizure_document_versions"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    format = Column(String(10), nullable=False)
    stored_name = Column(String(255), nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("report_id", "version", "format", name="uq_seizure_version_format"),)


class SeizureAuditEvent(Base):
    """Bitácora aditiva del módulo; cada fila identifica actor, acción y fecha."""
    __tablename__ = "seizure_audit_events"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("seizure_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(60), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, default="report")
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    user = relationship("User", lazy="joined")
