import api from './api';

export const getScanResults = async (params = {}) => {
  // Redirigir la antigua llamada de Scans al nuevo endpoint de Reportes (Fase 1)
  const query = new URLSearchParams();
  if (params.plataforma) query.append('plataforma', params.plataforma);
  if (params.estado) query.append('estado', params.estado);
  if (params.skip !== undefined) query.append('skip', params.skip);
  if (params.limit !== undefined) query.append('limit', params.limit);
  
  try {
    return await api.get(`/api/reports_defense/?${query.toString()}`);
  } catch (error) {
    return { data: [] };
  }
};

export const getScanStats = () => api.get('/api/dashboard/stats');
export const getScanResult = (id) => api.get(`/api/reports_defense/${id}`);
export const updateScanResult = (id, data) => api.patch(`/api/reports_defense/${id}`, data);
export const manualScan = (url, plataforma, brand_id) => {
  return api.post('/api/scan/manual', {
    url,
    plataforma,
    brand_id
  });
};
