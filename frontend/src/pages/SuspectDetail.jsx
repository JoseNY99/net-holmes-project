import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getSuspectDetail, updateSuspect, quickEditSuspect, getPerfil, updatePerfil, getAuditLogs, exportPdf, exportWord, exportCbnPdf, captureScreenshot } from '../services/suspectService';
import correlationService from '../services/correlationService';
import chatService from '../services/chatService';
import { FaArrowLeft, FaBoxOpen, FaSave, FaCheckCircle, FaExclamationTriangle, FaHistory, FaLock, FaUnlock, FaNetworkWired, FaFilePdf, FaFileWord, FaCommentDots, FaRobot, FaUserEdit, FaPaperPlane, FaWhatsapp, FaBrain, FaLink, FaCamera, FaEdit, FaTimes } from 'react-icons/fa';
import { useAuth } from '../context/AuthContext';
import './SuspectDetail.css';

const COMPLETION_FIELDS = [
  'dni_cedula', 'cuit_cuil_ruc', 'banco', 'alias_bancario', 'cvu_cbu',
  'email', 'direccion_exacta', 'telefono_privado', 'precio_final_cotizado'
];

const COMPLETION_FIELD_LABELS = {
  dni_cedula: 'DNI / cédula',
  cuit_cuil_ruc: 'CUIT / CUIL / RUC',
  banco: 'Banco / billetera',
  alias_bancario: 'Alias bancario',
  cvu_cbu: 'CVU / CBU',
  email: 'Correo electrónico',
  direccion_exacta: 'Dirección exacta',
  telefono_privado: 'Teléfono privado',
  precio_final_cotizado: 'Precio final cotizado'
};

const getCompletionSummary = (profile) => {
  const completedFields = COMPLETION_FIELDS.filter(field => String(profile[field] || '').trim());
  return {
    completedCount: completedFields.length,
    requiredCount: Math.ceil(COMPLETION_FIELDS.length * 0.8),
    percentage: Number((completedFields.length * 100 / COMPLETION_FIELDS.length).toFixed(2)),
    missingFields: COMPLETION_FIELDS.filter(field => !String(profile[field] || '').trim())
  };
};

const getApiErrorMessage = async (error, fallback) => {
  const responseData = error.response?.data;
  if (responseData instanceof Blob) {
    try {
      const parsed = JSON.parse(await responseData.text());
      return parsed.detail || fallback;
    } catch {
      return fallback;
    }
  }
  return responseData?.detail || fallback;
};

