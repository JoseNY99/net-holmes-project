import React, { useState, useEffect } from 'react';
import { FaWhatsapp, FaEye, FaEyeSlash, FaSave, FaCheckCircle, FaExclamationTriangle } from 'react-icons/fa';
import api from '../services/api';

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
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await api.get('/settings/whatsapp');
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
      await api.post('/settings/whatsapp', formData);
      setMessage({ type: 'success', text: 'Configuración guardada correctamente.' });
      setTimeout(() => setMessage(null), 3000);
      fetchSettings(); // Refresh to get masked token
    } catch (err) {
      console.error("Error saving settings:", err);
      setMessage({ type: 'error', text: 'Error al guardar la configuración.' });
    } finally {
      setSaving(false);
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

          <button 
            type="submit" 
            className="btn-primary" 
            disabled={saving}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', fontSize: '1rem' }}
          >
            <FaSave /> {saving ? 'Guardando...' : 'Guardar Configuración'}
          </button>
        </form>
      </div>
    </div>
  );
}
