import { useEffect, useRef, useState } from 'react';
import { FaCheckCircle, FaExclamationTriangle, FaPlay, FaSearch } from 'react-icons/fa';
import { getBrands } from '../services/brandService';
import api from '../services/api';

const ARGENTINA_LOCATIONS = [
  'Argentina', 'CABA', 'Buenos Aires', 'Catamarca', 'Chaco', 'Chubut', 'Córdoba',
  'Corrientes', 'Entre Ríos', 'Formosa', 'Jujuy', 'La Pampa', 'La Rioja', 'Mendoza',
  'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan', 'San Luis', 'Santa Cruz',
  'Santa Fe', 'Santiago del Estero', 'Tierra del Fuego', 'Tucumán',
];

export default function TargetedSearch() {
  const [brands, setBrands] = useState([]);
  const [brandId, setBrandId] = useState('');
  const [location, setLocation] = useState('Argentina');
  const [keywordsText, setKeywordsText] = useState('');
  const [durationMinutes, setDurationMinutes] = useState(15);
  const [loading, setLoading] = useState(false);
  const [searchStatus, setSearchStatus] = useState({ is_running: false });
  const [feedback, setFeedback] = useState(null);
  const wasSearchRunning = useRef(false);

  useEffect(() => {
    const loadBrands = async () => {
      try {
        const response = await getBrands('activa');
        const activeBrands = (response.data || []).filter(brand => (brand.estado || 'activa').toLowerCase() === 'activa');
        setBrands(activeBrands);
        if (activeBrands.length) setBrandId(String(activeBrands[0].id));
      } catch {
        setFeedback({ type: 'error', text: 'No se pudieron cargar las marcas activas.' });
      }
    };
    loadBrands();
  }, []);

  useEffect(() => {
    let active = true;
    const refreshSearchStatus = async () => {
      try {
        const response = await api.get('/api/cron/search/status');
        const status = response.data || { is_running: false };
        if (!active) return;
        setSearchStatus(status);
        if (status.is_running) {
          wasSearchRunning.current = true;
        } else if (wasSearchRunning.current && status.finished_at) {
          wasSearchRunning.current = false;
          setFeedback(status.last_error
            ? { type: 'error', text: `La búsqueda terminó con un error: ${status.last_error}` }
            : { type: 'success', text: `Búsqueda finalizada. ${status.processed_items || 0} publicaciones procesadas.` });
        }
      } catch {
        if (active) setSearchStatus({ is_running: false });
      }
    };

    refreshSearchStatus();
    const intervalId = window.setInterval(refreshSearchStatus, 2000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!brandId || loading || searchStatus.is_running) return;

    const keywords = keywordsText
      .split(/[\n,;]/)
      .map(keyword => keyword.trim())
      .filter(Boolean);

    setLoading(true);
    setFeedback(null);
    try {
      const response = await api.post('/api/cron/search', {
        brand_id: Number(brandId),
        locations: [location],
        keywords,
        duration_minutes: Number(durationMinutes),
      });
      const data = response.data;
      setFeedback({
        type: 'success',
        text: data.using_saved_keywords
          ? `Búsqueda iniciada por ${durationMinutes} minutos con las keywords configuradas para la marca.`
          : `Búsqueda iniciada por ${durationMinutes} minutos con ${keywords.length} keyword${keywords.length === 1 ? '' : 's'} del cliente.`,
      });
    } catch (error) {
      setFeedback({ type: 'error', text: error.response?.data?.detail || 'No se pudo iniciar la búsqueda.' });
    } finally {
      setLoading(false);
    }
  };

  const searchInProgress = loading || searchStatus.is_running;

  return (
    <section className="dashboard-search glass-card" aria-labelledby="dashboard-search-title">
      <div className="dashboard-search__heading">
        <div className="dashboard-search__icon"><FaSearch /></div>
        <div>
          <h2 id="dashboard-search-title">Búsqueda dirigida</h2>
          <p>Consulta fuentes públicas con términos y alcance geográfico definidos.</p>
        </div>
      </div>

      <form className="dashboard-search__form" onSubmit={handleSubmit}>
        <div className="dashboard-search__fields">
          <label className="dashboard-search__field">
            <span>Marca</span>
            <select className="input-field" value={brandId} onChange={event => setBrandId(event.target.value)} required disabled={!brands.length}>
              {brands.length === 0 && <option value="">Sin marcas activas</option>}
              {brands.map(brand => <option key={brand.id} value={brand.id}>{brand.nombre}</option>)}
            </select>
          </label>
          <label className="dashboard-search__field">
            <span>Ubicación</span>
            <select className="input-field" value={location} onChange={event => setLocation(event.target.value)}>
              {ARGENTINA_LOCATIONS.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="dashboard-search__field">
            <span>Duración de búsqueda</span>
            <select className="input-field" value={durationMinutes} onChange={event => setDurationMinutes(event.target.value)}>
              {[5, 10, 15, 30, 45, 60].map(value => <option key={value} value={value}>{value} minutos</option>)}
            </select>
          </label>
        </div>

        <label className="dashboard-search__field">
          <span>Keywords del cliente <small>(opcional; una por línea o separadas por coma)</small></span>
          <textarea
            className="input-field dashboard-search__keywords"
            value={keywordsText}
            onChange={event => setKeywordsText(event.target.value)}
            placeholder="Ej.: zapatillas réplica\nNike Air Max usadas"
            rows={3}
          />
          <small>Si queda vacío, se usan las keywords configuradas para la marca.</small>
        </label>

        <div className="dashboard-search__footer">
          {searchStatus.is_running && (
            <p className="dashboard-search__feedback" role="status" aria-live="polite">
              <span className="spinner-inline" aria-hidden="true" />
              {searchStatus.current_query
                ? `Buscando: ${searchStatus.current_query}`
                : 'Búsqueda en curso'}
            </p>
          )}
          {!searchStatus.is_running && searchStatus.last_error && (
            <p className="dashboard-search__feedback dashboard-search__feedback--error" role="alert">
              {`La última búsqueda falló: ${searchStatus.last_error}`}
            </p>
          )}
          {feedback && (
            <p className={`dashboard-search__feedback dashboard-search__feedback--${feedback.type}`} role="status">
              {feedback.type === 'success' ? <FaCheckCircle /> : <FaExclamationTriangle />}
              {feedback.text}
            </p>
          )}
          <button className="btn-primary" type="submit" disabled={searchInProgress || !brandId}>
            {searchInProgress ? <span className="spinner-inline" /> : <FaPlay />}
            {searchInProgress ? 'Buscando...' : 'Iniciar búsqueda'}
          </button>
        </div>
      </form>
    </section>
  );
}
