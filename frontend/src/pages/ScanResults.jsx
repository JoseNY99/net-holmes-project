import React, { useState, useEffect } from 'react';
import { getScanResults } from '../services/scanService';
import { FaRobot, FaUserCog, FaSearch, FaExternalLinkAlt } from 'react-icons/fa';
import './ScanResults.css';

export default function ScanResults() {
  const [activeTab, setActiveTab] = useState('automatico');
  const [results, setResults] = useState([]);
  const [allResults, setAllResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  
  const [platformFilter, setPlatformFilter] = useState('todas');
  const [dateFilter, setDateFilter] = useState('');

  const [total, setTotal] = useState(0);

  useEffect(() => {
    fetchResults();
  }, [activeTab, platformFilter, dateFilter, page, pageSize]);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const skip = (page - 1) * pageSize;
      const res = await getScanResults({
        tipo: activeTab,
        plataforma: platformFilter !== 'todas' ? platformFilter : undefined,
        fecha_desde: dateFilter ? `${dateFilter}T00:00:00Z` : undefined,
        fecha_hasta: dateFilter ? `${dateFilter}T23:59:59Z` : undefined,
        skip,
        limit: pageSize
      });
      setResults(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (error) {
      console.error("Error al obtener resultados:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container fade-in">
      <div className="glass-card results-container">
        <div className="results-header" style={{ flexWrap: 'wrap', gap: '1rem' }}>
          <h2>Resultados de Escaneo</h2>
          <div className="results-tabs">
            <button 
              className={`tab-btn ${activeTab === 'automatico' ? 'active' : ''}`}
              onClick={() => setActiveTab('automatico')}
            >
              <FaRobot /> Motor Cron
            </button>
            <button 
              className={`tab-btn ${activeTab === 'manual' ? 'active' : ''}`}
              onClick={() => setActiveTab('manual')}
            >
              <FaUserCog /> Manual
            </button>
          </div>
        </div>

        <div className="filters-bar" style={{ display: 'flex', gap: '1rem', padding: '1rem 0', borderBottom: '1px solid var(--border-color)', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Plataforma:</label>
            <select 
              className="input-field" 
              style={{ width: '150px', padding: '6px' }}
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value)}
            >
              <option value="todas">Todas</option>
              <option value="facebook">Facebook</option>
              <option value="instagram">Instagram</option>
              <option value="tiktok">TikTok</option>
              <option value="mercadolibre">MercadoLibre</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Fecha:</label>
            <input 
              type="date" 
              className="input-field" 
              style={{ width: '150px', padding: '6px' }}
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
            />
          </div>
          {(platformFilter !== 'todas' || dateFilter) && (
            <button className="btn-ghost" onClick={() => { setPlatformFilter('todas'); setDateFilter(''); }} style={{ padding: '6px 12px' }}>
              Limpiar Filtros
            </button>
          )}
        </div>

        <div className="results-content">
          {loading ? (
            <div className="spinner-container"><div className="spinner spinner--dark"></div></div>
          ) : results.length === 0 ? (
            <div className="empty-state">
              <FaSearch className="empty-icon" />
              <h3>No hay resultados</h3>
              <p>No se encontraron capturas {activeTab === 'automatico' ? 'del motor automático' : 'de búsquedas manuales'}.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Plataforma</th>
                    <th>Vendedor</th>
                    <th>URL</th>
                    <th>Estado</th>
                    <th>Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((item, i) => (
                    <tr key={item.id} className="stagger-item" style={{ animationDelay: `${i * 0.05}s` }}>
                      <td><span className="platform-badge">{item.plataforma}</span></td>
                      <td>{item.titular_cuenta || 'Desconocido'}</td>
                      <td>
                        <a href={item.url_evidencia} target="_blank" rel="noopener noreferrer" className="link-icon">
                          Ver link <FaExternalLinkAlt />
                        </a>
                      </td>
                      <td>
                        <span className={`status-badge status-${(item.estado || 'Pendiente').toLowerCase()}`}>{item.estado || 'Pendiente'}</span>
                      </td>
                      <td>{new Date(item.fecha_captura || item.created_at).toLocaleString('es-AR')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pagination" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', padding: '10px' }}>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                  Mostrando {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, total)} de {total} resultados
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button 
                    className="btn-ghost" 
                    disabled={page === 1} 
                    onClick={() => setPage(page - 1)}
                  >Anterior</button>
                  <span>Página {page} de {Math.ceil(total / pageSize) || 1}</span>
                  <button 
                    className="btn-ghost" 
                    disabled={page >= Math.ceil(total / pageSize)} 
                    onClick={() => setPage(page + 1)}
                  >Siguiente</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
