import api from './api';

export const getGeneralReport = () => {
  return api.get('/api/reports_defense/general');
};

export const getReportList = (params) => {
  return api.get('/api/reports_defense/', { params });
};

export const exportReport = (format, params) => {
  return api.get(`/api/reports_defense/export/${format}`, { params, responseType: 'blob' });
};

export const getSuspectReport = (suspectId) => api.get(`/api/reports_defense/${suspectId}`);

export const exportSingleReport = (itemId, format) => {
  return api.get(`/api/reports_defense/${itemId}/export/${format}`, { responseType: 'blob' });
};
