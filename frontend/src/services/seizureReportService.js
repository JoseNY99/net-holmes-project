import api from './api';

export const listSeizureReports = (params = {}) => api.get('/api/seizure-reports/', { params });
export const createSeizureReport = (data) => api.post('/api/seizure-reports/', data);
export const getSeizureReport = (id) => api.get(`/api/seizure-reports/${id}`);
export const updateSeizureReport = (id, data) => api.put(`/api/seizure-reports/${id}`, data);
export const transitionSeizureReport = (id, status, comment = '') => api.post(`/api/seizure-reports/${id}/transition`, { status, comment });
export const extractPolicePdf = (file) => {
  const body = new FormData(); body.append('file', file);
  return api.post('/api/seizure-reports/extract/police-pdf', body, { headers: { 'Content-Type': 'multipart/form-data' } });
};
const upload = async (id, kind, files) => {
  const responses = [];
  for (const file of Array.from(files)) {
    const body = new FormData(); body.append('files', file);
    responses.push(await api.post(`/api/seizure-reports/${id}/${kind}`, body, { headers: { 'Content-Type': 'multipart/form-data' } }));
  }
  return responses;
};
export const uploadSeizurePhotos = (id, files) => upload(id, 'photos', files);
export const uploadSeizureDocuments = (id, files) => upload(id, 'documents', files);
export const downloadSeizureReport = (id, format) => api.get(`/api/seizure-reports/${id}/download/${format}`, { responseType: 'blob' });
export const generateSeizureReport = (id) => api.post(`/api/seizure-reports/${id}/generate`);
export const getSeizureHistory = (id) => api.get(`/api/seizure-reports/${id}/history`);
export const updateSeizureFile = (reportId, fileId, data) => api.patch(`/api/seizure-reports/${reportId}/files/${fileId}`, data);
export const reorderSeizureFiles = (reportId, fileIds) => api.post(`/api/seizure-reports/${reportId}/files/reorder`, { file_ids: fileIds });
export const deleteSeizureFile = (reportId, fileId) => api.delete(`/api/seizure-reports/${reportId}/files/${fileId}`);
