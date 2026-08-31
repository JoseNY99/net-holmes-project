// Página de Inicio — landing premium con hero y características
import { Link } from 'react-router-dom';
import { FaShieldAlt, FaChartLine, FaFileAlt, FaArrowRight } from 'react-icons/fa';
import { useAuth } from '../context/AuthContext';
import './Home.css';

// Datos de las tarjetas de características
const features = [
  {
    icon: <FaShieldAlt />,
    title: 'Protección Automatizada',
    text: 'Motor de búsqueda OSINT que monitorea plataformas de comercio electrónico y redes sociales 24/7 para detectar falsificaciones.',
  },
  {
    icon: <FaChartLine />,
    title: 'Análisis Forense',
    text: 'Perfilado inteligente de sospechosos con correlación de patrones, geolocalización y rastreo de redes de distribución.',
  },
  {
    icon: <FaFileAlt />,
    title: 'Reportes Inteligentes',
    text: 'Exportación profesional en múltiples formatos con hallazgos detallados, evidencia y recomendaciones legales.',
  },
];

export default function Home() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="home">
      {/* Sección Hero */}
      <section className="hero">
        {/* Formas decorativas flotantes */}
        <div className="hero__shapes">
          <div className="hero__shape hero__shape--1" />
          <div className="hero__shape hero__shape--2" />
          <div className="hero__shape hero__shape--3" />
        </div>

        <div className="hero__content">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', marginBottom: '16px' }}>
            <img src="/netholmes-icon.png" alt="Net Holmes" style={{ height: '70px', width: 'auto', filter: 'drop-shadow(0 4px 16px rgba(16, 197, 201, 0.4))' }} />
          </div>
          <h1 className="hero__title">Net <span style={{ color: 'var(--accent-primary)' }}>Holmes</span></h1>
          <p className="hero__subtitle">Sistema de Inteligencia y Detección de Falsificaciones</p>
          <p className="hero__description">
            Plataforma integral de investigación y protección de propiedad intelectual que combina
            rastreo OSINT multiplataforma, análisis forense de redes y perfilado automatizado
            de infractores para salvaguardar el valor de tus marcas.
          </p>

          <div className="hero__cta">
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn-primary">
                Ir al Dashboard <FaArrowRight />
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn-primary">
                  Iniciar Sesión
                </Link>
                <Link to="/register" className="btn-secondary">
                  Registrarse
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Sección de Características */}
      <section className="features">
        <div className="features__header">
          <span className="features__label">Capacidades</span>
          <h2 className="features__title">Defensa Integral de Marca</h2>
        </div>

        <div className="features__grid">
          {features.map((feature, index) => (
            <div key={index} className="feature-card stagger-item">
              <div className="feature-card__icon">{feature.icon}</div>
              <h3 className="feature-card__title">{feature.title}</h3>
              <p className="feature-card__text">{feature.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
