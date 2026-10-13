import React, { useState, useEffect } from 'react';
import { FaCheck, FaTimes, FaUserSecret } from 'react-icons/fa';
import api from '../services/api';

export default function AdminLogs() {
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchFlags();
  }, []);

  const fetchFlags = async () => {
    try {
      const res = await api.get('/api/admin/logs/flags');
      setFlags(res.data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id) => {
    try {
      await api.post(`/api/admin/logs/flags/${id}/approve`);
      fetchFlags();
    } catch (e) {
      console.error(e);
      alert('Error al aprobar bandera');
    }
  };

  const handleReject = async (id) => {
    try {
      await api.post(`/api/admin/logs/flags/${id}/reject`);
      fetchFlags();
    } catch (e) {
      console.error(e);
      alert('Error al rechazar bandera');
    }
  };

  return (
    <div className="page-container fade-in">
      <div className="glass-card">
        <h2><FaUserSecret /> Logs de Entrenamiento IA (Falsos Positivos)</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '20px' }}>
          Revisa los sospechosos bandereados por los analistas. Al aprobarlos, entrenarás la memoria RAG para ignorar estos perfiles en el futuro.
        </p>

        {loading ? (
          <div className="spinner-container"><div className="spinner spinner--dark"></div></div>
        ) : flags.length === 0 ? (
          <div className="empty-state">
            <h3>No hay banderas pendientes</h3>
            <p>La IA está funcionando sin interrupciones reportadas.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Sospechoso</th>
                  <th>Username(s)</th>
                  <th>Fecha de Reporte</th>
                  <th>Reportado Por</th>
                  <th>Motivo</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {flags.map((flag) => (
                  <tr key={flag.id}>
                    <td><strong>{flag.nombre_completo || flag.codigo_sospechoso}</strong></td>
                    <td><span className="platform-badge">{flag.usernames || 'N/A'}</span></td>
                    <td>{flag.created_at ? new Date(flag.created_at).toLocaleString('es-AR') : 'N/A'}</td>
                    <td>{flag.flagged_by_name}</td>
                    <td><em>"{flag.flag_reason}"</em></td>
                    <td style={{ display: 'flex', gap: '8px' }}>
                      <button className="btn-primary" style={{ padding: '6px 12px', fontSize: '0.8rem' }} onClick={() => handleApprove(flag.id)}>
                        <FaCheck /> Confirmar & Entrenar
                      </button>
                      <button className="btn-ghost" style={{ padding: '6px 12px', fontSize: '0.8rem', color: 'var(--danger)', borderColor: 'var(--danger)' }} onClick={() => handleReject(flag.id)}>
                        <FaTimes /> Rechazar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
