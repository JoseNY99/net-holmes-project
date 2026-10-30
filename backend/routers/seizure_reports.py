"""API del módulo Informes de Allanamiento."""

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth_middleware import get_current_user
from models.seizure_report import SeizureFile, SeizureReport
from models.user import User
from schemas.seizure_report import (
    PaginatedSeizureReports, SeizureFileOrder, SeizureFileOut, SeizureFileUpdate,
    SeizureReportIn, SeizureReportOut, TransitionIn,
)
from services import seizure_report_service as service

router = APIRouter(prefix="/api/seizure-reports", tags=["Informes de Allanamiento"])


def _require_edit_access(report: SeizureReport, user: User) -> None:
    if report.status not in {"BORRADOR", "OBSERVADO"}:
        raise HTTPException(409, "Este informe ya no admite edición")
    if report.created_by != user.id and user.rol not in {"admin", "sup_admin"}:
        raise HTTPException(403, "No puede editar este informe")


@router.get("/", response_model=PaginatedSeizureReports)
def listing(search: str | None = None, status: str | None = None, brand_id: int | None = None,
            country: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return service.list_reports(db, search=search, status=status, brand_id=brand_id, country=country, skip=skip, limit=limit)


@router.post("/", response_model=SeizureReportOut, status_code=201)
def create(data: SeizureReportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.apply_payload(db, SeizureReport(created_by=user.id), data, user.id)


@router.get("/{report_id}", response_model=SeizureReportOut)
def detail(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return service.get_report(db, report_id)


@router.put("/{report_id}", response_model=SeizureReportOut)
def update(report_id: int, data: SeizureReportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = service.get_report(db, report_id)
    _require_edit_access(report, user)
    return service.apply_payload(db, report, data, user.id)


@router.post("/{report_id}/transition", response_model=SeizureReportOut)
def change_status(report_id: int, data: TransitionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = service.get_report(db, report_id)
    if report.created_by != user.id and user.rol not in {"admin", "sup_admin"}:
        raise HTTPException(403, "No puede modificar el estado de este informe")
    return service.transition(db, report, data.status, data.comment, user)


@router.post("/{report_id}/photos", status_code=201)
async def upload_photos(report_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report=service.get_report(db,report_id); start=len(report.files); rows=[]
    _require_edit_access(report, user)
    for index,upload in enumerate(files): rows.append(await service.store_upload(db,report,upload,"photo",user.id,start+index))
    return [{"id":r.id,"name":r.original_name} for r in rows]


@router.post("/{report_id}/documents", status_code=201)
async def upload_documents(report_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report=service.get_report(db,report_id); start=len(report.files); rows=[]
    _require_edit_access(report, user)
    for index,upload in enumerate(files): rows.append(await service.store_upload(db,report,upload,"document",user.id,start+index))
    return [{"id":r.id,"name":r.original_name} for r in rows]


@router.post("/extract/police-pdf")
async def extract_pdf(file: UploadFile = File(...), _user: User = Depends(get_current_user)):
    if file.content_type != "application/pdf": raise HTTPException(415,"Se requiere un PDF")
    content=await file.read()
    if len(content)>20*1024*1024: raise HTTPException(413,"El PDF supera 20 MB")
    try: return service.extract_police_pdf(BytesIO(content))
    except Exception as exc: raise HTTPException(422,"No se pudo leer el documento policial") from exc


@router.delete("/{report_id}/files/{file_id}", status_code=204)
def delete_file(report_id: int, file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_edit_access(service.get_report(db, report_id), user)
    row=db.query(SeizureFile).filter_by(id=file_id,report_id=report_id).first()
    if not row: raise HTTPException(404,"Archivo no encontrado")
    service.audit_event(db, report_id, user.id, "FILE_DELETED", entity_type="file", entity_id=row.id,
                        details={"kind": row.kind, "name": row.original_name})
    (service.STORAGE/row.stored_name).unlink(missing_ok=True); db.delete(row); db.commit()


@router.patch("/{report_id}/files/{file_id}", response_model=SeizureFileOut)
def update_file(report_id: int, file_id: int, data: SeizureFileUpdate,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_edit_access(service.get_report(db, report_id), user)
    row = db.query(SeizureFile).filter_by(id=file_id, report_id=report_id).first()
    if not row:
        raise HTTPException(404, "Archivo no encontrado")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    service.audit_event(db, report_id, user.id, "FILE_UPDATED", entity_type="file", entity_id=row.id,
                        details={"fields": list(data.model_dump(exclude_unset=True))})
    db.commit(); db.refresh(row)
    return row


@router.post("/{report_id}/files/reorder", response_model=list[SeizureFileOut])
def reorder_files(report_id: int, data: SeizureFileOrder,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = service.get_report(db, report_id)
    _require_edit_access(report, user)
    rows = {row.id: row for row in report.files}
    if len(set(data.file_ids)) != len(data.file_ids) or any(file_id not in rows for file_id in data.file_ids):
        raise HTTPException(422, "La lista contiene archivos inválidos o repetidos")
    if set(data.file_ids) != set(rows):
        raise HTTPException(422, "Debe indicar todos los archivos del informe")
    for position, file_id in enumerate(data.file_ids):
        rows[file_id].position = position
    service.audit_event(db, report_id, user.id, "FILES_REORDERED", details={"file_ids": data.file_ids})
    db.commit()
    return sorted(rows.values(), key=lambda row: row.position)


@router.get("/{report_id}/download/{fmt}")
def download(report_id: int, fmt: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report=service.get_report(db,report_id)
    if fmt not in {"pdf","docx"}: raise HTTPException(422,"Formato inválido")
    path=service.generate_pdf(report,user.id) if fmt=="pdf" else service.generate_docx(report,user.id)
    service.register_version(db,report,path,fmt,user.id)
    media="application/pdf" if fmt=="pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path,media_type=media,filename=f"{report.internal_reference or 'BORRADOR'}_SEIZURE_REPORT.{fmt}")


@router.post("/{report_id}/generate")
def generate_documents(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = service.get_report(db, report_id)
    pdf = service.generate_pdf(report, user.id)
    word = service.generate_docx(report, user.id)
    pdf_version = service.register_version(db, report, pdf, "pdf", user.id)
    word_version = service.register_version(db, report, word, "docx", user.id)
    return {
        "report_id": report.id,
        "pdf": {"file": pdf.name, "version": pdf_version.version},
        "docx": {"file": word.name, "version": word_version.version},
    }


@router.get("/{report_id}/history")
def history(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    report=service.get_report(db,report_id)
    return [{"from_status":h.from_status,"to_status":h.to_status,"comment":h.comment,"user_id":h.user_id,"created_at":h.created_at} for h in report.history]


@router.get("/{report_id}/audit")
def audit(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    report = service.get_report(db, report_id)
    return [{
        "id": row.id, "action": row.action, "entity_type": row.entity_type,
        "entity_id": row.entity_id, "details": row.details, "user_id": row.user_id,
        "user_name": f"{row.user.nombre} {row.user.apellido}".strip() if row.user else None,
        "created_at": row.created_at,
    } for row in report.audit_events]
