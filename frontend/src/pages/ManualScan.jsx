import React, { useState } from 'react';
import { manualScan } from '../services/scanService';
import { getBrands } from '../services/brandService';
import { FaSearch, FaLink, FaTags, FaPlay, FaUserSecret } from 'react-icons/fa';
import { promoteScan } from '../services/suspectService';
import './ManualScan.css';

export default function ManualScan() {
  const [url, setUrl] = useState('');
  const [plataforma, setPlataforma] = useState('tiktok');
  const [brandId, setBrandId] = useState('');
  const [brands, setBrands] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [promoting, setPromoting] = useState(false);
  const [promoteSuccess, setPromoteSuccess] = useState(false);
  const [nuevaMarca, setNuevaMarca] = useState('');

  const fetchBrands = async () => {
    try {
      const resBrands = await getBrands('activa');
      setBrands(resBrands.data);
      if (resBrands.data.length > 0) setBrandId(resBrands.data[0].id);
    } catch (e) {
      console.error(e);
    }
  };

  React.useEffect(() => {
    fetchBrands();
  }, []);

  const handleScan = async (e) => {
    e.preventDefault();
    if (!url || (!brandId && !nuevaMarca)) return;
    
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let activeBrandId = brandId;
      
      // Si el usuario eligió crear una marca nueva, la creamos al vuelo
      if (brandId === 'nueva') {
        if (!nuevaMarca.trim()) {
          setError('El nombre de la nueva marca no puede estar vacío.');
          setLoading(false);
          return;
        }
        
        // Importamos dinámicamente o asumiendo que createBrand existe en brandService
        const { createBrand } = await import('../services/brandService');
        const newBrandRes = await createBrand({
          nombre: nuevaMarca,
          descripcion: 'Marca creada desde Scraping Manual',
          estado: 'activa'
        });
        
        activeBrandId = newBrandRes.data.id;
        
        // Refrescamos la lista de marcas para que aparezca
        await fetchBrands();
        setBrandId(activeBrandId);
      }

      const res = await manualScan(url, plataforma, activeBrandId);
      setResult(res.data);
    } catch (err) {
      setError('Error al ejecutar el scraping manual o crear la marca.');
    } finally {
      setLoading(false);
    }
  };

  const handlePromote = async () => {
    if (!result || !result.id) return;
    setPromoting(true);
    try {
      await promoteScan(result.id);
      setPromoteSuccess(true);
    } catch (err) {
      setError('Error al promover el resultado a sospechoso.');
    } finally {
      setPromoting(false);
    }
  };

  return (
    <div className="page-container fade-in">
      <div className="manual-scan-header">
        <h2><FaSearch /> Scraping Manual (Bajo Demanda)</h2>
        <p>Analiza una publicación específica de forma aislada sin afectar el historial del motor Cron.</p>
      </div>

      <div className="scan-grid">
        <div className="glass-card scan-form-panel">
          <form onSubmit={handleScan}>
            <div className="form-group">
              <label><FaLink /> URL de la Publicación</label>
              <input 
                type="url" 
                className="input-field" 
                placeholder="https://www.tiktok.com/..." 
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Plataforma</label>
                <select className="input-field" value={plataforma} onChange={(e) => setPlataforma(e.target.value)}>
                  <option value="tiktok">TikTok</option>
                  <option value="facebook">Facebook</option>
                  <option value="instagram">Instagram</option>
                  <option value="generico">Genérico</option>
                </select>
              </div>

              <div className="form-group">
                <label><FaTags /> Marca Afectada</label>
                <select className="input-field" value={brandId} onChange={(e) => {
                  setBrandId(e.target.value);
                  if (e.target.value !== 'nueva') setNuevaMarca('');
                }} required>
                  {brands.map(b => (
                    <option key={b.id} value={b.id}>{b.nombre}</option>
                  ))}
                  <option value="nueva" style={{fontWeight: 'bold', color: '#ffcc00'}}>+ Registrar nueva marca</option>
                  {brands.length === 0 && <option value="" disabled>No hay marcas activas</option>}
                </select>
                
                {brandId === 'nueva' && (
                  <input 
                    type="text" 
                    className="input-field mt-2 slide-down" 
                    placeholder="Nombre de la nueva marca..." 
                    value={nuevaMarca}
                    onChange={(e) => setNuevaMarca(e.target.value)}
                    required
                    autoFocus
                  />
                )}
              </div>
            </div>

            <button type="submit" className="btn-primary w-100 mt-2" disabled={loading || (!brandId && !nuevaMarca)}>
              {loading ? <div className="spinner"></div> : <><FaPlay /> Iniciar Análisis Forense</>}
            </button>
          </form>
          {error && <div className="error-message mt-2">{error}</div>}
        </div>

        <div className="glass-card scan-result-panel">
          {result ? (
            <div className="result-success slide-up">
              <h3>Análisis Completado</h3>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginTop: '15px' }}>
                <div className="glass-card p-3" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <h4 style={{ color: 'var(--accent)', marginBottom: '10px' }}>Datos Generales</h4>
                  <ul className="info-list">
                    <li><strong>Título:</strong> {result.titulo_publicacion || 'N/A'}</li>
                    <li><strong>Vendedor:</strong> {result.vendedor_nombre || 'Desconocido'}</li>
                    <li><strong>Ubicación:</strong> {result.vendedor_ubicacion || 'N/A'}</li>
                    <li><strong>Precio:</strong> {result.precio || 'N/A'}</li>
                  </ul>
                </div>
                
                <div className="glass-card p-3" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <h4 style={{ color: 'var(--accent)', marginBottom: '10px' }}>Contacto Extraído</h4>
                  <ul className="info-list">
                    <li><strong>Teléfonos:</strong> {result.vendedor_telefono || 'No encontrado'}</li>
                    {result.platform_data && typeof result.platform_data === 'string' && (
                      (() => {
                        try {
                          const pData = JSON.parse(result.platform_data);
                          if(pData.extracted_emails && pData.extracted_emails.length > 0) {
                            return <li><strong>Correos:</strong> {pData.extracted_emails.join(', ')}</li>;
                          }
                        } catch(e) {}
                        return null;
                      })()
                    )}
                  </ul>
                </div>
              </div>
              
              {result.imagen_urls && result.imagen_urls !== "[]" && (
                <div className="mt-3">
                  <h4 style={{ color: 'var(--accent)', marginBottom: '10px' }}>Imágenes</h4>
                  <div style={{ display: 'flex', gap: '10px', overflowX: 'auto', paddingBottom: '10px' }}>
                    {(() => {
                      try {
                        const imgs = JSON.parse(result.imagen_urls.replace(/'/g, '"'));
                        return imgs.map((img, i) => <img key={i} src={img} alt="evidencia" style={{ height: '80px', borderRadius: '4px', border: '1px solid #444' }} />);
                      } catch(e) { return null; }
                    })()}
                  </div>
                </div>
              )}

              {result.correlaciones_nlp && result.correlaciones_nlp !== "{}" && (
                <div className="mt-3 p-3" style={{background: 'rgba(255,255,255,0.05)', borderRadius: '8px'}}>
                  <h4 style={{marginBottom: '8px', fontSize: '0.9rem', color: 'var(--accent)'}}>Patrones NLP Detectados</h4>
                  <pre style={{fontSize: '0.8rem', whiteSpace: 'pre-wrap'}}>{JSON.stringify(JSON.parse(result.correlaciones_nlp), null, 2)}</pre>
                </div>
              )}

              <div className="mt-3" style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
                <button 
                  className="btn-secondary" 
                  onClick={handlePromote} 
                  disabled={promoting || promoteSuccess}
                >
                  <FaUserSecret /> {promoting ? 'Promoviendo...' : promoteSuccess ? 'Promovido con éxito' : 'Promover a Sospechoso'}
                </button>
              </div>
              <p className="result-note mt-2">El resultado ha sido guardado en la base de datos bajo la categoría "Manual".</p>
            </div>
          ) : (
            <div className="empty-state">
              <FaSearch className="empty-icon" />
              <p>Los resultados del análisis aparecerán aquí.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
