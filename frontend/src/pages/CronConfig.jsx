import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { getCronConfig, updateCronConfig, toggleCron, triggerManualRun, stopCron } from '../services/cronService';
import { getBrands, toggleProduct } from '../services/brandService';
import api from '../services/api';
import { FaClock, FaPowerOff, FaPlay, FaSave, FaCheckCircle, FaExclamationTriangle, FaStopCircle, FaTags, FaGlobeAmericas, FaToggleOn, FaToggleOff, FaSlidersH, FaBolt, FaTerminal, FaTrashAlt, FaCopy, FaCheck } from 'react-icons/fa';
import './CronConfig.css';

const PLATFORM_OPTIONS = ['tiktok', 'facebook', 'instagram', 'mercadolibre'];
const EXTRACTION_LIMITS = [2, 5, 10, 20, 25, 50, 75, 100];
const PROVEEDOR_OPTIONS = [
  { value: 'google_meli_osint', label: '  Google Serper + MeLi Developers + Certstream (OSINT Avanzado)' },
  { value: 'playwright', label: '  Gratuito / Local (DuckDuckGo OSINT + API ML + Playwright)' },
  { value: 'rapidapi', label: '  RapidAPI — Alternativa (APIs de terceros vía RapidAPI Key)' },
  { value: 'apify', label: '  Apify Cloud (Escaneo de Pago - Alta Precisión)' }
];
const PROVINCIAS_AR = [
  "CABA", "Buenos Aires", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes",
  "Entre Ríos", "Formosa", "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones",
  "Neuquén", "Río Negro", "Salta", "San Juan", "San Luis", "Santa Cruz", "Santa Fe",
  "Santiago del Estero", "Tierra del Fuego", "Tucumán"
];