export default function SuspectDetail() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  
  // Fase 1 State
  const [reporte, setReporte] = useState(null);
  const [estado, setEstado] = useState('');
  const [loading, setLoading] = useState(true);

  // Edición Manual Fase 1 (Precio, Moneda, Teléfono, Dirección)
  const [isEditingFase1, setIsEditingFase1] = useState(false);
  const [fase1Form, setFase1Form] = useState({
    precio_publico: '',
    moneda: 'ARS',
    telefono_publico: '',
    direccion_publica: '',
    titular_cuenta: ''
  });
  const [savingFase1, setSavingFase1] = useState(false);
  
  // Fase 2 State (ABM)
  const [perfil, setPerfil] = useState({
    dni_cedula: '',
    cuit_cuil_ruc: '',
    banco: '',
    alias_bancario: '',
    cvu_cbu: '',
    email: '',
    direccion_exacta: '',
    telefono_privado: '',
    precio_final_cotizado: ''
  });
  const [auditLogs, setAuditLogs] = useState([]);
  const [savingPerfil, setSavingPerfil] = useState(false);
  const [message, setMessage] = useState(null);
  
  // Correlations State
  const [correlations, setCorrelations] = useState([]);

  // Export State
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingWord, setExportingWord] = useState(false);
  const [exportingCbnPdf, setExportingCbnPdf] = useState(false);
  const [capturingScreenshot, setCapturingScreenshot] = useState(false);
  const [screenshotTimestamp, setScreenshotTimestamp] = useState(Date.now());

  // Chat State
  const [activeTab, setActiveTab] = useState('abm');
  const [conversation, setConversation] = useState(null);
  const [chatInput, setChatInput] = useState('');
  const [sendingChat, setSendingChat] = useState(false);
  const chatEndRef = useRef(null);
  const [waPhone, setWaPhone] = useState('');
  const [linkingWa, setLinkingWa] = useState(false);

  useEffect(() => {
    fetchData();
  }, [id]);

  // Auto-refresh del chat cada 5 segundos cuando el tab está activo
  useEffect(() => {
    if (activeTab !== 'chat' || (estado !== 'Sospechoso' && estado !== 'Investigando')) return;
    const interval = setInterval(async () => {
      try {
        const chatRes = await chatService.getConversation(id);
        setConversation(chatRes.data);
      } catch (e) { /* silent */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTab, id, estado]);

  // Auto-scroll al último mensaje
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [conversation?.messages?.length]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getSuspectDetail(id);
      setReporte(res.data);
      setEstado(res.data.estado);
      
      if (res.data.estado === 'Sospechoso' || res.data.estado === 'Investigando') {
        fetchPerfilData();
      }
      
      // Fetch correlations
      try {
        const links = await correlationService.getLinksForReporte(id);
        setCorrelations(links);
      } catch(e) {
        console.error("Error fetching correlations", e);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPerfilData = async () => {
    try {
      const perfilRes = await getPerfil(id);
      if (perfilRes.data) {
        setPerfil(prev => ({ ...prev, ...perfilRes.data }));
      }
      const auditRes = await getAuditLogs(id);
      setAuditLogs(auditRes.data);
      
      const chatRes = await chatService.getConversation(id);
      setConversation(chatRes.data);
    } catch (error) {
      console.error("Error fetching perfil/audit/chat", error);
    }
  };

  const openEditFase1 = () => {
    if (!reporte) return;
    setFase1Form({
      precio_publico: reporte.precio_publico !== null && reporte.precio_publico !== undefined ? reporte.precio_publico : '',
      moneda: reporte.moneda || 'ARS',
      telefono_publico: reporte.telefono_publico || '',
      direccion_publica: reporte.direccion_publica || '',
      titular_cuenta: reporte.titular_cuenta || ''
    });
    setIsEditingFase1(true);
  };

  const handleSaveFase1 = async (e) => {
    e.preventDefault();
    setSavingFase1(true);
    try {
      const payload = {
        precio_publico: fase1Form.precio_publico !== '' && !isNaN(parseFloat(fase1Form.precio_publico)) ? parseFloat(fase1Form.precio_publico) : null,
        moneda: fase1Form.moneda || 'ARS',
        telefono_publico: fase1Form.telefono_publico.trim() || null,
        direccion_publica: fase1Form.direccion_publica.trim() || null,
        titular_cuenta: fase1Form.titular_cuenta.trim() || undefined
      };
      const res = await quickEditSuspect(id, payload);
      setReporte(prev => ({ ...prev, ...res.data }));
      setIsEditingFase1(false);
      setMessage({ type: 'success', text: 'Datos de Fase 1 (Precio, Moneda, Teléfono, Calle) actualizados correctamente.' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Error al actualizar los datos de Fase 1.' });
    } finally {
      setSavingFase1(false);
    }
  };

  const toggleChatMode = async () => {
    if (!conversation) return;
    try {
      const newMode = conversation.is_bot_active ? 'analista' : 'bot';
      const res = await chatService.toggleMode(id, newMode);
      setConversation(prev => ({ ...prev, is_bot_active: res.data.is_bot_active, mode: res.data.mode }));
      setMessage({ type: 'success', text: `Modo cambiado a ${newMode.toUpperCase()}` });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Error cambiando el modo del chat.' });
    }
  };

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || sendingChat) return;
    setSendingChat(true);
    try {
      await chatService.sendMessage(id, chatInput.trim());
      setChatInput('');
      // Refrescar mensajes inmediatamente
      const chatRes = await chatService.getConversation(id);
      setConversation(chatRes.data);
    } catch (error) {
      setMessage({ type: 'error', text: 'Error al enviar mensaje.' });
    } finally {
      setSendingChat(false);
    }
  };

  const handleLinkWhatsApp = async () => {
    if (!waPhone.trim() || linkingWa) return;
    setLinkingWa(true);
    try {
      await chatService.linkWhatsApp(id, waPhone.trim());
      setConversation(prev => ({ ...prev, whatsapp_phone: waPhone.trim() }));
      setMessage({ type: 'success', text: `WhatsApp ${waPhone} vinculado correctamente.` });
      setWaPhone('');
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Error al vincular WhatsApp.' });
    } finally {
      setLinkingWa(false);
    }
  };

  const parseEntities = (entitiesStr) => {
    if (!entitiesStr) return null;
    try { return JSON.parse(entitiesStr); } catch { return null; }
  };

  const ENTITY_LABELS = {
    dni_cedula: 'DNI',
    cuit_cuil_ruc: 'CUIT',
    cvu_cbu: 'CBU/CVU',
    alias_bancario: 'Alias',
    email: 'Email',
    telefono_privado: 'Teléfono',
    direccion_exacta: 'Dirección',
    precio_final_cotizado: 'Precio',
    banco: 'Banco',
    nombre_real: 'Nombre',
  };

  const [showStatusModal, setShowStatusModal] = useState(false);
  const [pendingEstado, setPendingEstado] = useState('');

  const confirmStatusChange = (e) => {
    const newEstado = e.target.value;
    if (newEstado !== estado) {
      setPendingEstado(newEstado);
      setShowStatusModal(true);
    }
  };

  const executeUpdateStatus = async () => {
    setEstado(pendingEstado);
    setShowStatusModal(false);
    try {
      await updateSuspect(id, { estado: pendingEstado });
      setMessage({ type: 'success', text: `Estado actualizado a ${pendingEstado}.` });
      setTimeout(() => setMessage(null), 3000);
      
      if (pendingEstado === 'Sospechoso' || pendingEstado === 'Investigando') {
        fetchPerfilData();
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Error al actualizar el estado.' });
    }
  };

  const handleSavePerfil = async (e) => {
    e.preventDefault();
    setSavingPerfil(true);
    const thresholdAlreadyReached = getCompletionSummary(perfil).percentage >= 80;
    try {
      const res = await updatePerfil(id, perfil);
      const savedProfile = { ...perfil, ...res.data };
      setPerfil(savedProfile);
      const auditRes = await getAuditLogs(id);
      setAuditLogs(auditRes.data);
      const completionPercentage = getCompletionSummary(savedProfile).percentage;
      setMessage({
        type: 'success',
        text: completionPercentage >= 80 && !thresholdAlreadyReached
          ? `Alerta: relevamiento al ${completionPercentage}%. El informe final está habilitado.`
          : 'Perfil ABM actualizado correctamente.'
      });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Error al actualizar el perfil ABM.' });
    } finally {
      setSavingPerfil(false);
    }
  };

  const handleExportCbnPdf = async () => {
    setExportingCbnPdf(true);
    try {
      const res = await exportCbnPdf(id);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `CBN_Reporte_Investigacion_${reporte.referencia_interna}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      setMessage({ type: 'error', text: await getApiErrorMessage(e, 'No se pudo generar el informe final.') });
    } finally {
      setExportingCbnPdf(false);
    }
  };

  const handleExportFinalFormat = async (format) => {
    const setExporting = format === 'word' ? setExportingWord : setExportingPdf;
    setExporting(true);
    try {
      const response = format === 'word' ? await exportWord(id) : await exportPdf(id);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `Reporte_Investigacion_${reporte.referencia_interna}.${format === 'word' ? 'docx' : 'pdf'}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setMessage({
        type: 'error',
        text: await getApiErrorMessage(error, `No se pudo generar el informe en ${format === 'word' ? 'Word' : 'PDF'}.`)
      });
    } finally {
      setExporting(false);
    }
  };

  const handleCaptureScreenshot = async () => {
    setCapturingScreenshot(true);
    try {
      const res = await captureScreenshot(id);
      setScreenshotTimestamp(Date.now());
      await fetchData();
      setMessage({ type: 'success', text: '¡Captura de pantalla en vivo tomada y guardada con éxito!' });
    } catch (e) {
      setMessage({ type: 'error', text: 'No se pudo capturar la pantalla del post en vivo en este momento.' });
    } finally {
      setCapturingScreenshot(false);
    }
  };

  if (loading) return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;
  if (!reporte) return <div className="page-container"><h2>Reporte no encontrado</h2></div>;

  const abmUnlocked = estado === 'Sospechoso' || estado === 'Investigando';
  const completionSummary = getCompletionSummary(perfil);
  const investigacionCompleta = abmUnlocked && completionSummary.percentage >= 80;
  const remainingRequiredFields = Math.max(0, completionSummary.requiredCount - completionSummary.completedCount);

  return (
    <div className="page-container fade-in">
      <div className="detail-header" style={{ marginBottom: '1rem' }}>
        <Link to="/investigation" className="btn-ghost back-btn"><FaArrowLeft /> Volver al Triage</Link>
        <div className="detail-title-row" style={{ marginTop: '1rem' }}>
          <div className="title-left">
            <div className="avatar-large"><FaBoxOpen /></div>
            <div>
              <h2>Ticket #{reporte.referencia_interna.substring(0,8).toUpperCase()}</h2>
              <p className="text-secondary">{reporte.marca_afectada} - {reporte.plataforma}</p>
            </div>
          </div>
          <div className="title-right">
            <select 
              className="input-field" 
              value={estado} 
              onChange={confirmStatusChange}
              style={{ background: (estado === 'Sospechoso' || estado === 'Investigando') ? 'rgba(231, 76, 60, 0.2)' : 'var(--glass-bg)', borderColor: (estado === 'Sospechoso' || estado === 'Investigando') ? 'var(--danger)' : 'var(--border-color)', transition: 'all 0.3s ease' }}
            >
              <option value="Pendiente">Pendiente (Triage)</option>
              <option value="Investigando" disabled={estado !== 'Investigando'}>Investigando (Automático)</option>
              <option value="Sospechoso" disabled={estado !== 'Sospechoso'}>Sospechoso (Automático)</option>
              <option value="Descartado">Descartado</option>
            </select>
          </div>
        </div>
      </div>

      {message && (
        <div className={`message-banner ${message.type === 'success' ? 'success-message' : 'error-message'} slide-up`} style={{ marginBottom: '1rem' }}>
          {message.type === 'success' ? <FaCheckCircle /> : <FaExclamationTriangle />} {message.text}
        </div>
      )}

      <div className="detail-grid split-view">
        {/* COLUMNA IZQUIERDA: FASE 1 DE LA INVESTIGACION */}
        <div className="glass-card detail-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '10px', marginBottom: '15px' }}>
            <h3 style={{ margin: 0 }}>Fase 1 de la investigación</h3>
            {!isEditingFase1 && (
              <button 
                type="button" 
                className="btn-secondary btn-sm"
                onClick={openEditFase1}
                style={{ fontSize: '0.8rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                title="Editar precio, moneda, teléfono o calle sin necesidad de cambiar de fase"
              >
                <FaEdit /> Editar Datos
              </button>
            )}
          </div>

          {isEditingFase1 ? (
            <form onSubmit={handleSaveFase1} className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '15px' }}>
              <div>
                <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Titular / Vendedor</label>
                <input 
                  type="text" 
                  className="input-field"
                  value={fase1Form.titular_cuenta}
                  onChange={(e) => setFase1Form(prev => ({ ...prev, titular_cuenta: e.target.value }))}
                  placeholder="Nombre de la cuenta o vendedor"
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Precio Detectado</label>
                  <input 
                    type="number" 
                    step="any"
                    className="input-field"
                    value={fase1Form.precio_publico}
                    onChange={(e) => setFase1Form(prev => ({ ...prev, precio_publico: e.target.value }))}
                    placeholder="Ej: 45000"
                    style={{ width: '100%' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Moneda</label>
                  <select 
                    className="input-field"
                    value={fase1Form.moneda}
                    onChange={(e) => setFase1Form(prev => ({ ...prev, moneda: e.target.value }))}
                    style={{ width: '100%' }}
                  >
                    <option value="ARS">ARS ($)</option>
                    <option value="USD">USD (US$)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="BRL">BRL (R$)</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Teléfono Público / WhatsApp</label>
                <input 
                  type="text" 
                  className="input-field"
                  value={fase1Form.telefono_publico}
                  onChange={(e) => setFase1Form(prev => ({ ...prev, telefono_publico: e.target.value }))}
                  placeholder="Ej: +54 9 11 1234-5678"
                  style={{ width: '100%' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Dirección / Calle Pública</label>
                <input 
                  type="text" 
                  className="input-field"
                  value={fase1Form.direccion_publica}
                  onChange={(e) => setFase1Form(prev => ({ ...prev, direccion_publica: e.target.value }))}
                  placeholder="Ej: Av. Corrientes 1234, CABA"
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '6px' }}>
                <button 
                  type="button" 
                  className="btn-ghost btn-sm" 
                  onClick={() => setIsEditingFase1(false)}
                  style={{ padding: '6px 12px' }}
                >
                  <FaTimes /> Cancelar
                </button>
                <button 
                  type="submit" 
                  className="btn-primary btn-sm" 
                  disabled={savingFase1}
                  style={{ padding: '6px 14px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <FaSave /> {savingFase1 ? 'Guardando...' : 'Guardar Cambios'}
                </button>
              </div>
            </form>
          ) : (
            <ul className="info-list read-only-list">
              <li><strong>País Origen:</strong> {reporte.pais}</li>
              <li><strong>Catálogo Afectado:</strong> {reporte.producto_catalogo}</li>
              <li><strong>Titular de Cuenta:</strong> {reporte.titular_cuenta}</li>
              <li><strong>Seguidores (Aprox):</strong> {reporte.seguidores_infractor !== null && reporte.seguidores_infractor !== undefined ? reporte.seguidores_infractor.toLocaleString() : 'No detectado'}</li>
              <li>
                <strong>Precio Público:</strong>{' '}
                {reporte.precio_publico !== null && reporte.precio_publico !== undefined
                  ? `${reporte.moneda || 'ARS'} $${Number(reporte.precio_publico).toLocaleString()}`
                  : 'No detectado'}
              </li>
              <li><strong>Teléfono Público:</strong> {reporte.telefono_publico || 'No detectado'}</li>
              <li><strong>Dirección Pública:</strong> {reporte.direccion_publica || 'No detectada'}</li>
              <li><strong>Fecha Captura:</strong> {new Date(reporte.fecha_captura).toLocaleString('es-AR')}</li>
            </ul>
          )}

          <div style={{ marginTop: '20px' }}>
            <strong>URL Evidencia:</strong><br/>
            <a href={reporte.url_evidencia} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-primary)', wordBreak: 'break-all' }}>
              {reporte.url_evidencia}
            </a>
          </div>

          {/* Evidencia Fotográfica / Captura de Pantalla del Post */}
          <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '15px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <strong style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                Captura de Pantalla / Evidencia
              </strong>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleCaptureScreenshot}
                disabled={capturingScreenshot || !reporte.url_evidencia}
                style={{ fontSize: '0.78rem', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: capturingScreenshot ? 'not-allowed' : 'pointer' }}
                title="Toma una captura de pantalla real del post con Playwright"
              >
                <FaCamera /> {capturingScreenshot ? 'Capturando...' : 'Capturar Pantalla en Vivo'}
              </button>
            </div>

            {(() => {
              // 1. Extraer imagen verificada del backend o de platform_data
              let imgUrl = reporte.evidence_image_url || null;

              if (!imgUrl && reporte.platform_data) {
                const pd = reporte.platform_data;
                const platKey = (reporte.plataforma || '').toLowerCase();
                const platData = pd[platKey] || pd.facebook || pd.instagram || pd.tiktok || pd.mercadolibre;
                if (platData && platData.image_urls) {
                  try {
                    const parsed = typeof platData.image_urls === 'string' ? JSON.parse(platData.image_urls) : platData.image_urls;
                    if (Array.isArray(parsed) && parsed.length > 0 && parsed[0]) imgUrl = parsed[0];
                    else if (typeof parsed === 'string' && parsed) imgUrl = parsed;
                  } catch {
                    imgUrl = platData.image_urls;
                  }
                }
              }

              if (imgUrl && typeof imgUrl === 'string' && imgUrl.startsWith('/static')) {
                imgUrl = `${imgUrl}?t=${screenshotTimestamp}`;
              }

              return imgUrl ? (
                <div style={{ position: 'relative', borderRadius: '10px', overflow: 'hidden', border: '1px solid var(--border-color)', background: 'rgba(0,0,0,0.3)', textAlign: 'center', minHeight: '180px', maxHeight: '380px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <img
                    key={`${reporte.id}-${screenshotTimestamp}`}
                    src={imgUrl}
                    alt="Evidencia del sospechoso"
                    style={{ maxWidth: '100%', maxHeight: '380px', objectFit: 'contain', display: 'block', margin: '0 auto' }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      const fallbackEl = document.getElementById(`fallback-no-img-${reporte.id}`);
                      if (fallbackEl) fallbackEl.style.display = 'block';
                    }}
                  />
                  <div
                    id={`fallback-no-img-${reporte.id}`}
                    style={{ display: 'none', padding: '25px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}
                  >
                    <p style={{ margin: '0 0 6px 0' }}>La imagen externa no está disponible o expiró.</p>
                    <small>Haz clic en "Capturar Pantalla en Vivo" para generar una captura con Playwright.</small>
                  </div>
                  <a
                    href={imgUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ position: 'absolute', bottom: '8px', right: '8px', background: 'rgba(0,0,0,0.7)', color: 'white', padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', textDecoration: 'none' }}
                  >
                    Ver original
                  </a>
                </div>
              ) : (
                <div style={{ borderRadius: '10px', border: '1px dashed var(--border-color)', background: 'rgba(0,0,0,0.2)', textAlign: 'center', padding: '32px 20px', color: 'var(--text-secondary)' }}>
                  <FaCamera style={{ fontSize: '2.2rem', opacity: 0.3, marginBottom: '10px' }} />
                  <p style={{ margin: '0 0 6px 0', fontWeight: '500', color: 'var(--text-primary)' }}>Sin captura visual guardada aún</p>
                  <p style={{ margin: '0 0 14px 0', fontSize: '0.82rem', opacity: 0.8 }}>
                    Esta publicación fue indexada sin imagen previa. Puedes capturarla directamente del enlace en vivo.
                  </p>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleCaptureScreenshot}
                    disabled={capturingScreenshot || !reporte.url_evidencia}
                    style={{ fontSize: '0.82rem', padding: '8px 18px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    <FaCamera /> {capturingScreenshot ? 'Capturando con Playwright...' : 'Capturar Pantalla en Vivo'}
                  </button>
                </div>
              );
            })()}
          </div>

          <div style={{ marginTop: '20px' }}>
            <strong>Descripción del Post:</strong>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '15px', borderRadius: '8px', marginTop: '5px', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>
              {reporte.descripcion_post || 'Sin descripción'}
            </div>
          </div>

          {/* Platform Specific Data - Smart Entity & Metadata Badges */}
          {(() => {
            const desc = reporte.descripcion_post || '';
            const mentions = Array.from(new Set(Array.from(desc.matchAll(/@([a-zA-Z0-9._]+)/g)).map(m => `@${m[1]}`)));
            const hashtags = Array.from(new Set(Array.from(desc.matchAll(/#([a-zA-Z0-9._]+)/g)).map(h => `#${h[1]}`)));

            // Extraer métricas reales no nulas
            let metrics = [];
            if (reporte.platform_data) {
              const pd = reporte.platform_data;
              const platKey = (reporte.plataforma || '').toLowerCase();
              const pData = pd[platKey] || {};
              
              if (pData.views || pData.video_views) metrics.push({ label: 'Vistas', value: pData.views || pData.video_views });
              if (pData.likes) metrics.push({ label: 'Likes', value: pData.likes });
              if (pData.shares) metrics.push({ label: 'Compartidos', value: pData.shares });
              if (pData.comments_count) metrics.push({ label: 'Comentarios', value: pData.comments_count });
              if (pData.followers) metrics.push({ label: 'Seguidores', value: pData.followers });
            }

            const hasEntities = mentions.length > 0 || hashtags.length > 0 || metrics.length > 0;
            if (!hasEntities) return null;

            return (
              <div style={{ marginTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '15px' }}>
                <h4 style={{ color: 'var(--accent-primary)', marginBottom: '12px', fontSize: '0.95rem' }}>
                  Metadatos y Cuentas Relacionadas
                </h4>
                
                {mentions.length > 0 && (
                  <div style={{ marginBottom: '10px' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Cuentas / Perfiles Mencionados:</span>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {mentions.map((m, idx) => (
                        <span key={idx} style={{ background: 'rgba(52, 152, 219, 0.15)', color: '#3498db', border: '1px solid rgba(52, 152, 219, 0.3)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.8rem', fontWeight: 600 }}>
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {hashtags.length > 0 && (
                  <div style={{ marginBottom: '10px' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Hashtags Detectados:</span>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {hashtags.map((h, idx) => (
                        <span key={idx} style={{ background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', border: '1px solid rgba(255, 255, 255, 0.1)', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>
                          {h}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {metrics.length > 0 && (
                  <div style={{ display: 'flex', gap: '15px', marginTop: '10px' }}>
                    {metrics.map((m, idx) => (
                      <div key={idx} style={{ background: 'rgba(0,0,0,0.25)', padding: '6px 12px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>{m.label}</span>
                        <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>{m.value}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
          
          {/* Correlations Data - Visualización Mejorada (5 Dimensiones) */}
          <div style={{ marginTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '15px' }}>
            <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)', marginBottom: '10px' }}>
              <FaNetworkWired /> Dimensiones de Correlación ({correlations.length})
            </h4>
            {correlations.length > 0 ? (
              <div className="audit-list">
                {correlations.map(link => {
                  let badgeColor = 'var(--text-secondary)';
                  if (link.tipo_correlacion === 'identificador') badgeColor = '#E74C3C'; // Rojo (Directo)
                  else if (link.tipo_correlacion === 'grafo_social') badgeColor = '#9B59B6'; // Morado (Red)
                  else if (link.tipo_correlacion === 'linguistico') badgeColor = '#F39C12'; // Naranja (Estilo)
                  else if (link.tipo_correlacion === 'contenido') badgeColor = '#3498DB'; // Azul (Visual)
                  else if (link.tipo_correlacion === 'temporal') badgeColor = '#2ECC71'; // Verde (Tiempo)
                  
                  return (
                    <div key={link.id} style={{ background: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px', marginBottom: '10px', fontSize: '0.85rem', borderLeft: `4px solid ${badgeColor}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <strong style={{ color: badgeColor, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          {link.tipo_correlacion.replace('_', ' ')}
                        </strong>
                        <span className="badge" style={{ background: link.score >= 0.8 ? 'var(--danger)' : 'var(--warning)', color: '#000', fontWeight: 'bold' }}>
                          Score: {(link.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>
                        <span style={{color: '#fff'}}>Subtipo:</span> {link.subtipo}
                      </div>
                      <div style={{ color: 'var(--text-secondary)' }}>
                        <span style={{color: '#fff'}}>Vínculo Fuerte con:</span> Reporte #{link.reporte_a_id === parseInt(id) ? link.reporte_b_id : link.reporte_a_id}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '15px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>Sin cruces detectados en las 5 dimensiones.</p>
              </div>
            )}
            <Link to="/correlations" className="btn-primary w-100" style={{ marginTop: '15px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', fontSize: '0.9rem' }}>
              <FaNetworkWired /> Analizar Grafo Espacial
            </Link>
          </div>
        </div>

        {/* COLUMNA DERECHA: FASE 2 DE RELEVAMIENTO */}
        <div className="glass-card notes-panel" style={{ position: 'relative' }}>
          {!abmUnlocked && (
            <div className="lock-overlay" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(10, 15, 30, 0.85)', backdropFilter: 'blur(4px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 10, borderRadius: '16px', padding: '20px' }}>
              <FaLock size={40} style={{ color: 'rgba(255,255,255,0.3)', marginBottom: '12px' }} />
              <h3 style={{ color: 'rgba(255,255,255,0.85)', fontSize: '1.2rem', marginBottom: '6px' }}>Fase 2 de Relevamiento Bloqueada</h3>
              <p style={{ textAlign: 'center', maxWidth: '85%', color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
                El relevamiento se inicia automáticamente para los hallazgos elegibles. Este caso todavía no está disponible para la Fase 2.
              </p>
            </div>
          )}
          
          <div className="tabs-header">
            <button 
              className={`tab-btn ${activeTab === 'abm' ? 'active' : ''}`} 
              onClick={() => setActiveTab('abm')}
              disabled={!abmUnlocked}
            >
              <FaUserEdit /> Fase 2 de relevamiento
            </button>
            <button 
              className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`} 
              onClick={() => setActiveTab('chat')}
              disabled={!abmUnlocked}
            >
              <FaCommentDots /> Chat Center
            </button>
          </div>
          
          {activeTab === 'abm' && (
            <>
              <section aria-label="Progreso del relevamiento" style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '6px' }}>
                  <strong>Progreso del relevamiento</strong>
                  <span>{completionSummary.percentage}% ({completionSummary.completedCount}/{COMPLETION_FIELDS.length})</span>
                </div>
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={completionSummary.percentage}
                  aria-valuetext={`${completionSummary.percentage}% completado`}
                  style={{ height: '8px', background: 'rgba(255,255,255,0.12)', borderRadius: '4px', overflow: 'hidden' }}
                >
                  <div style={{ width: `${completionSummary.percentage}%`, height: '100%', background: 'var(--accent-primary)', transition: 'width 0.25s ease' }} />
                </div>
                <small style={{ color: investigacionCompleta ? 'var(--accent-primary)' : 'var(--text-secondary)' }}>
                  {investigacionCompleta
                    ? 'Umbral mínimo del 80% alcanzado.'
                    : `Para generar el informe necesitas ${completionSummary.requiredCount} de ${COMPLETION_FIELDS.length} datos. Completa ${remainingRequiredFields} más.`}
                </small>
                {!investigacionCompleta && completionSummary.missingFields.length > 0 && (
                  <small style={{ display: 'block', marginTop: '4px', color: 'var(--text-secondary)' }}>
                    Pendientes: {completionSummary.missingFields.map(field => COMPLETION_FIELD_LABELS[field]).join(', ')}.
                    Puedes completar cualquier {remainingRequiredFields} de ellos.
                  </small>
                )}
              </section>
              <form className="abm-form" onSubmit={handleSavePerfil}>
                <div className="form-section abm-card">
              <h4>Identidad y Fiscalidad</h4>
              <div className="form-group">
                <label>DNI / Cédula <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="text" className="input-field" value={perfil.dni_cedula || ''} onChange={e => setPerfil({...perfil, dni_cedula: e.target.value})} placeholder="Ej: 35.123.456" disabled={!abmUnlocked} />
              </div>
              <div className="form-group">
                <label>CUIT / CUIL / RUC <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="text" className="input-field" value={perfil.cuit_cuil_ruc || ''} onChange={e => setPerfil({...perfil, cuit_cuil_ruc: e.target.value})} placeholder="Ej: 20-35123456-7" disabled={!abmUnlocked} />
              </div>
            </div>

            <div className="form-section abm-card">
              <h4>Trazabilidad Financiera</h4>
              <div className="form-group">
                <label>Alias Bancario <span style={{ color: 'var(--accent-primary)', fontWeight: 600, fontSize: '0.8rem' }}>* Clave de Cobro</span></label>
                <input type="text" className="input-field" value={perfil.alias_bancario || ''} onChange={e => setPerfil({...perfil, alias_bancario: e.target.value})} placeholder="Ej: zapatillas.fake.mp" disabled={!abmUnlocked} />
              </div>
              <div className="form-group">
                <label>Banco / Billetera <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="text" className="input-field" value={perfil.banco || ''} onChange={e => setPerfil({...perfil, banco: e.target.value})} placeholder="Ej: MercadoPago / Ualá" disabled={!abmUnlocked} />
              </div>
              <div className="form-group">
                <label>CVU / CBU <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="text" className="input-field" value={perfil.cvu_cbu || ''} onChange={e => setPerfil({...perfil, cvu_cbu: e.target.value})} placeholder="22 dígitos" disabled={!abmUnlocked} />
              </div>
            </div>

            <div className="form-section abm-card">
              <h4>Contacto Privado y Cierre</h4>
              <div className="form-group">
                <label>Teléfono Privado / WhatsApp <span style={{ color: 'var(--accent-primary)', fontWeight: 600, fontSize: '0.8rem' }}>* Contacto Directo</span></label>
                <input type="text" className="input-field" value={perfil.telefono_privado || ''} onChange={e => setPerfil({...perfil, telefono_privado: e.target.value})} placeholder="+54 9 11 1234-5678" disabled={!abmUnlocked} />
              </div>
              <div className="form-group">
                <label>Email Privado <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="email" className="input-field" value={perfil.email || ''} onChange={e => setPerfil({...perfil, email: e.target.value})} placeholder="correo@ejemplo.com" disabled={!abmUnlocked} />
              </div>
              <div className="form-group">
                <label>Dirección Exacta (Operativa) <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <textarea className="input-field" value={perfil.direccion_exacta || ''} onChange={e => setPerfil({...perfil, direccion_exacta: e.target.value})} rows="2" placeholder="Calle, Nro, Piso..." disabled={!abmUnlocked}></textarea>
              </div>
              <div className="form-group">
                <label>Precio Final Cotizado <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>(Opcional)</span></label>
                <input type="text" className="input-field" value={perfil.precio_final_cotizado || ''} onChange={e => setPerfil({...perfil, precio_final_cotizado: e.target.value})} placeholder="ARS / USD ..." disabled={!abmUnlocked} />
              </div>
            </div>

            {abmUnlocked && (
              <>
                <button type="submit" className="btn-primary" disabled={savingPerfil} style={{ width: '100%', marginTop: '10px' }}>
                  <FaSave /> {savingPerfil ? 'Guardando...' : 'Guardar Avances ABM'}
                </button>
                <div style={{ marginTop: '15px' }}>
                  <div style={{ position: 'relative' }}>
                    <button type="button" className="btn-primary" onClick={handleExportCbnPdf} disabled={exportingCbnPdf || !investigacionCompleta} style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', background: investigacionCompleta ? 'var(--accent-primary)' : 'rgba(100,100,100,0.3)', color: 'white', borderColor: investigacionCompleta ? 'var(--accent-primary)' : 'rgba(100,100,100,0.5)', marginBottom: '10px', cursor: investigacionCompleta ? 'pointer' : 'not-allowed', opacity: investigacionCompleta ? 1 : 0.6 }}>
                      <FaFilePdf /> {exportingCbnPdf ? 'Generando CBN...' : 'Exportar PDF Oficial (CBN)'}
                    </button>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button type="button" className="btn-secondary" onClick={() => handleExportFinalFormat('pdf')} disabled={exportingPdf || !investigacionCompleta} style={{ flex: 1, display: 'inline-flex', justifyContent: 'center', alignItems: 'center', gap: '6px' }}>
                        <FaFilePdf /> {exportingPdf ? 'Generando...' : 'PDF'}
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => handleExportFinalFormat('word')} disabled={exportingWord || !investigacionCompleta} style={{ flex: 1, display: 'inline-flex', justifyContent: 'center', alignItems: 'center', gap: '6px' }}>
                        <FaFileWord /> {exportingWord ? 'Generando...' : 'Word (.docx)'}
                      </button>
                    </div>
                    {!investigacionCompleta && (
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'center', marginTop: '4px' }}>
                        El informe se habilita al guardar los datos faltantes del relevamiento.
                      </p>
                    )}
                  </div>
                </div>
              </>
            )}
          </form>

          {abmUnlocked && (
            <div className="audit-panel" style={{ marginTop: '2rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '15px' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}><FaHistory /> Audit Trail</h4>
              <div className="audit-list">
                {auditLogs.map(log => (
                  <div key={log.id} className="audit-item" style={{ fontSize: '0.85rem', padding: '10px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px', marginBottom: '5px' }}>
                    <div style={{ marginBottom: '5px' }}>
                      <strong style={{ color: 'var(--accent-primary)' }}>{log.user_nombre}</strong> actualizó <em>{log.campo}</em> <span style={{ color: 'var(--text-secondary)', float: 'right' }}>{new Date(log.created_at).toLocaleString('es-AR')}</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--danger)', textDecoration: 'line-through' }}>{log.valor_anterior || 'Vacío'}</span>
                      <span style={{ margin: '0 8px', color: 'var(--text-secondary)' }}>→</span>
                      <span style={{ color: 'var(--success)' }}>{log.valor_nuevo || 'Vacío'}</span>
                    </div>
                  </div>
                ))}
                {auditLogs.length === 0 && <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Sin modificaciones.</p>}
              </div>
            </div>
          )}
          </>
          )}

          {activeTab === 'chat' && abmUnlocked && (
            <div className="chat-panel slide-up">
              {/* Header: Modo Bot/Analista + WhatsApp Status */}
              <div className="switch-container" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <FaRobot size={24} color={conversation?.is_bot_active ? 'var(--success)' : 'var(--text-secondary)'} />
                    <div>
                      <h4 style={{ margin: 0 }}>Honeypot Agent</h4>
                      <small style={{ color: 'var(--text-secondary)' }}>
                        {conversation?.is_bot_active ? 'Bot extrayendo datos (Cerebras LLM)' : 'Analista en control manual'}
                      </small>
                    </div>
                  </div>
                  <button 
                    className={`switch-btn ${!conversation?.is_bot_active ? 'manual' : ''}`} 
                    onClick={toggleChatMode}
                  >
                    {conversation?.is_bot_active ? 'Tomar Control (Manual)' : 'Reactivar Bot'}
                  </button>
                </div>

                {/* WhatsApp Link */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', background: 'rgba(37,211,102,0.1)', borderRadius: '8px', border: '1px solid rgba(37,211,102,0.2)' }}>
                  <FaWhatsapp color="#25D366" size={18} />
                  {conversation?.whatsapp_phone ? (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>Vinculado: <strong>{conversation.whatsapp_phone}</strong></span>
                  ) : (
                    <div style={{ display: 'flex', gap: '6px', flex: 1 }}>
                      <input
                        type="text"
                        className="input-field"
                        placeholder="+5491112345678"
                        value={waPhone}
                        onChange={e => setWaPhone(e.target.value)}
                        style={{ padding: '6px 10px', fontSize: '0.85rem', flex: 1 }}
                      />
                      <button className="btn-ghost" onClick={handleLinkWhatsApp} disabled={linkingWa} style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
                        <FaLink /> {linkingWa ? '...' : 'Vincular'}
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Chat Messages */}
              <div className="chat-container" style={{ maxHeight: '350px', overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {conversation?.messages && conversation.messages.length > 0 ? (
                  conversation.messages.map((msg, idx) => {
                    const entities = parseEntities(msg.extracted_entities);
                    return (
                      <div key={msg.id || idx} style={{ alignSelf: msg.sender === 'infractor' ? 'flex-start' : 'flex-end', maxWidth: '80%' }}>
                        <div className={`chat-bubble ${msg.sender === 'bot' || msg.sender === 'analista' ? 'bot' : 'infractor'}`} style={{ 
                          background: msg.sender === 'analista' ? 'rgba(52, 152, 219, 0.15)' : (msg.sender === 'bot' ? 'rgba(90, 46, 152, 0.2)' : 'rgba(255,255,255,0.05)'),
                          border: msg.sender === 'analista' ? '1px solid rgba(52, 152, 219, 0.4)' : (msg.sender === 'bot' ? '1px solid rgba(90, 46, 152, 0.4)' : '1px solid rgba(255,255,255,0.1)')
                        }}>
                          <strong style={{ display: 'block', fontSize: '0.75rem', marginBottom: '6px', color: msg.sender === 'analista' ? '#3498db' : (msg.sender === 'bot' ? '#9b66d9' : 'var(--text-secondary)') }}>
                            {msg.sender === 'bot' ? 'HONEYPOT AI' : msg.sender === 'analista' ? 'ANALISTA (TÚ)' : 'INFRACTOR'}
                            <span style={{ opacity: 0.6, marginLeft: '8px', fontWeight: 'normal' }}>{new Date(msg.timestamp).toLocaleTimeString('es-AR', {hour: '2-digit', minute:'2-digit'})}</span>
                          </strong>
                          <span style={{ lineHeight: '1.4', fontSize: '0.9rem' }}>{msg.text || msg.content}</span>
                        </div>
                        {/* LLM Extraction Badges */}
                        {entities && Object.keys(entities).length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px', paddingLeft: '8px' }}>
                            <FaBrain size={10} color="var(--warning)" title="Extraído por NLP" />
                            {Object.entries(entities).map(([key, val]) => (
                              <span key={key} style={{ fontSize: '0.7rem', background: 'rgba(255,215,0,0.15)', color: 'var(--warning)', padding: '2px 6px', borderRadius: '4px', border: '1px solid rgba(255,215,0,0.3)' }} title={String(val)}>
                                {ENTITY_LABELS[key] || key}: {String(val).substring(0, 20)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="chat-bubble system" style={{ textAlign: 'center', opacity: 0.6 }}>
                    No hay mensajes. {conversation?.whatsapp_phone ? 'Esperando interacción del infractor vía WhatsApp.' : 'Vincula un número de WhatsApp para iniciar.'}
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input de Envío Manual */}
              {!conversation?.is_bot_active && (
                <form onSubmit={handleSendChat} style={{ display: 'flex', gap: '8px', marginTop: '12px', padding: '0 4px' }}>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Escribe un mensaje como analista..."
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    disabled={sendingChat}
                    style={{ flex: 1, padding: '10px 14px' }}
                  />
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={sendingChat || !chatInput.trim()}
                    style={{ padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <FaPaperPlane /> {sendingChat ? '...' : 'Enviar'}
                  </button>
                </form>
              )}
              {conversation?.is_bot_active && (
                <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(57,255,20,0.05)', borderRadius: '8px', border: '1px solid rgba(57,255,20,0.15)', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  El bot está respondiendo automáticamente. Cambia a modo manual para intervenir.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      
      {showStatusModal && (
        <div className="modal-overlay">
          <div className="modal-content slide-up">
            <h3><FaExclamationTriangle /> Confirmar Cambio de Estado</h3>
            <p style={{ color: 'var(--text-secondary)' }}>
              Estás a punto de cambiar el estado del reporte a <strong>{pendingEstado}</strong>. 
              {(pendingEstado === 'Sospechoso' || pendingEstado === 'Investigando') && " Esto habilitará el módulo de Perfilamiento (ABM)."}
            </p>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setShowStatusModal(false)}>Cancelar</button>
              <button className="btn-primary" onClick={executeUpdateStatus}>Confirmar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
