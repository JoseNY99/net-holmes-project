import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getSuspects as getReportes } from '../services/suspectService';
import { FaBoxOpen, FaSearch, FaCheck, FaTimes, FaUserSecret } from 'react-icons/fa';
import './Investigation.css'; // Mantenemos el css base para estilos

export default function Investigation() {
  const [reportes, setReportes] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  
  const [filterEstado, setFilterEstado] = useState('Pendiente');
  const [filterPlataforma, setFilterPlataforma] = useState('');
  
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  useEffect(() => {
    setPage(1);
  }, [filterEstado, filterPlataforma, limit]);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      fetchReportes();
    }, 300);
    return () => clearTimeout(delayDebounceFn);
  }, [filterEstado, filterPlataforma, page, limit]);

  const fetchReportes = async () => {
    setLoading(true);
    try {
      const skip = (page - 1) * limit;
      const res = await getReportes({
        estado: filterEstado,
        plataforma: filterPlataforma,
        skip,
        limit
      });
      setReportes(res.data.items);
      setTotal(res.data.total);
    } catch (error) {
      console.error("Error fetching reportes:", error);
    } finally {
      setLoading(false);
    }
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="page-container fade-in">
      <div className="investigation-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', width: '100%' }}>
          <div>
            <h2>Triage Net Holmes</h2>
            <p>Dashboard de triage para clasificar los reportes e infracciones detectadas (Fase 1 de la investigación).</p>
          </div>
        </div>
        <div className="investigation-filters" style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '1rem' }}>
          <div style={{ position: 'relative' }}>
            <FaSearch className="filter-icon" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
            <input 
              type="text" 
              className="input-field" 
              placeholder="Plataforma..."
              value={filterPlataforma}
              onChange={(e) => setFilterPlataforma(e.target.value)}
              style={{ paddingLeft: '35px' }}
            />
          </div>
          <select 
            className="input-field filter-select" 
            value={filterEstado} 
            onChange={(e) => setFilterEstado(e.target.value)}
          >
            <option value="todos">Todos los Estados</option>
            <option value="Pendiente">Pendiente (Nuevos)</option>
            <option value="Investigando">Investigando (En Progreso)</option>
            <option value="Sospechoso">Sospechoso (ABM)</option>
            <option value="Descartado">Descartado</option>
          </select>
          <select
            className="input-field filter-select"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            <option value={10}>10 por pág</option>
            <option value={20}>20 por pág</option>
            <option value={50}>50 por pág</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="spinner-container">
          <div className="spinner spinner--dark"></div>
          <span className="spinner-text">Cargando reportes de scrapers...</span>
        </div>
      ) : reportes.length === 0 ? (
        <div className="glass-card empty-state">
          <FaBoxOpen className="empty-icon" />
          <h3>Sin Reportes</h3>
          <p>No hay reportes en Triage actualmente.</p>
        </div>
      ) : (
        <div className="glass-card" style={{ padding: '0', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.05)' }}>
                <th style={{ padding: '15px' }}>Referencia</th>
                <th style={{ padding: '15px' }}>Marca</th>
                <th style={{ padding: '15px' }}>Plataforma</th>
                <th style={{ padding: '15px' }}>Titular</th>
                <th style={{ padding: '15px' }}>Seguidores</th>
                <th style={{ padding: '15px' }}>Precio</th>
                <th style={{ padding: '15px' }}>Estado</th>
                <th style={{ padding: '15px' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {reportes.map((report, index) => (
                <tr key={report.id} className="table-row-hover stagger-item" style={{ animationDelay: `${index * 0.05}s` }}>
                  <td style={{ padding: '15px' }}>{report.referencia_interna}</td>
                  <td style={{ padding: '15px', color: 'var(--accent-primary)', fontWeight: 'bold' }}>{report.marca_afectada}</td>
                  <td style={{ padding: '15px' }}>
                    <span className="platform-badge">{report.plataforma}</span>
                  </td>
                  <td style={{ padding: '15px' }}>{report.titular_cuenta}</td>
                  <td style={{ padding: '15px' }}>
                    {report.seguidores_infractor !== null && report.seguidores_infractor !== undefined ? report.seguidores_infractor.toLocaleString() : '-'}
                  </td>
                  <td style={{ padding: '15px' }}>{report.precio_publico ? `$${report.precio_publico}` : 'N/A'}</td>
                  <td style={{ padding: '15px' }}>
                    <span className={`status-badge`} style={{ background: report.estado === 'Sospechoso' ? 'var(--danger)' : report.estado === 'Investigando' ? '#3498db' : report.estado === 'Descartado' ? '#555' : 'var(--warning)' }}>
                      {report.estado}
                    </span>
                  </td>
                  <td style={{ padding: '15px' }}>
                    <Link to={`/suspects/${report.id}`} className="btn-secondary" style={{ padding: '5px 10px', fontSize: '0.8rem' }}>
                      <FaUserSecret /> Abrir
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Controls */}
      {!loading && total > 0 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', marginTop: '2rem', gap: '15px' }}>
          <button 
            className="btn-secondary" 
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Anterior
          </button>
          <span>Página {page} de {totalPages || 1} ({total} registros)</span>
          <button 
            className="btn-secondary" 
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages || totalPages === 0}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
