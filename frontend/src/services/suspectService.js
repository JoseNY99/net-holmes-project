import api from './api';

export const getSuspects = (params = {}) => {
  const query = new URLSearchParams();
  if (params.estado && params.estado !== 'todos') query.append('estado', params.estado);
  if (params.plataforma) query.append('plataforma', params.plataforma);
  if (params.skip !== undefined) query.append('skip', params.skip);
  if (params.limit !== undefined) query.append('limit', params.limit);
  
  return api.get(`/api/reports_defense/?${query.toString()}`);
};

export const getSuspectDetail = (id) => api.get(`/api/reports_defense/${id}`);
export const updateSuspect = (id, data) => api.patch(`/api/reports_defense/${id}`, data);
export const quickEditSuspect = (suspectId, data) => api.patch(`/api/reports_defense/${suspectId}/quick-edit`, data);
export const getPerfil = (suspectId) => api.get(`/api/reports_defense/${suspectId}/perfil`);
export const updatePerfil = (suspectId, data) => api.patch(`/api/reports_defense/${suspectId}/perfil`, data);
export const getAuditLogs = (suspectId) => api.get(`/api/reports_defense/${suspectId}/audit`);

// Endpoints de exportación de reportes finales
export const exportPdf = (suspectId) => api.get(`/api/reports_defense/${suspectId}/export/pdf`, { responseType: 'blob' });
export const exportWord = (suspectId) => api.get(`/api/reports_defense/${suspectId}/export/word`, { responseType: 'blob' });
export const exportCbnPdf = (suspectId) => api.get(`/api/reports_defense/${suspectId}/export/cbn-pdf`, { responseType: 'blob' });
export const captureScreenshot = (suspectId) => api.post(`/api/reports_defense/${suspectId}/screenshot`);
// Antiguas funciones requeridas por otros componentes
export const promoteScan = (scanResultId) => api.post(`/api/suspects/promote/${scanResultId}`);
export const addNote = (suspectId, contenido) => api.post(`/api/suspects/${suspectId}/notes`, { contenido });
export const getNotes = (suspectId) => api.get(`/api/suspects/${suspectId}/notes`);
export const flagSuspect = (suspectId, reason) => api.post(`/api/admin/logs/suspects/${suspectId}/flag`, { reason });
