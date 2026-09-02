// Barra de Navegación — componente principal de navegación
import { useState, useEffect } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { FaShieldAlt, FaSun, FaMoon, FaBars, FaTimes, FaSignOutAlt } from 'react-icons/fa';
import { useAuth } from '../context/AuthContext';
import './Navbar.css';

import { getCronStatus } from '../services/cronService';

export default function Navbar() {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
  const [menuOpen, setMenuOpen] = useState(false);
  const [iconRotate, setIconRotate] = useState(false);
  const [cronRunning, setCronRunning] = useState(false);
  const [prevCronRunning, setPrevCronRunning] = useState(false);
  const [showScanComplete, setShowScanComplete] = useState(false);

  // Aplicar tema al documento
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Chequear estado de cron
  useEffect(() => {
    if (!isAuthenticated) return;
    
    const checkCron = async () => {
      try {
        const res = await getCronStatus();
        const isRunning = res.data.is_running;
        setCronRunning((prev) => {
          if (prev === true && isRunning === false) {
            // Pasó de ejecutándose a detenido
            setShowScanComplete(true);
          }
          return isRunning;
        });
      } catch (e) {}
    };

    checkCron();
    const interval = setInterval(checkCron, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // Alternar tema claro/oscuro
  const toggleTheme = () => {
    setIconRotate(true);
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
    setTimeout(() => setIconRotate(false), 400);
  };

  // Cerrar sesión y redirigir
  const handleLogout = () => {
    logout();
    setMenuOpen(false);
    navigate('/');
  };

  // Obtener iniciales del usuario
  const getInitials = () => {
    if (!user) return '?';
    const first = user.nombre?.[0] || '';
    const last = user.apellido?.[0] || '';
    return (first + last).toUpperCase();
  };

  return (
    <>
    {cronRunning && (
      <div style={{ position: 'fixed', bottom: 0, left: 0, width: '100%', background: 'var(--danger)', color: '#fff', textAlign: 'center', padding: '12px', fontSize: '0.95rem', fontWeight: 600, zIndex: 9999, boxShadow: '0 -4px 12px rgba(0,0,0,0.2)' }}>
        ⚠️ ATENCIÓN: El motor Cron está actualmente en ejecución. Las modificaciones a las marcas han sido bloqueadas temporalmente para evitar corrupción de datos.
      </div>
    )}
    <nav className="navbar">
      <div className="navbar__inner">
        {/* Logo */}
        <Link to="/" className="navbar__logo">
          <img src="/netholmes-icon.png" alt="Net Holmes" className="navbar__logo-img" />
          <span className="navbar__logo-text">net <strong className="navbar__logo-highlight">HOLMES</strong></span>
        </Link>

        {/* Menú hamburguesa para móvil */}
        <button
          className="navbar__hamburger"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Menú"
        >
          {menuOpen ? <FaTimes /> : <FaBars />}
        </button>

        {/* Menú móvil desplegable */}
        {menuOpen && (
          <>
            <div className="navbar__mobile-backdrop" onClick={() => setMenuOpen(false)} />
            <div className="navbar__mobile-menu">
              {isAuthenticated && (
                <div className="navbar__links">
                <NavLink
                  to="/dashboard"
                  className={({ isActive }) =>
                    `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                  }
                  onClick={() => setMenuOpen(false)}
                >
                  Dashboard
                </NavLink>
                <NavLink
                  to="/investigation"
                  className={({ isActive }) =>
                    `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                  }
                  onClick={() => setMenuOpen(false)}
                >
                  Investigaciones
                </NavLink>
                  <NavLink
                    to="/manual-scan"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                    onClick={() => setMenuOpen(false)}
                  >
                    Scraping Manual
                  </NavLink>
                  <NavLink
                    to="/chat"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                    onClick={() => setMenuOpen(false)}
                  >
                    💬 Honeypot Chat
                  </NavLink>
                  <NavLink
                    to="/correlations"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                    onClick={() => setMenuOpen(false)}
                  >
                    Correlaciones
                  </NavLink>
                {isAdmin && (
                  <>
                    <NavLink
                      to="/brands"
                      className={({ isActive }) =>
                        `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                      }
                      onClick={() => setMenuOpen(false)}
                    >
                      Marcas
                    </NavLink>
                    <NavLink
                      to="/cron"
                      className={({ isActive }) =>
                        `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                      }
                      onClick={() => setMenuOpen(false)}
                    >
                      Cron
                    </NavLink>
                    <NavLink
                      to="/admin/scrapers"
                      className={({ isActive }) =>
                        `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                      }
                      onClick={() => setMenuOpen(false)}
                    >
                      Scrapers & APIs
                    </NavLink>
                    <NavLink
                      to="/admin/whatsapp-settings"
                      className={({ isActive }) =>
                        `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                      }
                      onClick={() => setMenuOpen(false)}
                    >
                      WhatsApp
                    </NavLink>
                    <NavLink
                      to="/admin/users"
                      className={({ isActive }) =>
                        `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                      }
                      onClick={() => setMenuOpen(false)}
                    >
                      ⚙️ Accesos
                    </NavLink>
                  </>
                )}
              </div>
            )}
            <div className="navbar__actions">
              <button className="navbar__theme-btn" onClick={toggleTheme} aria-label="Cambiar tema">
                <span className={`navbar__theme-icon ${iconRotate ? 'navbar__theme-icon--rotate' : ''}`}>
                  {theme === 'light' ? <FaMoon /> : <FaSun />}
                </span>
              </button>
              {isAuthenticated ? (
                <>
                  <div className="navbar__user-badge">
                    <span className="navbar__user-avatar">{getInitials()}</span>
                    <span>{user?.nombre}</span>
                  </div>
                  <button className="navbar__logout-btn" onClick={handleLogout}>
                    <FaSignOutAlt style={{ marginRight: '6px' }} /> Cerrar Sesión
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className="btn-ghost" onClick={() => setMenuOpen(false)}>
                    Iniciar Sesión
                  </Link>
                  <Link to="/register" className="btn-primary" onClick={() => setMenuOpen(false)}>
                    Registrarse
                  </Link>
                </>
              )}
            </div>
          </div>
        </>
      )}

        {/* Navegación de escritorio (oculta en móvil) */}
        <div className="navbar__links navbar__desktop-only" style={{ display: '' }}>
          {isAuthenticated && (
            <>
              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                }
              >
                Dashboard
              </NavLink>
              <NavLink
                to="/investigation"
                className={({ isActive }) =>
                  `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                }
              >
                Investigaciones
              </NavLink>
              <NavLink
                to="/manual-scan"
                className={({ isActive }) =>
                  `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                }
              >
                Scraping Manual
              </NavLink>
              <NavLink
                to="/chat"
                className={({ isActive }) =>
                  `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                }
              >
                💬 Honeypot Chat
              </NavLink>
              <NavLink
                to="/correlations"
                className={({ isActive }) =>
                  `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                }
              >
                Correlaciones
              </NavLink>
              {isAdmin && (
                <>
                  <NavLink
                    to="/brands"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                  >
                    Marcas
                  </NavLink>
                  <NavLink
                    to="/cron"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                  >
                    Cron
                  </NavLink>
                  <NavLink
                    to="/admin/scrapers"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                  >
                    Scrapers & APIs
                  </NavLink>
                  <NavLink
                    to="/admin/whatsapp-settings"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                  >
                    WhatsApp
                  </NavLink>
                  <NavLink
                    to="/admin/users"
                    className={({ isActive }) =>
                      `navbar__link ${isActive ? 'navbar__link--active' : ''}`
                    }
                    title="Administración de Accesos y Usuarios"
                  >
                    ⚙️ Accesos
                  </NavLink>
                </>
              )}
            </>
          )}
        </div>

        {/* Acciones de escritorio */}
        <div className="navbar__actions navbar__desktop-only">
          <button className="navbar__theme-btn" onClick={toggleTheme} aria-label="Cambiar tema">
            <span className={`navbar__theme-icon ${iconRotate ? 'navbar__theme-icon--rotate' : ''}`}>
              {theme === 'light' ? <FaMoon /> : <FaSun />}
            </span>
          </button>

          {isAuthenticated ? (
            <>
              <div className="navbar__user-badge">
                <span 
                  className="navbar__user-avatar"
                  style={user?.rol === 'sup_admin' ? { border: '2px solid #FFD700', boxShadow: '0 0 10px rgba(255,215,0,0.5)', background: 'linear-gradient(135deg, #1A120B, #FFD700)' } : {}}
                >
                  {getInitials()}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontWeight: user?.rol === 'sup_admin' ? 700 : 500 }}>
                  {user?.nombre}
                  {user?.rol === 'sup_admin' && <span title="Super Administrador (SUP_ADMIN)" style={{ color: '#FFD700', fontSize: '0.85rem' }}>👑</span>}
                </span>
              </div>
              <button className="navbar__logout-btn" onClick={handleLogout} title="Cerrar Sesión">
                <FaSignOutAlt style={{ marginRight: '6px' }} /> Cerrar Sesión
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn-ghost">Iniciar Sesión</Link>
              <Link to="/register" className="btn-primary" style={{ textDecoration: 'none' }}>
                Registrarse
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
    
    {/* Modal de Finalización de Escaneo */}
    {showScanComplete && (
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="glass-card fade-in" style={{ padding: '2rem', textAlign: 'center', maxWidth: '400px', background: 'var(--bg-card)' }}>
          <FaShieldAlt style={{ fontSize: '3rem', color: 'var(--success)', marginBottom: '1rem' }} />
          <h2 style={{ marginBottom: '1rem', color: 'var(--accent-primary)' }}>Escaneo Terminado</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
            El motor de Inteligencia ha finalizado la recolección de evidencia en todas las plataformas.
          </p>
          <button className="btn-primary" onClick={() => setShowScanComplete(false)} style={{ width: '100%' }}>
            Entendido
          </button>
        </div>
      </div>
    )}
    </>
  );
}
