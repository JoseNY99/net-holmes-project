from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models.user import User
from models.reporte import ReporteBrandDefense
from models.correlation_cluster import CorrelationCluster
from models.correlation_link import CorrelationLink
from schemas.correlation import CorrelationClusterResponse, CorrelationLinkResponse, CorrelationAnalysisRequest, CorrelationAnalysisResult
from middleware.auth_middleware import get_current_user
from services.correlation_engine import CorrelationEngine

router = APIRouter(prefix="/api/correlations", tags=["Correlations"])

@router.get("/clusters", response_model=List[CorrelationClusterResponse])
def get_clusters(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    clusters = db.query(CorrelationCluster).order_by(CorrelationCluster.score_promedio.desc()).all()
    return clusters

@router.get("/clusters/{cluster_id}", response_model=CorrelationClusterResponse)
def get_cluster(cluster_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    cluster = db.query(CorrelationCluster).filter(CorrelationCluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster no encontrado")
    return cluster

@router.post("/analyze/{reporte_id}", response_model=CorrelationAnalysisResult)
def analyze_deep(reporte_id: int, request: CorrelationAnalysisRequest, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    result = CorrelationEngine.deep_analysis(db, reporte_id, request.dimensiones)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@router.get("/links/{reporte_id}", response_model=List[CorrelationLinkResponse])
def get_links(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    from sqlalchemy import or_
    links = db.query(CorrelationLink).filter(
        or_(CorrelationLink.reporte_a_id == reporte_id, CorrelationLink.reporte_b_id == reporte_id)
    ).all()
    return links

@router.post("/auto-correlate")
def auto_correlate(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Dispara la evaluación de las 5 dimensiones de correlación sobre los últimos 100 reportes."""
    reportes = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.id.desc()).limit(100).all()
    if not reportes:
        return {"msg": "No hay reportes suficientes."}
        
    reportes_ids = [r.id for r in reportes]
    # We can reuse analyze_new_reports but it only does 2 dimensions. Let's do all 5 here for the 100 reportes.
    # Actually, calling deep_analysis on each of the 100 reportes might be too heavy.
    # Let's just use a modified approach or reuse existing methods.
    
    recent_all = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.id.desc()).limit(1000).all()
    all_links = []
    
    from services.correlation_identifiers import analyze_identifiers
    from services.correlation_content import analyze_content
    from services.correlation_temporal import analyze_temporal
    from services.correlation_linguistic import analyze_linguistic
    from services.correlation_social_graph import analyze_social_graph
    
    for reporte in reportes:
        all_links.extend(analyze_identifiers(db, reporte, recent_all))
        all_links.extend(analyze_content(db, reporte, recent_all))
        all_links.extend(analyze_temporal(db, reporte, recent_all))
        all_links.extend(analyze_linguistic(db, reporte, recent_all))
        all_links.extend(analyze_social_graph(db, reporte, recent_all))
        
    stats = CorrelationEngine._save_and_cluster_links(db, all_links, "automatico_fase2")
    return {
        "msg": "Correlación automática completada.",
        "links_encontrados": stats["links"],
        "clusters_afectados": stats["clusters"]
    }
