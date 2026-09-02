import api from './api';

export const getApiKeys = () => {
  return api.get('/api/api-keys');
};

export const saveApiKey = (data) => {
  return api.post('/api/api-keys', data);
};

export const deleteApiKey = (serviceName) => {
  return api.delete(`/api/api-keys/${serviceName}`);
};

export const testApiKey = (serviceName, apiKey = null) => {
  return api.post(`/api/api-keys/test/${serviceName}`, { api_key: apiKey });
};