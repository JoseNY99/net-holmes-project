import api from './api';

const correlationService = {
  getClusters: async () => {
    const response = await api.get('/api/correlations/clusters');
    return response.data;
  },
  getClusterDetails: async (clusterId) => {
    const response = await api.get(`/api/correlations/clusters/${clusterId}`);
    return response.data;
  },
  getLinksForReporte: async (reporteId) => {
    const response = await api.get(`/api/correlations/links/${reporteId}`);
    return response.data;
  },
  analyzeDeep: async (reporteId, dimensions = ["temporal", "linguistico", "contenido", "identificador"]) => {
    const response = await api.post(`/api/correlations/analyze/${reporteId}`, { dimensiones: dimensions });
    return response.data;
  },
  autoCorrelate: async () => {
    const response = await api.post('/api/correlations/auto-correlate');
    return response.data;
  }
};

export default correlationService;