export default function CronConfig() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hora, setHora] = useState(2);
  const [minuto, setMinuto] = useState(0);
  const [plataformas, setPlataformas] = useState(["mercadolibre", "facebook", "instagram", "tiktok"]);
  const [marcas, setMarcas] = useState([]);
  const [activeBrands, setActiveBrands] = useState([]);
  
  const [scanProvinces, setScanProvinces] = useState(false);
  const [provincias, setProvincias] = useState([]);
  
  const [limiteFB, setLimiteFB] = useState(5);
  const [limiteIG, setLimiteIG] = useState(5);
  const [limiteTT, setLimiteTT] = useState(5);
  const [limiteML, setLimiteML] = useState(5);
  
  const [isActive, setIsActive] = useState(false);
  const [message, setMessage] = useState(null);
  const [logs, setLogs] = useState(["[Sistema] Consola de monitoreo inicializada. Listo para escuchar eventos."]);
  const [cronRunning, setCronRunning] = useState(false);
  const [proveedor, setProveedor] = useState("playwright");
  
  const [modalState, setModalState] = useState({ isOpen: false, type: null, title: null, body: null });
  const [modalCountdown, setModalCountdown] = useState(5);
  const modalTimerRef = React.useRef(null);
  const modalIntervalRef = React.useRef(null);

  const [autoScroll, setAutoScroll] = useState(true);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const terminalLogsRef = React.useRef(null);
  const initialLogsCount = React.useRef(null);
  const wasRunning = React.useRef(null);
  const isFirstMount = React.useRef(true);

  const closeModal = () => {
    if (modalTimerRef.current) clearTimeout(modalTimerRef.current);
    if (modalIntervalRef.current) clearInterval(modalIntervalRef.current);
    setModalState({ isOpen: false, type: null, title: null, body: null });
  };

  const showNoticeModal = ({ title, body, type = 'success' }) => {
    if (modalTimerRef.current) clearTimeout(modalTimerRef.current);
    if (modalIntervalRef.current) clearInterval(modalIntervalRef.current);

    setModalCountdown(5);
    setModalState({ isOpen: true, type, title, body });

    let remaining = 5;
    modalIntervalRef.current = setInterval(() => {
      remaining -= 1;
      setModalCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(modalIntervalRef.current);
      }
    }, 1000);

    modalTimerRef.current = setTimeout(() => {
      closeModal();
    }, 5000);
  };

  // Auto-scroll terminal to bottom on new logs
  useEffect(() => {
    if (autoScroll && terminalLogsRef.current) {
      terminalLogsRef.current.scrollTop = terminalLogsRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);



  useEffect(() => {
    fetchConfig();
    fetchBrands();
    
    let isSubscribed = true;
    let timerId = null;

    const pollStatus = async () => {
      if (!isSubscribed) return;
      let nextInterval = 4000; // 4 segundos en reposo
      
      try {
        const statusRes = await api.get('/api/cron/status').then(r => r.data);
        
        const isCurrentlyRunning = statusRes.is_running;
        setCronRunning(isCurrentlyRunning);
        
        if (isCurrentlyRunning) {
            nextInterval = 1500; // 1.5 segundos durante escaneo activo
        }
        
        if (isFirstMount.current) {
          if (isCurrentlyRunning) {
            setModalState({ isOpen: true, type: 'info', title: 'Escaneo en Curso', body: 'El motor de escaneo está actualmente en ejecución en segundo plano.' });
          }
          isFirstMount.current = false;
        } else {
          if (wasRunning.current === true && !isCurrentlyRunning) {
            setModalState({ isOpen: true, type: 'info', title: 'Escaneo Finalizado', body: 'El ciclo de escaneo automático ha concluido.' });
          }
        }
        wasRunning.current = isCurrentlyRunning;

        if (statusRes.logs && statusRes.logs.length > 0) {
          setLogs(statusRes.logs);
        } else {
          setLogs(["[Sistema] Consola de monitoreo inicializada. Esperando eventos..."]);
        }
      } catch (e) {
        console.error("Error polling status", e);
      }
      
      if (isSubscribed) {
        timerId = setTimeout(pollStatus, nextInterval);
      }
    };
    
    pollStatus();
    
    return () => {
        isSubscribed = false;
        if (timerId) clearTimeout(timerId);
    };
  }, []);

  const fetchBrands = async () => {
    try {
      const res = await getBrands();
      setActiveBrands(res.data || []);
    } catch (e) {
      console.error(e);
    }
  }

  const fetchConfig = async () => {
    try {
      const res = await getCronConfig();
      const data = res.data;
      const isRunning = data.is_running;
      setConfig(data);
      setCronRunning(isRunning);
      
      setHora(data.hora);
      setMinuto(data.minuto);
      setIsActive(data.is_active);
      setPlataformas(JSON.parse(data.plataformas_activas));
      setMarcas(JSON.parse(data.marcas_seleccionadas));
      
      const provs = JSON.parse(data.provincias_seleccionadas || '[]');
      setProvincias(provs);
      setScanProvinces(provs.length > 0);

      setLimiteFB(data.limite_extraccion_fb || 5);
      setLimiteIG(data.limite_extraccion_ig || 5);
      setLimiteTT(data.limite_extraccion_tt || 5);
      setLimiteML(data.limite_extraccion_ml || 5);
      setProveedor(data.proveedor || "apify");
    } catch (error) {
      console.error("Error fetching cron config:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleProveedorChange = (newProv) => {
    setProveedor(newProv);
    if (newProv === 'apify' || newProv === 'rapidapi') {
      setPlataformas(prev => prev.filter(p => p !== 'mercadolibre'));
    } else if (newProv === 'google_meli_osint' || newProv === 'playwright') {
      setPlataformas(prev => prev.includes('mercadolibre') ? prev : [...prev, 'mercadolibre']);
    }
  };

  const handleTogglePlatform = (plat) => {
    if ((proveedor === 'apify' || proveedor === 'rapidapi') && plat === 'mercadolibre') return;
    setPlataformas(prev => 
      prev.includes(plat) ? prev.filter(p => p !== plat) : [...prev, plat]
    );
  };

  const handleToggleMarca = (brandId) => {
    setMarcas(prev => 
      prev.includes(brandId) ? prev.filter(id => id !== brandId) : [...prev, brandId]
    );
  };

  const handleToggleKeyword = async (e, productId) => {
    e.stopPropagation();
    try {
      await toggleProduct(productId);
      fetchBrands();
    } catch (err) {
      console.error('Error toggling keyword:', err);
    }
  };

  const selectAllMarcas = () => {
    const onlyActiveIds = activeBrands
      .filter(b => (b.estado || 'activa').toLowerCase() === 'activa')
      .map(b => b.id);
    setMarcas(onlyActiveIds);
  };

  const deselectAllMarcas = () => {
    setMarcas([]);
  };

  const handleToggleProvincia = (prov) => {
    setProvincias(prev => 
      prev.includes(prov) ? prev.filter(p => p !== prov) : [...prev, prov]
    );
  };
  const selectAllProvincias = () => setProvincias(PROVINCIAS_AR);
  const deselectAllProvincias = () => setProvincias([]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const cleanMarcas = marcas.filter(mId => {
        const found = activeBrands.find(b => b.id === mId);
        return found && (found.estado || 'activa').toLowerCase() === 'activa';
      });

      const payload = {
        hora: Number(hora),
        minuto: Number(minuto),
        plataformas_activas: JSON.stringify(plataformas),
        marcas_seleccionadas: JSON.stringify(cleanMarcas),
        provincias_seleccionadas: JSON.stringify(scanProvinces ? provincias : []),
        limite_extraccion_fb: Number(limiteFB),
        limite_extraccion_ig: Number(limiteIG),
        limite_extraccion_tt: Number(limiteTT),
        limite_extraccion_ml: Number(limiteML),
        proveedor: proveedor
      };
      await updateCronConfig(payload);
      showNoticeModal({
        title: 'Configuración Guardada',
        body: 'La configuración del motor Cron ha sido guardada exitosamente y los horarios se han sincronizado con el servidor.',
        type: 'success'
      });
      await fetchConfig();
    } catch (error) {
      showNoticeModal({
        title: 'Error al Guardar',
        body: 'Ocurrió un error al guardar la configuración en el servidor.',
        type: 'error'
      });
    } finally {
      setSaving(false);
    }
  };

  const handleManualRun = async () => {
    try {
      setLogs(prev => ["[Sistema]   Disparando escaneo forzado inmediato...", ...prev]);
      await triggerManualRun();
      setCronRunning(true);
      showNoticeModal({
        title: 'Escaneo Forzado Iniciado',
        body: 'El escaneo inmediato ha sido disparado en segundo plano y los resultados se están transmitiendo a la consola.',
        type: 'info'
      });
    } catch (error) {
      const errorDetail = error.response?.data?.detail || error.response?.data?.msg || 'Error al disparar el escaneo.';
      showNoticeModal({
        title: 'Error de Ejecución',
        body: errorDetail,
        type: 'error'
      });
    }
  };

  const handleStopCron = async () => {
    try {
      await stopCron();
      setCronRunning(false);
      showNoticeModal({
        title: 'Señal de Detención Enviada',
        body: 'Se envió la orden de interrupción de emergencia al motor de escaneo.',
        type: 'warning'
      });
    } catch (error) {
      showNoticeModal({
        title: 'Error al Detener',
        body: 'No se pudo enviar la señal de detención al motor.',
        type: 'error'
      });
    }
  };

  const handleToggleActive = async () => {
    try {
      const nextState = !isActive;
      setIsActive(nextState);
      const res = await toggleCron(nextState);
      const serverState = res.data.is_active;
      setIsActive(serverState);
      showNoticeModal({
        title: serverState ? 'Motor Encendido' : 'Motor Apagado',
        body: serverState 
          ? 'El motor de escaneo automático ha sido ENCENDIDO. El sistema ejecutará las búsquedas según el horario configurado.' 
          : 'El motor de escaneo automático ha sido APAGADO. No se realizarán escaneos programados hasta que vuelva a activarse.',
        type: serverState ? 'success' : 'warning'
      });
      await fetchConfig();
    } catch (error) {
      setIsActive(prev => !prev);
      showNoticeModal({
        title: 'Error al Cambiar Estado',
        body: 'No se pudo cambiar el estado del motor en el servidor.',
        type: 'error'
      });
    }
  };

  const isEditingDisabled = cronRunning;

  if (loading) return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;

  const renderModal = () => {
    if (!modalState.isOpen) return null;

    let headerColor = 'var(--accent-primary)';
    if (modalState.type === 'error') headerColor = 'var(--danger)';
    else if (modalState.type === 'success') headerColor = '#00E676';
    else if (modalState.type === 'warning') headerColor = '#F59E0B';

    return createPortal(
      <div className="modal-overlay fade-in" onClick={closeModal}>
        <div 
          className="glass-modal slide-up" 
          onClick={(e) => e.stopPropagation()} 
          style={{ maxWidth: '460px', border: `1px solid ${headerColor}`, boxShadow: `0 8px 32px rgba(0,0,0,0.6)` }}
        >
          <div className="modal-header" style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ color: headerColor, display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.15rem', margin: 0 }}>
              {modalState.type === 'success' && <FaCheckCircle color="#00E676" size={18} />}
              {modalState.type === 'warning' && <FaPowerOff color="#F59E0B" size={18} />}
              {modalState.type === 'error' && <FaExclamationTriangle color="var(--danger)" size={18} />}
              {modalState.type === 'info' && <FaPlay color="var(--accent-primary)" size={18} />}
              {modalState.title}
            </h3>
            <button className="btn-close" onClick={closeModal} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: '1.4rem', cursor: 'pointer' }}>&times;</button>
          </div>
          <div className="modal-body" style={{ padding: '18px 0', fontSize: '0.95rem', color: 'var(--text-primary)', lineHeight: '1.5' }}>
            <p style={{ margin: 0 }}>{modalState.body}</p>
          </div>
          <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Cerrando en <strong>{modalCountdown}s</strong>...
            </span>
            <button className="btn-primary" onClick={closeModal} style={{ padding: '6px 18px', minWidth: '90px', fontSize: '0.9rem' }}>
              Aceptar
            </button>
          </div>
        </div>
      </div>,
      document.body
    );
  };

  return (
    <div className="page-container fade-in" style={{ maxWidth: '1600px', margin: '0 auto', position: 'relative' }}>
      {renderModal()}
      <div className="cron-header">
        <h2>Configuración del Motor Cron</h2>
        <p>Administra los horarios, marcas y plataformas para la búsqueda OSINT automatizada.</p>
      </div>

      {message && (
        <div className={`message-banner ${message.type === 'success' ? 'success-message' : 'error-message'} slide-up`}>
          {message.type === 'success' ? <FaCheckCircle /> : <FaExclamationTriangle />} {message.text}
        </div>
      )}

      <div className="cron-grid">
        <div className="glass-card config-panel fade-in">
          <h3><FaTags /> Marcas de Escaneo</h3>
          <div className="brands-selector" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '8px', maxHeight: '160px', overflowY: 'auto', padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', marginBottom: '15px'}}>
            {activeBrands.map(brand => {
              const isBrandActive = (brand.estado || 'activa').toLowerCase() === 'activa';
              const isChecked = isBrandActive && marcas.includes(brand.id);

              return (
                <label 
                  key={brand.id} 
                  className={`brand-toggle ${isChecked ? 'active' : ''}`} 
                  style={{ 
                    margin: 0, 
                    padding: '6px 10px', 
                    fontSize: '0.85rem',
                    opacity: isBrandActive ? 1 : 0.45,
                    cursor: isBrandActive ? 'pointer' : 'not-allowed',
                    borderStyle: isBrandActive ? 'solid' : 'dashed',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '6px'
                  }}
                  title={!isBrandActive ? 'Marca inactiva en el sistema (no seleccionable)' : ''}
                >
                  <input 
                    type="checkbox" 
                    checked={isChecked} 
                    onChange={() => isBrandActive && !isEditingDisabled && handleToggleMarca(brand.id)} 
                    disabled={!isBrandActive || isEditingDisabled} 
                    hidden
                  />
                  <span className="brand-name">{brand.nombre}</span>
                  {!isBrandActive && (
                    <span style={{ fontSize: '0.65rem', background: 'rgba(231,76,60,0.2)', color: 'var(--danger)', padding: '1px 5px', borderRadius: '4px', fontWeight: 600 }}>
                      Inactiva
                    </span>
                  )}
                </label>
              );
            })}
            {activeBrands.length === 0 && <span style={{color: 'var(--text-secondary)'}}>No hay marcas configuradas.</span>}
          </div>
          <div style={{display: 'flex', gap: '10px', marginBottom: '15px'}}>
            <button className="btn-ghost" style={{fontSize: '0.8rem', padding: '4px 10px'}} onClick={selectAllMarcas} disabled={isEditingDisabled}>Seleccionar Todas</button>
            <button className="btn-ghost" style={{fontSize: '0.8rem', padding: '4px 10px'}} onClick={deselectAllMarcas} disabled={isEditingDisabled}>Deseleccionar Todas</button>
          </div>

          <h3><FaGlobeAmericas /> Provincias de Escaneo</h3>
          <div className="brands-selector" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '8px', maxHeight: '150px', overflowY: 'auto', padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', marginBottom: '15px'}}>
            {PROVINCIAS_AR.map(prov => (
              <label key={prov} className={`brand-toggle ${provincias.includes(prov) ? 'active' : ''}`} style={{ margin: 0, padding: '5px', fontSize: '0.85rem' }}>
                <input type="checkbox" checked={provincias.includes(prov)} onChange={() => !isEditingDisabled && handleToggleProvincia(prov)} disabled={isEditingDisabled} hidden/>
                <span className="brand-name">{prov}</span>
              </label>
            ))}
          </div>
          <div style={{display: 'flex', gap: '10px', marginBottom: '10px'}}>
            <button className="btn-ghost" style={{fontSize: '0.8rem', padding: '4px 10px'}} onClick={selectAllProvincias} disabled={isEditingDisabled}>Seleccionar Todas</button>
            <button className="btn-ghost" style={{fontSize: '0.8rem', padding: '4px 10px'}} onClick={deselectAllProvincias} disabled={isEditingDisabled}>Deseleccionar Todas</button>
          </div>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '15px', display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(91, 141, 239, 0.08)', padding: '8px 12px', borderRadius: '6px', border: '1px solid rgba(91, 141, 239, 0.15)' }}>
              Las provincias solo aplican a <strong>Facebook Marketplace</strong>. Instagram, TikTok y MercadoLibre buscan a nivel nacional (Argentina).
          </p>

          <h3><FaClock /> Horario de Ejecución (Hora ARG)</h3>
          <div className="time-selector">
            <div className="input-group"><label>Hora (0-23)</label><input type="number" className="input-field" min="0" max="23" value={hora} onChange={(e) => setHora(e.target.value)} disabled={isEditingDisabled}/></div>
            <span className="time-separator">:</span>
            <div className="input-group"><label>Minuto (0-59)</label><input type="number" className="input-field" min="0" max="59" value={minuto} onChange={(e) => setMinuto(e.target.value)} disabled={isEditingDisabled}/></div>
          </div>
          <h3 className="mt-2"><FaBolt /> Proveedor</h3>
          <select className="input-field w-100" value={proveedor} onChange={(e) => handleProveedorChange(e.target.value)} disabled={isEditingDisabled} style={{ padding: '10px' }}>
            {PROVEEDOR_OPTIONS.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
          </select>
          {proveedor === 'rapidapi' && (
            <p style={{ fontSize: '0.8rem', color: 'var(--warning)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                Requiere <code>RAPIDAPI_KEY</code> configurada en el archivo <code>.env</code> del backend.
            </p>
          )}
          {proveedor === 'google_meli_osint' && (
            <p style={{ fontSize: '0.8rem', color: 'var(--accent-color, #38bdf8)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(56, 189, 248, 0.1)', padding: '8px 12px', borderRadius: '6px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                <strong>Suite OSINT Enterprise</strong>: Google Dorking estructurado (FB, IG, TikTok), API oficial de desarrolladores para Mercado Libre y monitoreo SSL de tiendas falsas (Certstream).
            </p>
          )}
          <h3 className="mt-2"><FaSlidersH /> Plataformas y Límites</h3>
          <div className="platforms-limits-container" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '15px'}}>
            {PLATFORM_OPTIONS.map(plat => {
              const isMLDisabled = plat === 'mercadolibre' && (proveedor === 'apify' || proveedor === 'rapidapi');
              const isChecked = plataformas.includes(plat) && !isMLDisabled;

              return (
                <div key={plat} className={`platform-limit-card ${isChecked ? 'active' : ''}`} style={{display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px', opacity: isMLDisabled ? 0.6 : 1}}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                    <div>
                      <span style={{textTransform: 'capitalize', fontWeight: 'bold'}}>{plat}</span>
                      {isMLDisabled && (
                        <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          (Solo en motor Local)
                        </span>
                      )}
                    </div>
                    <button 
                      className="btn-ghost" 
                      onClick={() => !isEditingDisabled && !isMLDisabled && handleTogglePlatform(plat)} 
                      disabled={isEditingDisabled || isMLDisabled}
                      title={isMLDisabled ? "Mercado Libre solo se ejecuta en el motor Gratuito/Local" : ""}
                    >
                      {isChecked ? <FaToggleOn /> : <FaToggleOff />}
                    </button>
                  </div>
                  {isChecked && (
                    <div className="limit-selector" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <label>Resultados (Max)</label>
                      <select className="input-field-small" value={plat === 'facebook' ? limiteFB : plat === 'instagram' ? limiteIG : plat === 'tiktok' ? limiteTT : limiteML} onChange={(e) => { const val = Number(e.target.value); if (plat === 'facebook') setLimiteFB(val); else if (plat === 'instagram') setLimiteIG(val); else if (plat === 'tiktok') setLimiteTT(val); else setLimiteML(val); }}>
                        {EXTRACTION_LIMITS.map(l => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="config-actions">
            <button 
              type="button"
              className={`btn-power ${isActive ? 'active' : ''}`} 
              onClick={handleToggleActive} 
              disabled={isEditingDisabled}
              title={isActive ? "Haz clic para APAGAR el motor automático" : "Haz clic para ENCENDER el motor automático"}
            >
              <FaPowerOff /> {isActive ? 'Motor Encendido' : 'Motor Apagado'}
            </button>
            <button 
              type="button"
              className="btn-primary" 
              onClick={handleSave} 
              disabled={saving || isEditingDisabled}
            >
              <FaSave /> {saving ? 'Guardando...' : 'Guardar Configuración'}
            </button>
          </div>
        </div>

        <div className="glass-card status-panel">
          <h3>Estado del Motor OSINT</h3>
          <div className="status-indicator"><div className={`status-dot ${cronRunning ? 'pulsing' : (isActive ? 'active' : 'inactive')}`}></div><span>{cronRunning ? 'ESCANEO EN PROGRESO...' : (isActive ? 'EN ESPERA (PROGRAMADO)' : 'APAGADO')}</span></div>
          <div className="danger-zone">
            <h4>Acciones Manuales</h4>
            <button className="btn-secondary w-100" onClick={handleManualRun} disabled={cronRunning}><FaPlay /> Forzar Ejecución Inmediata</button>
            <button className={cronRunning ? "btn-danger w-100" : "btn-ghost w-100"} onClick={handleStopCron} disabled={!cronRunning}><FaStopCircle /> Detener por Emergencia</button>
          </div>
          {/* Cyber-Forensic Terminal Window */}
          <div className="terminal-wrapper mt-2">
            <div className="terminal-window-header">
              <div className="terminal-dots">
                <span className="terminal-dot dot-red"></span>
                <span className="terminal-dot dot-yellow"></span>
                <span className="terminal-dot dot-green"></span>
              </div>
              <div className="terminal-window-title">
                <FaTerminal size={11} style={{ marginRight: '6px', color: '#5B8DEF' }} />
                <span>OSINT LIVE CONSOLE</span>
                {cronRunning && <span className="terminal-live-badge">SCANNING</span>}
              </div>
              <div className="terminal-controls">
                <button
                  type="button"
                  className="terminal-ctrl-btn"
                  onClick={() => setAutoScroll(prev => !prev)}
                  title={autoScroll ? "Auto-scroll Activado" : "Auto-scroll Pausado"}
                  style={{ color: autoScroll ? '#2ECC71' : 'rgba(255,255,255,0.4)' }}
                >
                  ↓ Auto
                </button>
                <button
                  type="button"
                  className="terminal-ctrl-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(logs.join('\n'));
                    setCopiedLogs(true);
                    setTimeout(() => setCopiedLogs(false), 2000);
                  }}
                  title="Copiar logs"
                >
                  {copiedLogs ? <FaCheck style={{ color: '#2ECC71' }} /> : <FaCopy />}
                </button>
                <button
                  type="button"
                  className="terminal-ctrl-btn"
                  onClick={() => setLogs(["[Sistema] Consola limpiada por el analista."])}
                  title="Limpiar consola"
                >
                  <FaTrashAlt />
                </button>
              </div>
            </div>

            <div ref={terminalLogsRef} className="terminal-console-body">
              {logs.map((log, i) => {
                let logType = "log-normal";
                if (log.includes(" ") || log.includes("Éxito") || log.includes("guardada con éxito")) logType = "log-success";
                else if (log.includes(" ") || log.includes("Warning") || log.includes("Aviso")) logType = "log-warning";
                else if (log.includes(" ") || log.includes("Error") || log.includes("Fallo")) logType = "log-danger";
                else if (log.includes(" ") || log.includes("Serper") || log.includes("OSINT")) logType = "log-osint";
                else if (log.includes(" ") || log.includes("Screenshot")) logType = "log-photo";
                else if (log.includes("======") || log.includes("---")) logType = "log-divider";

                const matchTime = log.match(/^(\[\d{2}:\d{2}:\d{2}\])\s*(.*)$/);
                if (matchTime) {
                  return (
                    <div key={i} className={`terminal-log-row ${logType}`}>
                      <span className="log-time-chip">{matchTime[1]}</span>
                      <span className="log-content-span">{matchTime[2]}</span>
                    </div>
                  );
                }

                return (
                  <div key={i} className={`terminal-log-row ${logType}`}>
                    <span className="log-content-span">{log}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
