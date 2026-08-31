import React, { useState, useEffect } from 'react';
import { getGeneralReport, getReportList, exportReport } from '../services/reportService';
import { getBrands } from '../services/brandService';
import { FaChartPie, FaDownload, FaRobot, FaUserCog, FaFilter, FaChevronLeft, FaChevronRight, FaLock } from 'react-icons/fa';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import './Reports.css';

const COLORS = ['#2D8A56', '#D4930D', '#C0392B', '#6B6B6B']; // Confirmado, Pendiente, Investigando, Descartado

export default function Reports() {
  const [activeTab, setActiveTab] = useState('automatico');
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Lista paginada y filtros
  const [listData, setListData] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [plataformaFilter, setPlataformaFilter] = useState('');
  const [estadoFilter, setEstadoFilter] = useState('');
  const [marcaFilter, setMarcaFilter] = useState('');
  const [marcas, setMarcas] = useState([]);

  useEffect(() => {
    fetchGeneralStats();
    fetchBrands();
  }, [activeTab]);

  useEffect(() => {
    fetchList();
  }, [page, pageSize, activeTab, plataformaFilter, estadoFilter, marcaFilter]);

  const fetchGeneralStats = async () => {
    try {
      const res = await getGeneralReport();
      setReportData(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchBrands = async () => {
    try {
      const res = await getBrands();
      setMarcas(res.data);
    } catch (e) {
      console.error(e);
    }
  }

  const fetchList = async () => {
    setLoading(true);
    try {
      const params = {
        tipo: activeTab,
        page,
        limit: pageSize
      };
      if (plataformaFilter) params.plataforma = plataformaFilter;
      if (estadoFilter) params.estado = estadoFilter;
      if (marcaFilter) params.brand_id = marcaFilter;

      const res = await getReportList(params);
      setListData(res.data?.items || []);
      setTotalPages(Math.ceil((res.data?.total || 0) / pageSize) || 1);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  const currentStats = activeTab === 'automatico' ? reportData?.stats_automatico : reportData?.stats_manual;

  const pieData = [
    { name: 'Confirmados', value: currentStats?.confirmados || 0 },
    { name: 'Pendientes', value: currentStats?.pendientes || 0 },
    { name: 'Investigando', value: currentStats?.investigando || 0 },
    { name: 'Descartados', value: currentStats?.descartados || 0 },
  ].filter(d => d.value > 0);

  const handleExport = async (format) => {
    try {
      const params = { tipo: activeTab };
      if (plataformaFilter) params.plataforma = plataformaFilter;
      if (estadoFilter) params.estado = estadoFilter;
      if (marcaFilter) params.brand_id = marcaFilter;

      const response = await exportReport(format, params);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `reporte_${activeTab}.${format === 'word' ? 'docx' : format}`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (e) {
      console.error("Export error", e);
      alert("Error al exportar");
    }
  };

  const handleSingleExport = async (itemId, format) => {
    try {
      const { exportSingleReport } = await import('../services/reportService');
      const res = await exportSingleReport(itemId, format);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      const ext = format === 'word' ? 'docx' : 'pdf';
      link.setAttribute('download', `reporte_${format}_${itemId}.${ext}`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Single export error", e);
      let errMsg = "Error al exportar el caso";
      if (e.response && e.response.data) {
        try {
          if (e.response.data instanceof Blob) {
            const text = await e.response.data.text();
            const parsed = JSON.parse(text);
            errMsg = parsed.detail || errMsg;
          } else if (e.response.data.detail) {
            errMsg = e.response.data.detail;
          }
        } catch(err) {}
      }
      alert(errMsg);
    }
  };

  return (
    <div className="page-container fade-in">
      <div className="glass-card reports-container">
        <div className="reports-header">
          <h2>Centro de Reportes Inteligentes</h2>
          
          <div className="reports-actions">
            <div className="reports-tabs">
              <button 
                className={`tab-btn ${activeTab === 'automatico' ? 'active' : ''}`}
                onClick={() => { setActiveTab('automatico'); setPage(1); }}
              >
                <FaRobot /> Automático
              </button>
              <button 
                className={`tab-btn ${activeTab === 'manual' ? 'active' : ''}`}
                onClick={() => { setActiveTab('manual'); setPage(1); }}
              >
                <FaUserCog /> Manual
              </button>
            </div>
            
            <div className="export-dropdown">
              <button className="btn-secondary"><FaDownload /> Exportar</button>
              <div className="export-menu">
                <button onClick={() => handleExport('pdf')}>PDF Document</button>
                <button onClick={() => handleExport('word')}>Word Document</button>
              </div>
            </div>
          </div>
        </div>

        <div className="reports-content">
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Total Escaneos</h3>
              <p className="stat-number">{currentStats?.total || 0}</p>
            </div>
            <div className="stat-card">
              <h3>Bajo Investigación</h3>
              <p className="stat-number alert">{currentStats?.investigando || 0}</p>
            </div>
            <div className="stat-card">
              <h3>Infracciones Confirmadas</h3>
              <p className="stat-number danger">{currentStats?.confirmados || 0}</p>
            </div>
          </div>

          <div className="list-section mt-4">
            <h3>Detalle de Escaneos</h3>
            <div className="filters-bar">
              <select className="input-field filter-input" value={plataformaFilter} onChange={e => { setPlataformaFilter(e.target.value); setPage(1); }}>
                <option value="">Todas las Plataformas</option>
                <option value="facebook">Facebook</option>
                <option value="instagram">Instagram</option>
                <option value="tiktok">TikTok</option>
              </select>
              <select className="input-field filter-input" value={estadoFilter} onChange={e => { setEstadoFilter(e.target.value); setPage(1); }}>
                <option value="">Todos los Estados</option>
                <option value="pendiente">Pendiente</option>
                <option value="investigando">Investigando</option>
                <option value="confirmado">Confirmado</option>
                <option value="descartado">Descartado</option>
              </select>
              <select className="input-field filter-input" value={marcaFilter} onChange={e => { setMarcaFilter(e.target.value); setPage(1); }}>
                <option value="">Todas las Marcas</option>
                {marcas.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
              </select>
            </div>

            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Plataforma</th>
                    <th>Marca</th>
                    <th>Usuario / Vendedor</th>
                    <th>Enlace (URL)</th>
                    <th>Correlaciones</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="8" style={{textAlign: 'center'}}><div className="spinner spinner--dark" style={{margin:'20px auto'}}></div></td></tr>
                  ) : listData.length === 0 ? (
                    <tr><td colSpan="8" style={{textAlign: 'center', padding: '20px'}}>No hay datos para estos filtros.</td></tr>
                  ) : (
                    listData.map(item => {
                      let correlations = "";
                      try {
                        if (item.correlaciones_nlp && item.correlaciones_nlp !== "{}") {
                          const parsed = JSON.parse(item.correlaciones_nlp);
                          correlations = Object.keys(parsed).map(k => `${k}: ${parsed[k].join(', ')}`).join(' | ');
                        }
                      } catch(e) {}
                      
                      let imageUrl = null;
                      try {
                        const urls = item.imagen_urls ? JSON.parse(item.imagen_urls.replace(/'/g, '"')) : [];
                        if (urls.length > 0) imageUrl = urls[0];
                      } catch(e){}

                      return (
                      <tr key={item.id}>
                        <td>{item.fecha_captura ? new Date(item.fecha_captura).toLocaleDateString('es-AR') : 'N/D'}</td>
                        <td><span className="platform-badge">{item.plataforma}</span></td>
                        <td>{item.marca_afectada}</td>
                        <td>
                          <div style={{display:'flex', alignItems:'center', gap:'10px'}}>
                            {imageUrl && <img src={imageUrl} alt="Profile" style={{width:'32px', height:'32px', borderRadius:'50%', objectFit:'cover', border:'1px solid #ddd'}} />}
                            <strong>{item.titular_cuenta || 'N/A'}</strong>
                          </div>
                        </td>
                        <td>
                          <a href={item.url_evidencia} target="_blank" rel="noreferrer" style={{color: 'var(--accent-primary)', textDecoration: 'underline'}}>Ver Publicación</a>
                        </td>
                        <td style={{fontSize: '0.85rem', maxWidth: '250px', whiteSpace: 'normal'}}>
                          {correlations ? <i>{correlations}</i> : <span style={{color: '#999'}}>No detectadas</span>}
                        </td>
                        <td><span className={`status-badge status-${item.estado}`}>{item.estado}</span></td>
                        <td>
                          <div style={{display:'flex', gap:'5px', alignItems:'center'}}>
                            {item.estado === 'pendiente' ? (
                              <>
                                <button 
                                  className="btn-primary" 
                                  style={{padding: '4px 8px', fontSize:'0.75rem', backgroundColor: 'var(--warning)', borderColor: 'var(--warning)', color: '#fff'}}
                                  onClick={() => {
                                    import('../services/suspectService').then(m => {
                                      m.promoteScan(item.id).then(() => {
                                        alert("Relevado a investigaciones exitosamente.");
                                        fetchList();
                                      }).catch(e => {
                                        console.error(e);
                                        alert("Error al relevar");
                                      });
                                    });
                                  }}
                                >
                                  Relevar
                                </button>
                                <div 
                                  title="El reporte requiere ser relevado y completado en la fase de investigación antes de poder exportarse o imprimirse"
                                  style={{ padding: '4px 8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)', cursor: 'not-allowed', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem' }}
                                >
                                  <FaLock /> Bloqueado
                                </div>
                              </>
                            ) : (
                              <div className="export-dropdown" style={{marginLeft: 0}}>
                                <button className="btn-secondary" style={{padding: '4px 8px', fontSize:'0.8rem'}}><FaDownload /> <span style={{fontSize:'0.6rem'}}>▼</span></button>
                                <div className="export-menu" style={{right: 0, minWidth: '150px'}}>
                                  <button onClick={() => handleSingleExport(item.id, 'pdf')}>PDF Estándar</button>
                                  <button onClick={() => handleSingleExport(item.id, 'cbn-pdf')} style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>⭐ PDF Oficial CBN</button>
                                  <button onClick={() => handleSingleExport(item.id, 'word')}>Word (.docx)</button>
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )})
                  )}
                </tbody>
              </table>
            </div>
            
            <div className="pagination" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Mostrar:</span>
                <select 
                  className="input-field" 
                  style={{ width: '80px', padding: '6px' }}
                  value={pageSize} 
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                >
                  <option value={20}>20</option>
                  <option value={30}>30</option>
                  <option value={50}>50</option>
                </select>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button 
                  className="btn-ghost" 
                  disabled={page === 1} 
                  onClick={() => setPage(page - 1)}
                ><FaChevronLeft /> Anterior</button>
                <span>Página {page} de {totalPages || 1}</span>
                <button 
                  className="btn-ghost" 
                  disabled={page === totalPages || totalPages === 0} 
                  onClick={() => setPage(page + 1)}
                >Siguiente <FaChevronRight /></button>
              </div>
            </div>

          </div>

        </div>
      </div>
    </div>
  );
}
