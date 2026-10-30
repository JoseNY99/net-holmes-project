from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field


class TargetIn(BaseModel):
    establishment_name: str | None = None
    address: str = Field(min_length=2, max_length=350)
    city: str | None = None
    province: str | None = None
    country: str | None = None
    description: str | None = None
    investigated_party: str | None = Field(None, max_length=20_000)
    notes: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ProductIn(BaseModel):
    brand_name: str = Field(min_length=1, max_length=200)
    client_name: str | None = None
    category: str | None = None
    description: str | None = None
    quantity: int = Field(ge=0, le=100_000_000)
    unit: str = "unidades"
    establishment: str | None = None
    notes: str | None = None
    model_config = ConfigDict(from_attributes=True)


class SeizureReportIn(BaseModel):
    report_type: str = Field("ALLANAMIENTO", pattern="^(ALLANAMIENTO|INTELIGENCIA|ESTUDIO_MERCADO)$")
    country: str = "Argentina"
    province: str | None = None
    city: str | None = None
    operation_date: date | None = None
    case_origin: str | None = None
    action_type: str | None = None
    client_name: str | None = None
    brand_id: int | None = None
    brand_code: str | None = Field(None, max_length=10)
    client_case_number: str | None = None
    investigator: str | None = None
    general_notes: str | None = None
    police_agency: str | None = None
    police_unit: str | None = None
    court: str | None = None
    judge: str | None = None
    prosecution: str | None = None
    prosecutor: str | None = None
    court_case_number: str | None = None
    authorities_notes: str | None = None
    media_impact: str | None = None
    political_impact: str | None = None
    proposed_fees: str | None = None
    currency: str | None = "USD"
    internal_comments: str | None = None
    background: str | None = None
    operation_summary: str | None = None
    targets: list[TargetIn] = Field(default_factory=list)
    products: list[ProductIn] = Field(default_factory=list)


class TransitionIn(BaseModel):
    status: str
    comment: str | None = None


class SeizureFileUpdate(BaseModel):
    position: int | None = Field(None, ge=0)
    caption: str | None = None
    brand_name: str | None = None
    establishment: str | None = None
    document_type: str | None = None
    include_in_report: bool | None = None


class SeizureFileOrder(BaseModel):
    file_ids: list[int] = Field(min_length=1)


class SeizureFileOut(BaseModel):
    id: int
    kind: str
    document_type: str | None
    original_name: str
    mime_type: str
    size_bytes: int
    position: int
    caption: str | None
    brand_name: str | None
    establishment: str | None
    include_in_report: bool
    model_config = ConfigDict(from_attributes=True)


class SeizureReportOut(BaseModel):
    id: int
    internal_reference: str | None
    client_case_number: str | None
    status: str
    report_type: str
    country: str
    province: str | None
    city: str | None
    operation_date: date | None
    case_origin: str | None
    action_type: str | None
    client_name: str | None
    brand_id: int | None
    brand_name: str | None
    brand_code: str | None
    investigator: str | None
    general_notes: str | None
    police_agency: str | None
    police_unit: str | None
    court: str | None
    judge: str | None
    prosecution: str | None
    prosecutor: str | None
    court_case_number: str | None
    authorities_notes: str | None
    media_impact: str | None
    political_impact: str | None
    proposed_fees: str | None
    currency: str | None
    internal_comments: str | None
    background: str | None
    operation_summary: str | None
    seized_goods_total: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    targets: list[TargetIn] = Field(default_factory=list)
    products: list[ProductIn] = Field(default_factory=list)
    files: list[SeizureFileOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class PaginatedSeizureReports(BaseModel):
    items: list[SeizureReportOut]
    total: int
