// Página Dashboard — panel principal del usuario Net Holmes
import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FaShieldAlt,
  FaSearch,
  FaSpinner,
  FaStop,
  FaFileAlt,
  FaUserSecret,
  FaCog,
  FaFacebookF,
  FaInstagram,
  FaTiktok,
  FaShoppingBag,
  FaClock,
  FaExclamationTriangle,
  FaArrowRight,
  FaBroadcastTower,
  FaBrain,
  FaUsers
} from 'react-icons/fa';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar
} from 'recharts';
import { useAuth } from '../context/AuthContext';
import { getBrands } from '../services/brandService';
import { getSearchLocations, startDashboardSearch, getDashboardSearchStatus, stopDashboardSearch } from '../services/dashboardSearchService';
import api from '../services/api';
import './Dashboard.css';

// Componente premium ágil para efecto Count-Up
function AnimatedCounter({ value, duration = 400 }) {
  const [count, setCount] = useState(value <= 5 ? value : 0);

  useEffect(() => {
    if (!value || value <= 5) return;
    let frameId;
    let startTimestamp = null;
    const actualDuration = Math.min(duration, 500);
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / actualDuration, 1);
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(easeProgress * value));
      if (progress < 1) {
        frameId = window.requestAnimationFrame(step);
      } else {
        setCount(value);
      }
    };
    frameId = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(frameId);
  }, [value, duration]);

  return <>{(value <= 5 ? value || 0 : count || 0).toLocaleString('es-AR')}</>;
}

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [activeBrands, setActiveBrands] = useState(0);
  const [brands, setBrands] = useState([]);
  const [selectedBrand, setSelectedBrand] = useState('');
  const [selectedCountry, setSelectedCountry] = useState('Argentina');
  const [locations, setLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState('');
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [searchTerms, setSearchTerms] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState(['facebook', 'instagram', 'tiktok', 'mercadolibre']);
  const [searching, setSearching] = useState(false);
  const [searchFeedback, setSearchFeedback] = useState(null);
  const scanWasRunning = useRef(false);
  const searchRequestPending = useRef(false);
  const [scanStatus, setScanStatus] = useState(null);
  const [statusLoaded, setStatusLoaded] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const countryScope = locations.find(location => location.pais === selectedCountry);
  const remainingSeconds = scanStatus?.deadline_at
    ? Math.max(0, Math.ceil((Date.parse(scanStatus.deadline_at) - now) / 1000))
    : null;
  
  const [stats, setStats] = useState({
    analisis_pendientes: 0,
    reportes_generados: 0,
    sospechosos_detectados: 0,
    timeline: [],
    platforms: [],
    recent_activity: []
  });

  useEffect(() => {
    const fetchBrands = async () => {
      try {
        const response = await getBrands();
        const brandsList = Array.isArray(response?.data) ? response.data : [];
        const activeList = brandsList.filter(b => (b.estado || '').toLowerCase() === 'activa');
        setBrands(activeList);
        setSelectedBrand(current => current || String(activeList[0]?.id || ''));
        setActiveBrands(activeList.length > 0 ? activeList.length : brandsList.length);
      } catch {
        setActiveBrands(0);
      }
    };
    const fetchStats = async () => {
      try {
        const res = await api.get('/api/dashboard/stats');
        const data = res.data;
        if (!data) return;
        
        // Formatear la hora localmente
        const formattedActivity = (data.recent_activity || []).map(act => ({
          ...act,
          timeFormatted: act.time ? new Date(act.time).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' }) : ''
        }));

        setStats({
          analisis_pendientes: data.analisis_pendientes || 0,
          reportes_generados: data.reportes_generados || 0,
          sospechosos_detectados: data.sospechosos_detectados || 0,
          timeline: data.timeline || [],
          platforms: data.platforms || [],
          recent_activity: formattedActivity
        });
      } catch {
        // Silencio en consola para evitar spam de polling
      }
    };
    
    fetchBrands();
    fetchStats();
    getSearchLocations()
      .then(({ data }) => setLocations(data))
      .catch(() => setSearchFeedback({ type: 'error', text: 'No se pudieron cargar las provincias y estados. Recarga el dashboard para reintentar.' }));
    
    // Polling cada 15 segundos para actualizar estados en vivo
    const intervalId = setInterval(fetchStats, 15000);
    window.addEventListener('dashboard-search-finished', fetchStats);
    return () => {
      clearInterval(intervalId);
      window.removeEventListener('dashboard-search-finished', fetchStats);
    };
  }, []);

  useEffect(() => {
    let subscribed = true;
    let timerId;

    const pollSearchStatus = async () => {
      if (!subscribed) return;
      let nextInterval = scanWasRunning.current ? 2000 : 5000;
      try {
        const { data } = await getDashboardSearchStatus();
        if (!subscribed) return;
        setStatusLoaded(true);
        if (!searchRequestPending.current) {
          setScanStatus(data);
          setSearching(Boolean(data.is_running));
          if (data.is_running) {
            scanWasRunning.current = true;
            nextInterval = 2000;
          } else if (scanWasRunning.current) {
            const message = {
              completed: data.finish_reason === 'deadline'
                ? 'Se cumplió el tiempo máximo de búsqueda.'
                : 'La búsqueda terminó correctamente.',
              stopped: 'La búsqueda fue detenida.',
              failed: 'La búsqueda terminó con errores. Los resultados guardados se conservaron.',
            }[data.status] || 'La búsqueda finalizó.';
            setSearchFeedback({
              type: data.status === 'failed' ? 'error' : 'success',
              text: `${message} Nuevos: ${data.saved || 0}. Duplicados omitidos o actualizados: ${data.duplicates || 0}.${data.warning ? ` ${data.warning}` : ''}`,
            });
            scanWasRunning.current = false;
            window.dispatchEvent(new Event('dashboard-search-finished'));
          }
        }
      } catch {
        if (subscribed) setSearchFeedback({ type: 'error', text: 'No se pudo consultar el estado. Reintentando la conexión…' });
      }
      if (subscribed) timerId = setTimeout(pollSearchStatus, nextInterval);
    };

    pollSearchStatus();
    return () => {
      subscribed = false;
      if (timerId) clearTimeout(timerId);
    };
  }, []);

  useEffect(() => {
    if (!searching) return;
    const timerId = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timerId);
  }, [searching]);

  const handleStartSearch = async (event) => {
    event.preventDefault();
    if (!selectedBrand || searching || searchRequestPending.current) return;
    searchRequestPending.current = true;
    setSearching(true);
    setSearchFeedback(null);
    try {
      const keywords = searchTerms.split(',').map(term => term.trim()).filter(Boolean);
      const { data } = await startDashboardSearch({
        brand_ids: [Number(selectedBrand)],
        pais: selectedCountry,
        provincias: selectedLocation ? [selectedLocation] : [],
        keywords,
        duration_minutes: durationMinutes,
        plataformas: selectedPlatforms,
        proveedor: 'google_meli_osint',
      });
      setScanStatus(data);
      setNow(Date.now());
      scanWasRunning.current = true;
    } catch (error) {
      const detail = error.response?.data?.detail;
      setSearchFeedback({
        type: 'error',
        text: typeof detail === 'string' ? detail : 'No se pudo iniciar la búsqueda. Revisa los filtros seleccionados.',
      });
      setSearching(false);
    } finally {
      searchRequestPending.current = false;
    }
  };

  const handleStopSearch = async () => {
    if (stopping || searchRequestPending.current) return;
    searchRequestPending.current = true;
    setStopping(true);
    try {
      const { data } = await stopDashboardSearch();
      setScanStatus(data);
      setSearching(false);
      scanWasRunning.current = false;
      setSearchFeedback({ type: 'success', text: `Búsqueda detenida. Nuevos: ${data.saved || 0}. Duplicados omitidos o actualizados: ${data.duplicates || 0}.` });
      window.dispatchEvent(new Event('dashboard-search-finished'));
    } catch {
      setSearchFeedback({ type: 'error', text: 'No se pudo detener la búsqueda. Vuelve a intentarlo.' });
    } finally {
      searchRequestPending.current = false;
      setStopping(false);
    }
  };

  const getPlatformIcon = (platform) => {
    const p = (platform || '').toLowerCase();
    if (p.includes('facebook')) return { icon: <FaFacebookF />, name: 'Facebook', className: 'feed-icon-fb' };
    if (p.includes('instagram')) return { icon: <FaInstagram />, name: 'Instagram', className: 'feed-icon-ig' };
    if (p.includes('tiktok')) return { icon: <FaTiktok />, name: 'TikTok', className: 'feed-icon-tt' };
    if (p.includes('mercadolibre') || p.includes('meli')) return { icon: <FaShoppingBag />, name: 'Mercado Libre', className: 'feed-icon-ml' };
    return { icon: <FaSearch />, name: platform, className: 'feed-icon-default' };
  };

  const getStatusBadge = (estado) => {
    const s = (estado || '').toLowerCase();
    if (s === 'sospechoso') {
      return (
        <span className="feed-status-badge feed-status-sospechoso">
          <FaExclamationTriangle /> Sospechoso
        </span>
      );
    }
    if (s === 'investigando') {
      return (
        <span className="feed-status-badge feed-status-investigando">
          <FaSearch /> En Análisis
        </span>
      );
    }
    if (s === 'descartado') {
      return (
        <span className="feed-status-badge feed-status-descartado">
          Descartado
        </span>
      );
    }
    return (
      <span className="feed-status-badge feed-status-pendiente">
        <FaClock /> Pendiente
      </span>
    );
  };

  const statCards = [
    {
      icon: <FaShieldAlt />,
      iconClass: 'stat-card__icon--brands',
      number: activeBrands,
      label: 'Marcas Activas',
    },
    {
      icon: <FaSearch />,
      iconClass: 'stat-card__icon--analysis',
      number: stats.analisis_pendientes,
      label: 'Análisis Pendientes',
    },
    {
      icon: <FaFileAlt />,
      iconClass: 'stat-card__icon--reports',
      number: stats.reportes_generados,
      label: 'Reportes Generados',
    },
    {
      icon: <FaUserSecret />,
      iconClass: 'stat-card__icon--suspects',
      number: stats.sospechosos_detectados,
      label: 'Sospechosos Detectados',
    },
  ];

  return (
    <div className="page-container dashboard fade-in">
      {/* Encabezado de bienvenida */}
      <div className="dashboard__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '24px' }}>
        <div>
          <h1 className="dashboard__welcome">
            Centro de Control <span className="dashboard__welcome-name">NET HOLMES</span>
          </h1>
          <p className="dashboard__welcome-sub">
            Operador en línea: <strong>{user?.nombre || 'Analista'}</strong> — Modo de Inteligencia OSINT Activo
          </p>
        </div>

        {/* Acciones rápidas (solo admin) */}
        {isAdmin && (
          <div className="dashboard__quick-actions">
            <Link to="/brands" className="action-pill-btn action-pill-primary">
              <span className="action-pill-icon"><FaShieldAlt /></span>
              <span>Gestionar Marcas</span>
            </Link>
            <Link to="/cron" className="action-pill-btn action-pill-secondary">
              <span className="action-pill-icon"><FaCog /></span>
              <span>Configurar Cron</span>
            </Link>
            <Link to="/admin/logs" className="action-pill-btn action-pill-secondary">
              <span className="action-pill-icon"><FaBrain /></span>
              <span>Memoria RAG</span>
            </Link>
            <Link to="/admin/users" className="action-pill-btn action-pill-accent">
              <span className="action-pill-icon"><FaUsers /></span>
              <span>Accesos</span>
            </Link>
          </div>
        )}
      </div>

      {/* Tarjetas de estadísticas */}
      <div className="dashboard__stats">
        {statCards.map((stat, index) => (
          <div key={index} className="glass-card stat-card stagger-item">
            <div className={`stat-card__icon ${stat.iconClass}`}>
              {stat.icon}
            </div>
            <div className="stat-card__info">
              <div className="stat-card__number">
                <AnimatedCounter value={stat.number} />
              </div>
              <div className="stat-card__label">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      <section className="dashboard-search" aria-labelledby="dashboard-search-title">
        <div className="dashboard-search__heading">
          <div>
            <h2 id="dashboard-search-title">Nueva búsqueda</h2>
            <p>Selecciona el país y, si lo necesitas, una provincia o estado.</p>
          </div>
          <FaSearch aria-hidden="true" />
        </div>
        <form className="dashboard-search__form" onSubmit={handleStartSearch} aria-busy={searching}>
          <label>
            Marca
            <select className="input-field" value={selectedBrand} onChange={event => setSelectedBrand(event.target.value)} disabled={searching} required>
              <option value="" disabled>Seleccionar marca</option>
              {brands.map(brand => <option key={brand.id} value={brand.id}>{brand.nombre}</option>)}
            </select>
          </label>
          <label>
            País
            <select className="input-field" value={selectedCountry} disabled={searching || locations.length === 0} onChange={event => {
              setSelectedCountry(event.target.value);
              setSelectedLocation('');
            }}>
              {locations.length === 0 && <option value="Argentina">Argentina</option>}
              {locations.map(location => <option key={location.pais} value={location.pais}>{location.pais}</option>)}
            </select>
          </label>
          <label>
            {selectedCountry === 'Argentina' ? 'Provincia' : 'Estado'}
            <select className="input-field" value={selectedLocation} onChange={event => setSelectedLocation(event.target.value)} disabled={searching || !countryScope}>
              <option value="">Todo el país</option>
              {(countryScope?.provincias || []).map(location => <option key={location} value={location}>{location}</option>)}
            </select>
          </label>
          <label className="dashboard-search__terms">
            Palabras clave (opcional)
            <input
              className="input-field"
              value={searchTerms}
              disabled={searching}
              maxLength={2009}
              onChange={event => setSearchTerms(event.target.value)}
              placeholder="Ej.: zapatillas, remeras, buzos"
            />
          </label>
          <label>
            Tiempo máximo
            <select className="input-field" value={durationMinutes} onChange={event => setDurationMinutes(Number(event.target.value))} disabled={searching}>
              <option value={5}>5 minutos</option>
              <option value={15}>15 minutos</option>
              <option value={30}>30 minutos</option>
              <option value={60}>60 minutos</option>
            </select>
          </label>
          <div style={{ marginTop: '15px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>
              Plataformas
            </label>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              {['facebook', 'instagram', 'tiktok', 'mercadolibre'].map(platform => (
                <label key={platform} style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    disabled={searching}
                    checked={selectedPlatforms.includes(platform)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedPlatforms([...selectedPlatforms, platform]);
                      } else {
                        setSelectedPlatforms(selectedPlatforms.filter(p => p !== platform));
                      }
                    }}
                    style={{ cursor: 'pointer' }}
                  />
                  <span style={{ textTransform: 'capitalize' }}>
                    {platform === 'mercadolibre' ? 'Mercado Libre' : platform.charAt(0).toUpperCase() + platform.slice(1)}
                  </span>
                </label>
              ))}
            </div>
          </div>
          {searching ? (
            <button className="btn-primary" type="button" onClick={handleStopSearch} disabled={stopping || !scanStatus?.is_running}>
              <FaStop /> {stopping ? 'Deteniendo…' : 'Detener'}
            </button>
          ) : (
            <button className="btn-primary" type="submit" disabled={!statusLoaded || !countryScope || !selectedBrand || selectedPlatforms.length === 0}>
              <FaSearch /> Iniciar búsqueda
            </button>
          )}
        </form>
        {searching && (
          <div className="dashboard-search__loading" role="status" aria-live="polite">
            <FaSpinner className="dashboard-search__spinner" aria-hidden="true" />
            <span>
              {scanStatus?.is_running ? `Buscando${scanStatus.current_platform ? ` en ${scanStatus.current_platform === 'mercadolibre' ? 'Mercado Libre' : scanStatus.current_platform}` : ''}…` : 'Iniciando búsqueda…'}
              {scanStatus?.is_running && ` ${scanStatus.saved || 0} nuevos · ${scanStatus.duplicates || 0} duplicados omitidos o actualizados`}
              {remainingSeconds !== null && searching && ` · Máximo restante: ${Math.floor(remainingSeconds / 60)}:${String(remainingSeconds % 60).padStart(2, '0')}`}
            </span>
          </div>
        )}
        {searchFeedback && <p className={`dashboard-search__feedback ${searchFeedback.type}`} role="status">{searchFeedback.text}</p>}
      </section>

      <div className="dashboard__grid">
        {/* Gráficos */}
        <div className="dashboard__charts">
          <div className="glass-card chart-container">
            <h3 className="chart-title">Actividad de Recolección (Últimos 7 días)</h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={stats.timeline}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="name" stroke="var(--text-secondary)" />
                  <YAxis stroke="var(--text-secondary)" />
                  <RechartsTooltip contentStyle={{backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--accent-cyan)', borderRadius: '8px'}} />
                  <Line type="monotone" dataKey="scans" stroke="var(--accent-cyan)" strokeWidth={3} dot={{ fill: 'var(--accent-cyan)', r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          <div className="glass-card chart-container">
            <h3 className="chart-title">Distribución por Plataforma</h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={stats.platforms}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="name" stroke="var(--text-secondary)" />
                  <YAxis stroke="var(--text-secondary)" />
                  <RechartsTooltip contentStyle={{backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--accent-primary)', borderRadius: '8px'}} />
                  <Bar dataKey="value" fill="var(--accent-primary)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Live Feed Modernizado */}
        <div className="glass-card dashboard__feed-panel">
          <div className="feed-header">
            <div>
              <h3 className="feed-title">
                <FaBroadcastTower className="feed-live-icon" /> Activity Feed
              </h3>
              <span className="feed-subtitle">Registro en tiempo real de infracciones</span>
            </div>
            <div className="feed-live-beacon">
              <span className="feed-beacon-dot"></span>
              EN VIVO
            </div>
          </div>

          <div className="feed-body">
            {stats.recent_activity.length === 0 ? (
              <div className="feed-empty-state">
                <FaSearch className="feed-empty-icon" />
                <p>Esperando datos de recolección automática...</p>
                <small>Los resultados de los bots y scrapers aparecerán aquí en vivo.</small>
              </div>
            ) : (
              <div className="feed-list">
                {stats.recent_activity.map((act, i) => {
                  const platMeta = getPlatformIcon(act.plataforma);
                  return (
                    <div 
                      key={act.id || i} 
                      className="feed-card-item"
                      onClick={() => navigate(`/suspects/${act.id}`)}
                      title={`Ver expediente del reporte #${act.id}`}
                    >
                      <div className={`feed-plat-avatar ${platMeta.className}`}>
                        {platMeta.icon}
                      </div>
                      <div className="feed-card-content">
                        <div className="feed-card-top">
                          <span className="feed-seller-name">{act.vendedor}</span>
                          <span className="feed-time">
                            <FaClock style={{ fontSize: '0.7rem', marginRight: 3 }} />
                            {act.timeFormatted}
                          </span>
                        </div>
                        <div className="feed-card-bottom">
                          <div className="feed-meta-tags">
                            <span className="feed-platform-tag">{platMeta.name}</span>
                            {act.marca && <span className="feed-brand-tag">{act.marca}</span>}
                          </div>
                          {getStatusBadge(act.estado)}
                        </div>
                      </div>
                      <div className="feed-arrow-hint">
                        <FaArrowRight />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
