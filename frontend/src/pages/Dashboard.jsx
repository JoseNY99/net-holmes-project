// Página Dashboard — panel principal del usuario Net Holmes
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FaShieldAlt,
  FaSearch,
  FaFileAlt,
  FaUserSecret,
  FaCog,
  FaTerminal,
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
import api from '../services/api';
import './Dashboard.css';

// Componente premium ágil para efecto Count-Up
function AnimatedCounter({ value, duration = 400 }) {
  const [count, setCount] = useState(value <= 5 ? value : 0);

  useEffect(() => {
    if (!value || value <= 5) {
      setCount(value || 0);
      return;
    }
    let startTimestamp = null;
    const actualDuration = Math.min(duration, 500);
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / actualDuration, 1);
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(easeProgress * value));
      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        setCount(value);
      }
    };
    window.requestAnimationFrame(step);
  }, [value, duration]);

  return <>{(count || 0).toLocaleString('es-AR')}</>;
}

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [activeBrands, setActiveBrands] = useState(0);
  
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
    
    // Polling cada 15 segundos para actualizar estados en vivo
    const intervalId = setInterval(fetchStats, 15000);
    return () => clearInterval(intervalId);
  }, []);

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

