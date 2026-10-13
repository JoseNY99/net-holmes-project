import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getSuspects as getReportes } from '../services/suspectService';
import { getBrands } from '../services/brandService';
import { exportReport } from '../services/reportService';
import { 
  FaBoxOpen, FaSearch, FaUserSecret, FaFilter, FaDownload, 
  FaFilePdf, FaFileWord, FaFileExcel, FaLayerGroup, FaCheckCircle, 
  FaTimesCircle, FaExclamationTriangle, FaExternalLinkAlt 
} from 'react-icons/fa';
import './Investigation.css';

export default function Investigation() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'fase2';

  const [activeTab, setActiveTab] = useState(initialTab);
  const [reportes, setReportes] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  
  const [filterEstado, setFilterEstado] = useState('');
  const [filterPlataforma, setFilterPlataforma] = useState('');
  const [filterMarca, setFilterMarca] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [marcas, setMarcas] = useState([]);
  
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [exporting, setExporting] = useState(false);
  const [sortBy, setSortBy] = useState('marca');
  const [sortDirection, setSortDirection] = useState('asc');

  // Cargar marcas para el filtro
  useEffect(() => {
    const fetchBrandsList = async () => {
      try {
        const res = await getBrands();
        setMarcas(res.data || []);
      } catch (e) {}
    };
    fetchBrandsList();
  }, []);

  // Ajustar estado según la pestaña activa
  useEffect(() => {
    setPage(1);
    if (activeTab === 'fase2') {
      setFilterEstado('Investigando,Sospechoso');
    } else if (activeTab === 'fase3') {
      setFilterEstado('Confirmado');
    } else if (activeTab === 'descartados') {
      setFilterEstado('Descartado');
    } else if (activeTab === 'todos') {
      setFilterEstado('');
    }
  }, [activeTab]);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      fetchReportes();
    }, 250);
    return () => clearTimeout(delayDebounceFn);
  }, [filterEstado, filterPlataforma, filterMarca, page, limit, activeTab]);

  const fetchReportes = async () => {
    setLoading(true);
    try {
      const skip = (page - 1) * limit;
      let effectiveEstado = filterEstado;

      const res = await getReportes({
        estado: effectiveEstado || undefined,
        plataforma: filterPlataforma || undefined,
        brand_id: filterMarca || undefined,
        skip,
        limit
      });
      setReportes(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (error) {
      console.error("Error fetching reportes:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format) => {
    setExporting(true);
    try {
      const params = {
        tipo: 'automatico',
        plataforma: filterPlataforma || undefined,
        estado: filterEstado || undefined,
        brand_id: filterMarca || undefined
      };
      const response = await exportReport(format, params);
      const ext = format === 'word' ? 'docx' : format;
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `reporte_investigaciones_${activeTab}.${ext}`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (e) {
      alert("Error al exportar el reporte.");
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / limit);

  // Filtrado local por término de búsqueda si el usuario escribe
  const displayItems = searchQuery.trim()
    ? reportes.filter(r => 
        (r.titular_cuenta || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.marca_afectada || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.referencia_interna || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.descripcion_post || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : reportes;

  const sortedItems = [...displayItems].sort((left, right) => {
    const fields = {
      marca: left.marca_afectada,
      vendedor: left.titular_cuenta,
      ubicacion: left.direccion_publica || left.pais,
      estado: left.estado
    };
    const leftValue = String(fields[sortBy] || '').trim();
    const rightValue = String(({
      marca: right.marca_afectada,
      vendedor: right.titular_cuenta,
      ubicacion: right.direccion_publica || right.pais,
      estado: right.estado
    })[sortBy] || '').trim();
    const comparison = leftValue.localeCompare(rightValue, 'es', { sensitivity: 'base', numeric: true });
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const setSort = (field) => {
    if (sortBy === field) {
      setSortDirection((direction) => direction === 'asc' ? 'desc' : 'asc');
      return;
    }
    setSortBy(field);
    setSortDirection('asc');
  };

  return (
    <div className="page-container fade-in" style={{ maxWidth: '1600px', margin: '0 auto' }}>
      {/* Header Unificado */}
      <div className="investigation-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', width: '100%' }}>
          <div>
            <h2><FaLayerGroup style={{ marginRight: '10px', color: 'var(--accent-primary)' }} /> Centro de Investigaciones & Hallazgos</h2>
            <p>Monitoreo unificado del ciclo de vida de infracciones: Investigaciones Activas (Fase 2), Perfilado ABM y Reportes Finales (Fase 3).</p>
          </div>

          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button 
              className="btn-secondary btn-sm" 
              onClick={() => handleExport('pdf')} 
              disabled={exporting || reportes.length === 0}
              title="Descargar reporte en PDF"
            >
              <FaFilePdf color="#EF4444" /> Exportar PDF
            </button>
            <button 
              className="btn-secondary btn-sm" 
              onClick={() => handleExport('excel')} 
              disabled={exporting || reportes.length === 0}
              title="Descargar datos en Excel"
            >
              <FaFileExcel color="#10B981" /> Excel
            </button>
          </div>
        </div>

        {/* Tabs de Fases */}
        <div className="investigation-tabs" style={{ display: 'flex', gap: '8px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px', marginTop: '1.5rem', overflowX: 'auto' }}>
          <button 
            type="button"
            className={`tab-btn ${activeTab === 'fase2' ? 'tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('fase2'); setSearchParams({ tab: 'fase2' }); }}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'fase2' ? 'var(--accent-primary)' : 'rgba(255,255,255,0.05)', color: activeTab === 'fase2' ? '#000' : 'var(--text-secondary)' }}
          >
            Fase 2: Investigaciones Activas
          </button>
          <button 
            type="button"
            className={`tab-btn ${activeTab === 'fase3' ? 'tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('fase3'); setSearchParams({ tab: 'fase3' }); }}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'fase3' ? 'var(--accent-primary)' : 'rgba(255,255,255,0.05)', color: activeTab === 'fase3' ? '#000' : 'var(--text-secondary)' }}
          >
            Fase 3: Casos Confirmados & Reportes
          </button>
          <button 
            type="button"
            className={`tab-btn ${activeTab === 'todos' ? 'tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('todos'); setSearchParams({ tab: 'todos' }); }}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'todos' ? 'var(--accent-primary)' : 'rgba(255,255,255,0.05)', color: activeTab === 'todos' ? '#000' : 'var(--text-secondary)' }}
          >
            Vista Global (Todos)
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'descartados' ? 'tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('descartados'); setSearchParams({ tab: 'descartados' }); }}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'descartados' ? 'var(--accent-primary)' : 'rgba(255,255,255,0.05)', color: activeTab === 'descartados' ? '#000' : 'var(--text-secondary)' }}
          >
            Descartados
          </button>
        </div>

        {/* Barra de Filtros */}
        <div className="investigation-filters" style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '1rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: '1 1 200px', minWidth: '180px' }}>
            <FaSearch className="filter-icon" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
            <input 
              type="text" 
              className="input-field" 
              placeholder="Buscar vendedor, marca o post..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '35px', width: '100%' }}
            />
          </div>

          <select 
            className="input-field filter-select" 
            value={filterPlataforma} 
            onChange={(e) => setFilterPlataforma(e.target.value)}
            style={{ flex: '0 1 160px' }}
          >
            <option value="">Todas las Plataformas</option>
            <option value="facebook">Facebook Marketplace</option>
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
            <option value="mercadolibre">Mercado Libre</option>
          </select>

          <select 
            className="input-field filter-select" 
            value={filterMarca} 
            onChange={(e) => setFilterMarca(e.target.value)}
            style={{ flex: '0 1 160px' }}
          >
            <option value="">Todas las Marcas</option>
            {marcas.map(m => (
              <option key={m.id} value={m.id}>{m.nombre}</option>
            ))}
          </select>

          {activeTab === 'todos' && (
            <select 
              className="input-field filter-select" 
              value={filterEstado} 
              onChange={(e) => setFilterEstado(e.target.value)}
              style={{ flex: '0 1 160px' }}
            >
              <option value="">Todos los Estados</option>
              <option value="Sospechoso">Sospechoso (Fase 2)</option>
              <option value="Investigando">Investigando (En Proceso)</option>
              <option value="Confirmado">Confirmado (Fase 3)</option>
              <option value="Descartado">Descartado</option>
            </select>
          )}

          <select
            className="input-field filter-select"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            style={{ flex: '0 1 110px' }}
          >
            <option value={10}>10 / pág</option>
            <option value={20}>20 / pág</option>
            <option value={50}>50 / pág</option>
            <option value={100}>100 / pág</option>
          </select>
        </div>
      </div>

      {/* Listado de Resultados */}
      {loading ? (
        <div className="spinner-container">
          <div className="spinner spinner--dark"></div>
          <span className="spinner-text">Cargando registros de la investigación...</span>
        </div>
      ) : displayItems.length === 0 ? (
        <div className="glass-card empty-state" style={{ textAlign: 'center', padding: '50px 20px' }}>
          <FaBoxOpen className="empty-icon" style={{ fontSize: '3rem', opacity: 0.3, marginBottom: '16px' }} />
          <h3>Sin Registros en esta Fase</h3>
          <p style={{ color: 'var(--text-secondary)' }}>No se encontraron reportes con los filtros aplicados en {activeTab.toUpperCase()}.</p>
        </div>
      ) : (
        <div className="glass-card" style={{ padding: '0', overflowX: 'auto', borderRadius: '12px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.03)' }}>
                <th style={{ padding: '14px 16px' }}>Ref</th>
                <th style={{ padding: '14px 16px' }}><button className="investigation-sort-button" type="button" onClick={() => setSort('marca')} aria-label="Ordenar por marca">Marca{sortBy === 'marca' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>
                <th style={{ padding: '14px 16px' }}>Plataforma</th>
                <th style={{ padding: '14px 16px' }}><button className="investigation-sort-button" type="button" onClick={() => setSort('vendedor')} aria-label="Ordenar alfabéticamente por infractor">Vendedor / Infractor{sortBy === 'vendedor' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>
                <th style={{ padding: '14px 16px' }}><button className="investigation-sort-button" type="button" onClick={() => setSort('ubicacion')} aria-label="Ordenar por ubicación">Contacto / Ubicación{sortBy === 'ubicacion' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>
                <th style={{ padding: '14px 16px' }}>Precio Cotizado</th>
                <th style={{ padding: '14px 16px' }}>Relevamiento</th>
                <th style={{ padding: '14px 16px' }}><button className="investigation-sort-button" type="button" onClick={() => setSort('estado')} aria-label="Ordenar por estado">Estado{sortBy === 'estado' ? (sortDirection === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>
                <th style={{ padding: '14px 16px', textAlign: 'right' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((report, index) => {
                const currency = report.moneda || 'ARS';
                const formattedPrice = report.precio_publico !== null && report.precio_publico !== undefined
                  ? `${currency} $${Number(report.precio_publico).toLocaleString()}`
                  : 'N/A';

                return (
                  <tr key={report.id} className="table-row-hover stagger-item" style={{ animationDelay: `${index * 0.03}s`, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '14px 16px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      #{report.id}
                    </td>
                    <td className="investigation-cell-brand">
                      <span>{report.marca_afectada}</span>
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <span className="platform-badge" style={{ textTransform: 'capitalize' }}>{report.plataforma}</span>
                    </td>
                    <td className="investigation-cell-seller">
                      <div className="investigation-seller-name">{report.titular_cuenta}</div>
                      {report.seguidores_infractor !== null && report.seguidores_infractor !== undefined && (
                        <small className="investigation-cell-secondary">
                          {Number(report.seguidores_infractor).toLocaleString()} seguidores
                        </small>
                      )}
                    </td>
                    <td className="investigation-cell-contact">
                      {report.telefono_publico && (
                        <div className="investigation-contact-phone">{report.telefono_publico}</div>
                      )}
                      <div className="investigation-contact-location">
                        {report.direccion_publica || report.pais || 'Argentina'}
                      </div>
                    </td>
                    <td className="investigation-cell-price">
                      {formattedPrice}
                    </td>
                    <td style={{ padding: '14px 16px', fontWeight: 700, color: report.relevamiento_completitud >= 80 ? 'var(--success)' : 'var(--warning)' }}>
                      {report.relevamiento_completitud || 0}%
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <span 
                        className={`status-badge investigation-status investigation-status--${(report.estado || '').toLowerCase().replace(/[^a-z]+/g, '-')}`} 
                        style={{ 
                          border: '1px solid currentColor'
                        }}
                      >
                        {report.estado}
                      </span>
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                      <Link 
                        to={`/suspects/${report.id}`} 
                        className="btn-primary" 
                        style={{ padding: '6px 14px', fontSize: '0.82rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                      >
                        <FaUserSecret /> Abrir Caso
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      {!loading && total > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Mostrando {((page - 1) * limit) + 1} a {Math.min(page * limit, total)} de {total} hallazgos
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button 
              className="btn-secondary btn-sm" 
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              Anterior
            </button>
            <span style={{ padding: '6px 12px', fontSize: '0.85rem', color: 'var(--text-primary)' }}>
              Pág {page} de {totalPages || 1}
            </span>
            <button 
              className="btn-secondary btn-sm" 
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages || totalPages === 0}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}