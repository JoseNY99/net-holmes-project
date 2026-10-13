import React, { useState, useEffect } from 'react';
import { 
  FaKey, FaPlug, FaCheckCircle, FaExclamationTriangle, FaTrashAlt, 
  FaEdit, FaEye, FaEyeSlash, FaExternalLinkAlt, FaSync, FaShieldAlt,
  FaServer, FaRobot, FaSearch, FaWhatsapp
} from 'react-icons/fa';
import { getApiKeys, saveApiKey, deleteApiKey, testApiKey } from '../services/apiKeyService';
import './ScraperSettings.css';

export default function ScraperSettings() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [testingService, setTestingService] = useState(null);
  const [testResult, setTestResult] = useState({});

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedService, setSelectedService] = useState(null);
  const [newKey, setNewKey] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newIsActive, setNewIsActive] = useState(true);
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalTesting, setModalTesting] = useState(false);
  const [modalTestResult, setModalTestResult] = useState(null);

  const fetchKeys = async () => {
    try {
      setLoading(true);
      const res = await getApiKeys();
      setKeys(res.data || []);
    } catch (err) {
      setMessage({ type: 'error', text: 'Error al cargar la configuración de API Keys.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleOpenEdit = (srv) => {
    setSelectedService(srv);
    setNewKey('');
    setNewDescription(srv.description || '');
    setNewIsActive(srv.is_active !== false);
    setShowKeyInput(false);
    setModalTestResult(null);
    setModalOpen(true);
  };

  const handleSaveKey = async (e) => {
    e.preventDefault();
    if (!selectedService) return;

    setSaving(true);
    try {
      await saveApiKey({
        service_name: selectedService.service_name,
        api_key: newKey.trim() || undefined,
        description: newDescription.trim() || undefined,
        is_active: newIsActive
      });
      setMessage({ type: 'success', text: `API Key para ${selectedService.display_name} guardada correctamente en la Base de Datos.` });
      setModalOpen(false);
      fetchKeys();
    } catch (err) {
      const errDetail = err.response?.data?.detail || 'Error al guardar la API Key.';
      setMessage({ type: 'error', text: errDetail });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (srv) => {
    if (!window.confirm(`¿Seguro que deseas eliminar la API Key de base de datos para ${srv.display_name}? El sistema recurrirá al archivo .env si existe.`)) {
      return;
    }

    try {
      await deleteApiKey(srv.service_name);
      setMessage({ type: 'success', text: `Configuración en DB eliminada para ${srv.display_name}.` });
      fetchKeys();
    } catch (err) {
      setMessage({ type: 'error', text: 'Error al eliminar la configuración.' });
    }
  };

  const handleTestConnection = async (serviceName, keyOverride = null) => {
    try {
      if (keyOverride !== null) {
        setModalTesting(true);
        setModalTestResult(null);
      } else {
        setTestingService(serviceName);
      }

      const res = await testApiKey(serviceName, keyOverride);
      const data = res.data;

      if (keyOverride !== null) {
        setModalTestResult(data);
      } else {
        setTestResult(prev => ({ ...prev, [serviceName]: data }));
      }
    } catch (err) {
      const errData = { success: false, message: err.response?.data?.detail || 'Error de conexión con el proveedor.' };
      if (keyOverride !== null) {
        setModalTestResult(errData);
      } else {
        setTestResult(prev => ({ ...prev, [serviceName]: errData }));
      }
    } finally {
      setTestingService(null);
      setModalTesting(false);
    }
  };

  const getServiceIcon = (name) => {
    switch (name) {
      case 'serper': return <FaSearch color="#4285F4" />;
      case 'apify': return <FaPlug color="#FF5722" />;
      case 'rapidapi': return <FaServer color="#00E676" />;
      case 'cerebras': return <FaRobot color="#A855F7" />;
      case 'deepseek': return <FaRobot color="#3B82F6" />;
      case 'meta_whatsapp': return <FaWhatsapp color="#25D366" />;
      default: return <FaKey color="#F59E0B" />;
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="spinner-container"><div className="spinner spinner--dark"></div></div>
      </div>
    );
  }

  return (
    <div className="page-container scraper-settings-page fade-in">
      <div className="scraper-settings-header">
        <div className="header-title-group">
          <h2><FaKey style={{ marginRight: '10px', color: 'var(--accent-primary)' }} /> Configuración de Scrapers & API Keys</h2>
          <p>Administra y prueba en tiempo real las credenciales almacenadas en Base de Datos para cada motor de búsqueda e Inteligencia Artificial.</p>
        </div>
        <button className="btn-secondary" onClick={fetchKeys} title="Refrescar estados">
          <FaSync /> Refrescar
        </button>
      </div>

      {message && (
        <div className={`message-banner ${message.type === 'success' ? 'success-message' : 'error-message'} slide-up`}>
          {message.type === 'success' ? <FaCheckCircle /> : <FaExclamationTriangle />} {message.text}
        </div>
      )}

      <div className="scrapers-grid">
        {keys.map((srv) => {
          const result = testResult[srv.service_name];
          const isTesting = testingService === srv.service_name;

          return (
            <div key={srv.service_name} className={`glass-card scraper-card ${srv.is_configured ? 'configured' : 'unconfigured'}`}>
              <div className="scraper-card-top">
                <div className="scraper-icon-wrapper">
                  {getServiceIcon(srv.service_name)}
                </div>
                <div className="scraper-meta-info">
                  <h3>{srv.display_name}</h3>
                  <div className="scraper-badges">
                    {srv.is_from_db ? (
                      <span className="badge badge-db">Base de Datos (ABM)</span>
                    ) : srv.is_configured ? (
                      <span className="badge badge-env">Archivo .env</span>
                    ) : (
                      <span className="badge badge-missing">Sin Configurar</span>
                    )}

                    {srv.is_configured && (
                      <span className={`badge ${srv.is_active ? 'badge-active' : 'badge-inactive'}`}>
                        {srv.is_active ? 'Activo' : 'Desactivado'}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <p className="scraper-description">{srv.description}</p>

              <div className="scraper-key-preview">
                <span className="key-label">API Key:</span>
                <span className="key-value font-mono">
                  {srv.masked_key ? srv.masked_key : '••••••••••••••••'}
                </span>
                {srv.doc_url && (
                  <a href={srv.doc_url} target="_blank" rel="noopener noreferrer" className="doc-link" title="Obtener API Key en portal oficial">
                    <FaExternalLinkAlt size={12} />
                  </a>
                )}
              </div>

              {/* Resultado del Test en vivo */}
              {result && (
                <div className={`test-feedback-box ${result.success ? 'feedback-success' : 'feedback-error'} fade-in`}>
                  {result.success ? <FaCheckCircle /> : <FaExclamationTriangle />}
                  <span>{result.message}</span>
                </div>
              )}

              <div className="scraper-card-actions">
                <button 
                  type="button" 
                  className="btn-test" 
                  onClick={() => handleTestConnection(srv.service_name)}
                  disabled={!srv.is_configured || isTesting}
                  title="Ejecutar prueba de conectividad y latencia con el proveedor"
                >
                  {isTesting ? <span className="spinner-inline" /> : <FaPlug />} Test Conexión
                </button>

                <button 
                  type="button" 
                  className="btn-edit-key"
                  onClick={() => handleOpenEdit(srv)}
                  title="Modificar o cargar nueva API Key en Base de Datos"
                >
                  <FaEdit /> Configurar
                </button>

                {srv.is_from_db && (
                  <button 
                    type="button" 
                    className="btn-delete-key"
                    onClick={() => handleDelete(srv)}
                    title="Eliminar de la Base de Datos y usar fallback"
                  >
                    <FaTrashAlt />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal de Configuración / Edición de Key */}
      {modalOpen && selectedService && (
        <div className="modal-overlay fade-in" onClick={() => setModalOpen(false)}>
          <div className="glass-modal slide-up scraper-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>
                {getServiceIcon(selectedService.service_name)}
                Configurar {selectedService.display_name}
              </h3>
              <button className="btn-close" onClick={() => setModalOpen(false)}>&times;</button>
            </div>

            <form onSubmit={handleSaveKey}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Nueva API Key / Token</label>
                  <div className="password-input-wrapper">
                    <input 
                      type={showKeyInput ? "text" : "password"}
                      className="input-field font-mono"
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      placeholder={selectedService.masked_key ? `Llave actual: ${selectedService.masked_key} (Dejar vacío para no cambiar)` : "Pega tu API Key aquí..."}
                      autoComplete="off"
                    />
                    <button 
                      type="button" 
                      className="btn-eye" 
                      onClick={() => setShowKeyInput(prev => !prev)}
                      title={showKeyInput ? "Ocultar" : "Mostrar"}
                    >
                      {showKeyInput ? <FaEyeSlash /> : <FaEye />}
                    </button>
                  </div>
                  <small className="help-text">La llave se almacenará en la base de datos y tendrá prioridad sobre el archivo .env.</small>
                </div>

                <div className="form-group">
                  <label className="form-label">Descripción / Nota</label>
                  <input 
                    type="text" 
                    className="input-field" 
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="Ej: Cuenta principal de producción, límite mensual 10k"
                  />
                </div>

                <div className="form-group-checkbox">
                  <label className="checkbox-label">
                    <input 
                      type="checkbox" 
                      checked={newIsActive} 
                      onChange={(e) => setNewIsActive(e.target.checked)}
                    />
                    <span>Habilitar este servicio para los escaneos del sistema</span>
                  </label>
                </div>

                {/* Test rápido dentro del modal */}
                {newKey.trim() && (
                  <div className="modal-test-section">
                    <button 
                      type="button" 
                      className="btn-secondary btn-sm"
                      onClick={() => handleTestConnection(selectedService.service_name, newKey.trim())}
                      disabled={modalTesting}
                    >
                      {modalTesting ? <span className="spinner-inline" /> : <FaPlug />} Probar esta Key antes de guardar
                    </button>

                    {modalTestResult && (
                      <div className={`test-feedback-box ${modalTestResult.success ? 'feedback-success' : 'feedback-error'} mt-2 fade-in`}>
                        {modalTestResult.success ? <FaCheckCircle /> : <FaExclamationTriangle />}
                        <span>{modalTestResult.message}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-ghost" onClick={() => setModalOpen(false)}>Cancelar</button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Guardando...' : 'Guardar en Base de Datos'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}