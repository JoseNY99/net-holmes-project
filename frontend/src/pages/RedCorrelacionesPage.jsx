import React, { useState, useEffect } from 'react';
import { 
  FaNetworkWired, 
  FaSearch, 
  FaExclamationTriangle, 
  FaClock, 
  FaLink, 
  FaFileAlt, 
  FaUserCircle,
  FaTimes,
  FaExternalLinkAlt,
  FaShieldAlt,
  FaBolt,
  FaInfoCircle
} from 'react-icons/fa';
import correlationService from '../services/correlationService';
import { useNavigate } from 'react-router-dom';

const RedCorrelacionesPage = () => {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCluster, setSelectedCluster] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [correlating, setCorrelating] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchClusters();
  }, []);

  const fetchClusters = async () => {
    try {
      setLoading(true);
      const data = await correlationService.getClusters();
      // Filtrar clusters con baja certeza (<60%) o marcados como débiles aislados
      const validClusters = (data || []).filter(
        c => (c.score_promedio || 0) >= 0.60 && !c.nombre?.startsWith("Débil-")
      );
      setClusters(validClusters);
    } catch (error) {
      console.error("Error fetching clusters:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleInspectCluster = async (cluster) => {
    setSelectedNode(null);
    try {
      setModalLoading(true);
      const fullDetails = await correlationService.getClusterDetails(cluster.id);
      setSelectedCluster(fullDetails || cluster);
    } catch (e) {
      console.error("Error loading cluster details:", e);
      setSelectedCluster(cluster);
    } finally {
      setModalLoading(false);
    }
  };

  const handleAutoCorrelate = async () => {
    setCorrelating(true);
    setStatusMessage(null);
    try {
      const res = await correlationService.autoCorrelate();
      setStatusMessage({ 
        type: 'success', 
        text: `Correlación 5D completada: ${res.links_encontrados || 0} vínculos evaluados, ${res.clusters_afectados || 0} clusters actualizados.` 
      });
      await fetchClusters();
    } catch (e) {
      setStatusMessage({ type: 'error', text: 'Error al ejecutar correlación automática.' });
    } finally {
      setCorrelating(false);
    }
  };

  const getDimensionMeta = (dim) => {
    switch(dim) {
      case 'temporal': 
        return { color: '#2ECC71', label: 'Temporal', icon: <FaClock /> };
      case 'linguistico': 
        return { color: '#F39C12', label: 'Lingüístico', icon: <FaFileAlt /> };
      case 'contenido': 
        return { color: '#3498DB', label: 'Contenido', icon: <FaLink /> };
      case 'identificador': 
        return { color: '#E74C3C', label: 'Identificador', icon: <FaUserCircle /> };
      case 'grafo_social':
      case 'social':
        return { color: '#9B59B6', label: 'Grafo Social', icon: <FaNetworkWired /> };
      default: 
        return { color: '#10C5C9', label: dim, icon: <FaShieldAlt /> };
    }
  };

  // Helper para construir grafo SVG del cluster
  const renderClusterGraph = (cluster) => {
    const rawLinks = cluster.links || [];
    // Filtrar enlaces de muy baja certeza (< 0.65)
    const links = rawLinks.filter(l => (l.score || 0) >= 0.65);
    // Obtener lista única de nodos (reporte_ids)
    const nodeSet = new Set();
    links.forEach(l => {
      nodeSet.add(l.reporte_a_id);
      nodeSet.add(l.reporte_b_id);
    });

    const nodeIds = Array.from(nodeSet);
    if (nodeIds.length === 0) {
      for (let i = 1; i <= Math.min(cluster.total_cuentas || 3, 6); i++) {
        nodeIds.push(i);
      }
    }

    const width = 540;
    const height = 320;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.35;

    // Calcular posiciones circulares
    const nodePositions = {};
    nodeIds.forEach((id, idx) => {
      const angle = (idx / nodeIds.length) * 2 * Math.PI - Math.PI / 2;
      nodePositions[id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        id
      };
    });

    return (
      <div style={{ position: 'relative', width: '100%', background: 'rgba(7, 26, 46, 0.9)', borderRadius: '12px', border: '1px solid rgba(16, 197, 201, 0.25)', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 12, left: 16, zIndex: 2, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          <FaInfoCircle style={{ marginRight: 6, color: 'var(--accent-primary)' }} />
          Haz clic en cualquier nodo para inspeccionar el expediente.
        </div>
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
          {/* Aristas (Links) */}
          {links.length > 0 ? (
            links.map((link, idx) => {
              const posA = nodePositions[link.reporte_a_id];
              const posB = nodePositions[link.reporte_b_id];
              if (!posA || !posB) return null;
              const meta = getDimensionMeta(link.tipo_correlacion);
              const isSelected = selectedNode && (selectedNode === link.reporte_a_id || selectedNode === link.reporte_b_id);

              return (
                <g key={`link-${idx}`}>
                  <line 
                    x1={posA.x} 
                    y1={posA.y} 
                    x2={posB.x} 
                    y2={posB.y} 
                    stroke={meta.color} 
                    strokeWidth={Math.max(2, (link.score || 0.8) * 4)}
                    strokeOpacity={isSelected ? 1 : 0.65}
                    strokeDasharray={link.score < 0.7 ? "5,5" : "none"}
                  />
                  <circle 
                    cx={(posA.x + posB.x) / 2} 
                    cy={(posA.y + posB.y) / 2} 
                    r={isSelected ? 5 : 3} 
                    fill={meta.color}
                  />
                </g>
              );
            })
          ) : (
            nodeIds.map((idA, i) => 
              nodeIds.slice(i + 1).map((idB, j) => {
                const posA = nodePositions[idA];
                const posB = nodePositions[idB];
                return (
                  <line 
                    key={`default-${i}-${j}`}
                    x1={posA.x} 
                    y1={posA.y} 
                    x2={posB.x} 
                    y2={posB.y} 
                    stroke="#10C5C9" 
                    strokeWidth="2"
                    strokeOpacity="0.4"
                  />
                );
              })
            )
          )}

          {/* Nodos (Cuentas) */}
          {nodeIds.map(id => {
            const pos = nodePositions[id];
            const isSelected = selectedNode === id;

            return (
              <g 
                key={`node-${id}`} 
                style={{ cursor: 'pointer' }}
                onClick={() => setSelectedNode(id)}
              >
                {isSelected && (
                  <circle 
                    cx={pos.x} 
                    cy={pos.y} 
                    r="28" 
                    fill="none" 
                    stroke="#10C5C9" 
                    strokeWidth="2.5"
                    strokeDasharray="4,4"
                  />
                )}
                <circle 
                  cx={pos.x} 
                  cy={pos.y} 
                  r="20" 
                  fill={isSelected ? '#10C5C9' : '#0B3256'} 
                  stroke={isSelected ? '#FFFFFF' : '#10C5C9'} 
                  strokeWidth="2"
                />
                <text 
                  x={pos.x} 
                  y={pos.y + 4} 
                  textAnchor="middle" 
                  fill={isSelected ? '#0B3256' : '#FFFFFF'} 
                  fontSize="10" 
                  fontWeight="bold"
                  fontFamily="Inter, sans-serif"
                >
                  #{id}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <div className="page-container fade-in">
      <div className="detail-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FaNetworkWired style={{ color: 'var(--accent-primary)' }} />
            Red de Correlaciones Net Holmes
          </h2>
          <p className="text-secondary" style={{ marginTop: '5px' }}>
            Análisis y graficación de redes de infractores organizados en 5 dimensiones.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            onClick={handleAutoCorrelate}
            disabled={correlating}
            className="btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <FaBolt />
            {correlating ? 'Evaluando 5D...' : 'Ejecutar Correlación 5D'}
          </button>
          <button 
            onClick={fetchClusters}
            className="btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <FaSearch />
            Actualizar Redes
          </button>
        </div>
      </div>

      {statusMessage && (
        <div className={`message-banner ${statusMessage.type === 'success' ? 'success-message' : 'error-message'} slide-up`} style={{ marginBottom: '1.5rem' }}>
          {statusMessage.type === 'success' ? <FaShieldAlt /> : <FaExclamationTriangle />} {statusMessage.text}
        </div>
      )}

      {loading ? (
        <div className="spinner-container" style={{ padding: '3rem 0' }}>
          <div className="spinner spinner--dark"></div>
          <span className="spinner-text">Analizando el grafo de relaciones...</span>
        </div>
      ) : clusters.length === 0 ? (
        <div className="glass-card empty-state" style={{ padding: '3rem' }}>
          <FaNetworkWired className="empty-icon" style={{ fontSize: '3rem', color: 'var(--text-secondary)' }} />
          <h3>Sin Detecciones</h3>
          <p style={{ color: 'var(--text-secondary)' }}>No se detectaron redes criminales organizadas aún. Pulsa "Ejecutar Correlación 5D" para forzar el análisis.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '20px' }}>
          {clusters.map(cluster => (
            <div key={cluster.id} className="glass-card" style={{ padding: '0', display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: 'rgba(0,0,0,0.2)' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.15rem', color: 'var(--accent-primary)' }}>{cluster.nombre}</h3>
                  <p style={{ margin: '5px 0 0 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {cluster.total_cuentas} cuentas sospechosas vinculadas
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '5px', background: 'rgba(231, 76, 60, 0.12)', color: 'var(--danger)', padding: '5px 10px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid rgba(231, 76, 60, 0.3)' }}>
                  <FaExclamationTriangle />
                  Riesgo Alto
                </div>
              </div>
              <div style={{ padding: '20px', flexGrow: 1 }}>
                <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px', textAlign: 'center', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <div style={{ fontSize: '1.6rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>{((cluster.score_promedio || 0.85) * 100).toFixed(0)}%</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Certeza Vínculo</div>
                  </div>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px', textAlign: 'center', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', fontSize: '1.2rem', marginBottom: '4px' }}>
                      <span style={{ color: '#E74C3C' }} title="Identificadores"><FaUserCircle /></span>
                      <span style={{ color: '#3498DB' }} title="Contenido"><FaLink /></span>
                      <span style={{ color: '#2ECC71' }} title="Temporal"><FaClock /></span>
                      <span style={{ color: '#F39C12' }} title="Lingüístico"><FaFileAlt /></span>
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginTop: '2px', fontWeight: 600 }}>Vectores 5D</div>
                  </div>
                </div>
                
                <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: '1.45' }}>
                  {cluster.descripcion || "Múltiples cuentas compartiendo identificadores exactos (CBU, teléfono, DNI), similitud visual de productos y patrones temporales sincronizados."}
                </p>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '15px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Cluster ID: #{cluster.id}
                  </span>
                  <button 
                    onClick={() => handleInspectCluster(cluster)}
                    className="btn-primary" 
                    style={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px' }}
                  >
                    Inspeccionar Red <FaNetworkWired />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal Inspector de Red de Correlaciones Interactivo */}
      {selectedCluster && (
        <div className="modal-overlay fade-in" style={{ position: 'fixed', inset: 0, background: 'rgba(7, 26, 46, 0.85)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10000, padding: '20px' }}>
          <div className="glass-card slide-up" style={{ width: '100%', maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto', background: 'var(--bg-secondary)', border: '1px solid rgba(16, 197, 201, 0.3)', padding: '24px' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '12px' }}>
              <div>
                <h3 style={{ margin: 0, color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <FaNetworkWired /> {selectedCluster.nombre}
                </h3>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  Inspección espacial de conexiones criminales multiplataforma
                </span>
              </div>
              <button 
                onClick={() => setSelectedCluster(null)}
                className="btn-close"
                style={{ background: 'none', border: 'none', color: '#fff', fontSize: '1.4rem', cursor: 'pointer' }}
              >
                <FaTimes />
              </button>
            </div>

            {modalLoading ? (
              <div className="spinner-container" style={{ padding: '2rem' }}>
                <div className="spinner spinner--dark"></div>
              </div>
            ) : (
              <>
                {/* Visualizador de Grafo SVG Interactivo */}
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ color: 'var(--text-primary)', marginBottom: '10px' }}>Mapa de Relaciones Espaciales</h4>
                  {renderClusterGraph(selectedCluster)}
                </div>

                {/* Detalle del Nodo Seleccionado */}
                {selectedNode && (
                  <div style={{ background: 'rgba(16, 197, 201, 0.1)', border: '1px solid var(--accent-primary)', borderRadius: '8px', padding: '15px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                    <div>
                      <strong style={{ color: 'var(--accent-primary)', display: 'block' }}>Reporte Seleccionado: #{selectedNode}</strong>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        Haz clic en el botón para abrir el expediente completo en el módulo de investigación.
                      </span>
                    </div>
                    <button 
                      onClick={() => navigate(`/suspects/${selectedNode}`)}
                      className="btn-primary"
                      style={{ fontSize: '0.85rem', padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      Abrir Expediente <FaExternalLinkAlt />
                    </button>
                  </div>
                )}

                {/* Desglose de Vínculos y Dimensiones */}
                <div style={{ marginTop: '20px' }}>
                  {(() => {
                    const validLinks = (selectedCluster.links || []).filter(l => (l.score || 0) >= 0.65);
                    return (
                      <>
                        <h4 style={{ color: 'var(--text-primary)', marginBottom: '12px' }}>
                          Vínculos Validados ({validLinks.length})
                        </h4>
                        {validLinks.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '200px', overflowY: 'auto' }}>
                            {validLinks.map(link => {
                              const meta = getDimensionMeta(link.tipo_correlacion);
                              const scoreVal = link.score || 0;
                              return (
                                <div 
                                  key={link.id} 
                                  style={{ background: 'rgba(255,255,255,0.04)', borderLeft: `4px solid ${meta.color}`, borderRadius: '6px', padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                                >
                                  <div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: meta.color, fontWeight: 'bold', fontSize: '0.85rem', textTransform: 'uppercase' }}>
                                      {meta.icon} {meta.label} <span style={{ color: 'var(--text-secondary)', fontWeight: 'normal', fontSize: '0.8rem' }}>({link.subtipo})</span>
                                    </div>
                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '3px' }}>
                                      Conexión: <strong>Reporte #{link.reporte_a_id}</strong> con <strong>Reporte #{link.reporte_b_id}</strong>
                                    </div>
                                  </div>
                                  <span className="badge" style={{ 
                                    background: scoreVal >= 0.85 ? 'rgba(231, 76, 60, 0.25)' : scoreVal >= 0.75 ? 'rgba(16, 197, 201, 0.25)' : 'rgba(243, 156, 18, 0.25)', 
                                    color: scoreVal >= 0.85 ? '#FF6B6B' : scoreVal >= 0.75 ? '#10C5C9' : '#F39C12', 
                                    border: `1px solid ${scoreVal >= 0.85 ? '#E74C3C' : scoreVal >= 0.75 ? '#10C5C9' : '#F39C12'}`,
                                    fontWeight: 'bold', 
                                    fontSize: '0.75rem',
                                    padding: '4px 8px',
                                    borderRadius: '6px'
                                  }}>
                                    {scoreVal >= 0.85 ? 'Alta Certeza' : 'Certeza Media'}: {(scoreVal * 100).toFixed(0)}%
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                            No hay vínculos con score mayor al umbral de confianza (65%).
                          </p>
                        )}
                      </>
                    );
                  })()}
                </div>

                <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-end' }}>
                  <button 
                    onClick={() => setSelectedCluster(null)}
                    className="btn-ghost"
                  >
                    Cerrar Inspector
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default RedCorrelacionesPage;
