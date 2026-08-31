import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from models.reporte import ReporteBrandDefense
from models.correlation_cluster import CorrelationCluster
from models.correlation_link import CorrelationLink
from schemas.correlation import CorrelationAnalysisResult

from services.correlation_identifiers import analyze_identifiers
from services.correlation_temporal import analyze_temporal
from services.correlation_linguistic import analyze_linguistic
from services.correlation_content import analyze_content
from services.correlation_social_graph import analyze_social_graph

class CorrelationEngine:
    @staticmethod
    def analyze_new_reports(db: Session, reportes_ids: list[int]):
        """
        Análisis automático ligero post-ingesta.
        Solo corre dimensiones rápidas: Identificadores y Contenido.
        """
        reportes = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.id.in_(reportes_ids)).all()
        # Para cada nuevo, compararlo con los últimos 1000 de la base para no colapsar la DB
        recent_all = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.id.desc()).limit(1000).all()
        
        all_links = []
        for reporte in reportes:
            links_ident = analyze_identifiers(db, reporte, recent_all)
            links_content = analyze_content(db, reporte, recent_all)
            all_links.extend(links_ident)
            all_links.extend(links_content)
            
        return CorrelationEngine._save_and_cluster_links(db, all_links, "automatico")

    @staticmethod
    def deep_analysis(db: Session, reporte_id: int, dimensiones: list[str]) -> dict:
        """
        Análisis profundo bajo demanda para un sospechoso.
        """
        target = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.id == reporte_id).first()
        if not target:
            return {"error": "Reporte no encontrado"}
            
        recent_all = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.id.desc()).limit(5000).all()
        
        all_links = []
        if "identificador" in dimensiones:
            all_links.extend(analyze_identifiers(db, target, recent_all))
        if "contenido" in dimensiones:
            all_links.extend(analyze_content(db, target, recent_all))
        if "temporal" in dimensiones:
            all_links.extend(analyze_temporal(db, target, recent_all))
        if "linguistico" in dimensiones:
            all_links.extend(analyze_linguistic(db, target, recent_all))
        if "social" in dimensiones:
            all_links.extend(analyze_social_graph(db, target, recent_all))
            
        stats = CorrelationEngine._save_and_cluster_links(db, all_links, "manual")
        return {
            "links_encontrados": stats["links"],
            "clusters_afectados": stats["clusters"],
            "resumen": f"Se encontraron {stats['links']} vínculos nuevos o actualizados."
        }

    @staticmethod
    def _save_and_cluster_links(db: Session, links_data: list[dict], origin: str) -> dict:
        """
        Union-Find con confirmación multi-dimensional.
        Un par de reportes solo forma/entra en un cluster si:
          a) Tiene al menos 1 link con score >= 0.90 (identificador directo), O
          b) Tiene links en ≥2 dimensiones diferentes entre sí.
        Esto evita que un solo edge temporal o lingüístico débil fusione clusters enteros.
        """
        saved_links = 0
        affected_clusters = set()
        
        # Agrupar links por par de reportes para evaluar multi-dimensional
        from collections import defaultdict
        pair_links = defaultdict(list)
        for data in links_data:
            ra = min(data["reporte_a_id"], data["reporte_b_id"])
            rb = max(data["reporte_a_id"], data["reporte_b_id"])
            pair_links[(ra, rb)].append(data)
        
        for (ra_id, rb_id), pair_data in pair_links.items():
            # Verificar confirmación multi-dimensional
            dimensiones_unicas = set(d["tipo_correlacion"] for d in pair_data)
            max_score = max(d["score"] for d in pair_data)
            
            # Regla: score >= 0.90 (identificador directo) o ≥2 dimensiones distintas
            if max_score < 0.90 and len(dimensiones_unicas) < 2:
                # Link débil de una sola dimensión — guardar el link pero NO crear/mergear cluster
                for data in pair_data:
                    existing = db.query(CorrelationLink).filter(
                        or_(
                            and_(CorrelationLink.reporte_a_id == data["reporte_a_id"], CorrelationLink.reporte_b_id == data["reporte_b_id"], CorrelationLink.tipo_correlacion == data["tipo_correlacion"]),
                            and_(CorrelationLink.reporte_a_id == data["reporte_b_id"], CorrelationLink.reporte_b_id == data["reporte_a_id"], CorrelationLink.tipo_correlacion == data["tipo_correlacion"])
                        )
                    ).first()
                    if existing:
                        continue
                    # Guardar sin cluster (cluster_id = None o en cluster aislado)
                    import uuid
                    uid = uuid.uuid4().hex[:8]
                    solo_cluster = CorrelationCluster(nombre=f"Débil-{uid}-{ra_id}")
                    db.add(solo_cluster)
                    db.flush()
                    
                    new_link = CorrelationLink(
                        cluster_id=solo_cluster.id,
                        reporte_a_id=data["reporte_a_id"],
                        reporte_b_id=data["reporte_b_id"],
                        tipo_correlacion=data["tipo_correlacion"],
                        subtipo=data["subtipo"],
                        score=data["score"],
                        evidencia=json.dumps(data.get("evidencia", {})),
                        detectado_por=origin
                    )
                    db.add(new_link)
                    saved_links += 1
                    affected_clusters.add(solo_cluster.id)
                continue
            
            # Link confirmado — proceder con clustering normal
            for data in pair_data:
                a_id = data["reporte_a_id"]
                b_id = data["reporte_b_id"]
                
                # Chequear si ya existe el link (ida o vuelta)
                existing = db.query(CorrelationLink).filter(
                    or_(
                        and_(CorrelationLink.reporte_a_id == a_id, CorrelationLink.reporte_b_id == b_id, CorrelationLink.tipo_correlacion == data["tipo_correlacion"]),
                        and_(CorrelationLink.reporte_a_id == b_id, CorrelationLink.reporte_b_id == a_id, CorrelationLink.tipo_correlacion == data["tipo_correlacion"])
                    )
                ).first()
                
                if existing:
                    continue
                    
                # Buscar a qué cluster pertenece
                cluster_a = db.query(CorrelationLink).filter(or_(CorrelationLink.reporte_a_id == a_id, CorrelationLink.reporte_b_id == a_id)).first()
                cluster_b = db.query(CorrelationLink).filter(or_(CorrelationLink.reporte_a_id == b_id, CorrelationLink.reporte_b_id == b_id)).first()
                
                target_cluster_id = None
                c_id_a = cluster_a.cluster_id if cluster_a else None
                c_id_b = cluster_b.cluster_id if cluster_b else None

                if c_id_a and c_id_b and c_id_a != c_id_b:
                    # Merge clusters: Move all links from cluster_b to cluster_a
                    links_to_move = db.query(CorrelationLink).filter(CorrelationLink.cluster_id == c_id_b).all()
                    for link in links_to_move:
                        link.cluster_id = c_id_a
                    db.flush()
                    old_cluster = db.query(CorrelationCluster).filter(CorrelationCluster.id == c_id_b).first()
                    if old_cluster:
                        db.delete(old_cluster)
                        db.flush()
                    target_cluster_id = c_id_a
                    affected_clusters.discard(c_id_b)
                elif c_id_a:
                    target_cluster_id = c_id_a
                elif c_id_b:
                    target_cluster_id = c_id_b
                else:
                    import uuid
                    uid = uuid.uuid4().hex[:8]
                    new_cluster = CorrelationCluster(nombre=f"Cluster-{uid}-{a_id}")
                    db.add(new_cluster)
                    db.flush()
                    db.refresh(new_cluster)
                    target_cluster_id = new_cluster.id
                    
                affected_clusters.add(target_cluster_id)
                
                # Guardar Link
                new_link = CorrelationLink(
                    cluster_id=target_cluster_id,
                    reporte_a_id=a_id,
                    reporte_b_id=b_id,
                    tipo_correlacion=data["tipo_correlacion"],
                    subtipo=data["subtipo"],
                    score=data["score"],
                    evidencia=json.dumps(data.get("evidencia", {})),
                    detectado_por=origin
                )
                db.add(new_link)
                saved_links += 1
            
        if saved_links > 0:
            db.commit()
            
            # Recalcular score y cuentas por cluster
            for c_id in affected_clusters:
                CorrelationEngine._update_cluster_stats(db, c_id)
                
        return {"links": saved_links, "clusters": len(affected_clusters)}

    @staticmethod
    def _update_cluster_stats(db: Session, cluster_id: int):
        cluster = db.query(CorrelationCluster).filter(CorrelationCluster.id == cluster_id).first()
        if not cluster: return
        
        links = db.query(CorrelationLink).filter(CorrelationLink.cluster_id == cluster_id).all()
        if not links: return
        
        # Calcular cuentas unicas
        cuentas = set()
        total_score = 0
        for l in links:
            cuentas.add(l.reporte_a_id)
            cuentas.add(l.reporte_b_id)
            total_score += l.score
            
        cluster.total_cuentas = len(cuentas)
        cluster.score_promedio = total_score / len(links)
        db.commit()
