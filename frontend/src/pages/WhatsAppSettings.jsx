import React, { useState, useEffect } from 'react';
import { FaWhatsapp, FaEye, FaEyeSlash, FaSave, FaCheckCircle, FaExclamationTriangle, FaVial, FaSpinner } from 'react-icons/fa';
import api from '../services/api';
import Modal from '../components/Modal';

export default function WhatsAppSettings() {
  const [formData, setFormData] = useState({
    whatsapp_access_token: '',
    whatsapp_phone_number_id: '',
    whatsapp_business_account_id: '',
    whatsapp_verify_token: ''
  });
  
  const [showToken, setShowToken] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState(null);

  // Estado del Modal de Resultados (Pruebas y Guardado)
  const [modal, setModal] = useState({
    isOpen: false,
    title: '',
    type: 'info', // 'success', 'error', 'testing'
    message: '',
    details: '',
    latency_ms: null
  });

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/settings/whatsapp');
      setFormData({
        whatsapp_access_token: res.data.whatsapp_access_token || '',
        whatsapp_phone_number_id: res.data.whatsapp_phone_number_id || '',
        whatsapp_business_account_id: res.data.whatsapp_business_account_id || '',
        whatsapp_verify_token: res.data.whatsapp_verify_token || ''
      });
    } catch (err) {
      console.error("Error fetching settings:", err);
      setMessage({ type: 'error', text: 'No se pudo cargar la configuración actual.' });
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await api.post('/api/settings/whatsapp', formData);
      fetchSettings(); // Recargar datos
      setModal({
        isOpen: true,
        title: 'Configuración Guardada',
        type: 'success',
        message: res.data?.message || 'Las credenciales se guardaron exitosamente en la base de datos PostgreSQL.',
        details: 'El sistema ya está utilizando estos parámetros para el Webhook y la mensajería activa.',
        latency_ms: null
      });
    } catch (err) {
      console.error("Error saving settings:", err);
      const errorDetail = err.response?.data?.detail || err.message || 'Ocurrió un problema al guardar la configuración en la base de datos.';
      setModal({
        isOpen: true,
        title: 'Error al Guardar',
        type: 'error',
        message: errorDetail,
        details: 'Verifique que su usuario cuente con permisos de administrador o intente de nuevo.',
        latency_ms: null
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setModal({
      isOpen: true,
      title: 'Probando Conexión con Meta',
      type: 'testing',
      message: 'Conectando con Meta Graph API (v21.0)...',
      details: 'Consultando la validez del WhatsApp Access Token y el Phone Number ID en los servidores de Meta.',
      latency_ms: null
    });

    try {
      const res = await api.post('/api/settings/whatsapp/test', {
        whatsapp_access_token: formData.whatsapp_access_token,
        whatsapp_phone_number_id: formData.whatsapp_phone_number_id
      });

      if (res.data?.success) {
        setModal({
          isOpen: true,
          title: 'Conexión Exitosa con Meta',
          type: 'success',
          message: res.data.message || 'El Access Token y el Phone Number ID son 100% válidos.',
          details: res.data.details || 'La API de WhatsApp Cloud respondió satisfactoriamente.',
          latency_ms: res.data.latency_ms
        });
      } else {
        setModal({
          isOpen: true,
          title: 'Fallo en la Conexión con Meta',
          type: 'error',
          message: res.data?.message || 'Meta rechazó la solicitud de verificación.',
          details: res.data?.details || 'Compruebe que el Access Token no haya expirado y que el Phone Number ID sea el correcto.',
          latency_ms: res.data?.latency_ms
        });
      }
    } catch (err) {
      console.error("Error testing connection:", err);
      const errorDetail = err.response?.data?.detail || err.message || 'No se pudo contactar con la API de Meta.';
      setModal({
        isOpen: true,
        title: 'Error al Probar Conexión',
        type: 'error',
        message: errorDetail,
        details: 'Revise que los datos ingresados no contengan espacios en blanco o caracteres extraños.',
        latency_ms: null
      });
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;

  return (
    <div className="page-container fade-in">
      <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px' }}>
        <div className="avatar-large"><FaWhatsapp /></div>
        <div>
          <h2>Configuración de WhatsApp Cloud API</h2>
          <p className="text-secondary">Credenciales para el Chat Center y Webhook de Meta</p>
        </div>
      </div>

      {message && (
        <div className={`message-banner ${message.type === 'success' ? 'success-message' : 'error-message'} slide-up`} style={{ marginBottom: '20px' }}>
          {message.type === 'success' ? <FaCheckCircle /> : <FaExclamationTriangle />} {message.text}
        </div>
      )}

      <div className="glass-card" style={{ maxWidth: '800px' }}>
        <form onSubmit={handleSave}>
          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>WhatsApp Access Token</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showToken ? 'text' : 'password'}
                name="whatsapp_access_token"
                className="input-field"
                value={formData.whatsapp_access_token}
                onChange={handleChange}
                placeholder="EAAA..."
                autoComplete="current-password"
                style={{ width: '100%', paddingRight: '40px' }}
              />
              <button 
                type="button" 
                onClick={() => setShowToken(!showToken)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'rgba(255,255,255,0.5)',
                  cursor: 'pointer'
                }}
              >
                {showToken ? <FaEyeSlash /> : <FaEye />}
              </button>
            </div>
            <small style={{ color: 'var(--text-secondary)' }}>Token permanente o temporal generado en Meta for Developers.</small>
          </div>

          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>Phone Number ID</label>
            <input
              type="text"
              name="whatsapp_phone_number_id"
              className="input-field"
              value={formData.whatsapp_phone_number_id}
              onChange={handleChange}
              placeholder="Ej: 123456789012345"
              style={{ width: '100%' }}
            />
            <small style={{ color: 'var(--text-secondary)' }}>Identificador único del número de teléfono remitente.</small>
          </div>

          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>WhatsApp Business Account ID</label>
            <input
              type="text"
              name="whatsapp_business_account_id"
              className="input-field"
              value={formData.whatsapp_business_account_id}
              onChange={handleChange}
              placeholder="Ej: 109876543210987"
              style={{ width: '100%' }}
            />
          </div>

          <div className="form-group" style={{ marginBottom: '30px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>Verify Token (Webhook)</label>
            <input
              type="text"
              name="whatsapp_verify_token"
              className="input-field"
              value={formData.whatsapp_verify_token}
              onChange={handleChange}
              placeholder="Ej: mi_secreto_seguro_123"
              style={{ width: '100%' }}
            />
            <small style={{ color: 'var(--text-secondary)' }}>El mismo token que pegarás en la configuración del Webhook de Meta.</small>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
            <button 
              type="submit" 
              className="btn-primary" 
              disabled={saving}
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', fontSize: '1rem', cursor: 'pointer' }}
            >
              <FaSave /> {saving ? 'Guardando en BD...' : 'Guardar Configuración'}
            </button>

            <button 
              type="button" 
              onClick={handleTestConnection}
              disabled={testing || saving}
              className="btn-secondary"
              style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px', 
                padding: '12px 20px', 
                fontSize: '1rem',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.4)',
                color: '#60a5fa',
                borderRadius: '8px',
                cursor: 'pointer'
              }}
            >
              <FaVial /> {testing ? 'Probando conexión...' : '🧪 Probar Conexión'}
            </button>
          </div>
        </form>
      </div>

      {/* Modal de Resultados (Pruebas y Guardado) */}
      <Modal
        isOpen={modal.isOpen}
        onClose={() => setModal(prev => ({ ...prev, isOpen: false }))}
        title={modal.title}
        footer={
          modal.type !== 'testing' ? (
            <button
              type="button"
              className={modal.type === 'success' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setModal(prev => ({ ...prev, isOpen: false }))}
              style={{ padding: '10px 24px', cursor: 'pointer' }}
            >
              {modal.type === 'success' ? 'Aceptar' : 'Entendido / Cerrar'}
            </button>
          ) : null
        }
      >
        <div style={{ textAlign: 'center', padding: '15px 10px' }}>
          {modal.type === 'testing' && (
            <div>
              <FaSpinner className="spin" style={{ fontSize: '3rem', color: '#3b82f6', marginBottom: '16px', animation: 'spin 1s linear infinite' }} />
              <h4 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>{modal.message}</h4>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem' }}>{modal.details}</p>
            </div>
          )}

          {modal.type === 'success' && (
            <div>
              <FaCheckCircle style={{ fontSize: '3.2rem', color: '#22c55e', marginBottom: '16px' }} />
              <h4 style={{ fontSize: '1.25rem', color: '#22c55e', marginBottom: '10px' }}>Operación Exitosa</h4>
              <p style={{ fontSize: '1rem', marginBottom: '12px', fontWeight: '500' }}>{modal.message}</p>
              {modal.details && (
                <div style={{
                  backgroundColor: 'rgba(34, 197, 94, 0.08)',
                  border: '1px solid rgba(34, 197, 94, 0.25)',
                  borderRadius: '8px',
                  padding: '12px',
                  color: 'var(--text-primary)',
                  fontSize: '0.9rem',
                  textAlign: 'left'
                }}>
                  <strong>Detalles:</strong>
                  <p style={{ margin: '4px 0 0 0', opacity: 0.9 }}>{modal.details}</p>
                </div>
              )}
              {modal.latency_ms && (
                <div style={{ marginTop: '10px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  Latencia de respuesta: <strong>{modal.latency_ms} ms</strong>
                </div>
              )}
            </div>
          )}

          {modal.type === 'error' && (
            <div>
              <FaExclamationTriangle style={{ fontSize: '3.2rem', color: '#ef4444', marginBottom: '16px' }} />
              <h4 style={{ fontSize: '1.25rem', color: '#ef4444', marginBottom: '10px' }}>Se detectó un problema</h4>
              <p style={{ fontSize: '1rem', marginBottom: '12px', fontWeight: '500', color: '#f87171' }}>{modal.message}</p>
              {modal.details && (
                <div style={{
                  backgroundColor: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  borderRadius: '8px',
                  padding: '12px',
                  color: 'var(--text-primary)',
                  fontSize: '0.9rem',
                  textAlign: 'left'
                }}>
                  <strong style={{ color: '#f87171' }}>Causa / Detalle técnico:</strong>
                  <p style={{ margin: '4px 0 0 0', opacity: 0.9, wordBreak: 'break-word' }}>{modal.details}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
