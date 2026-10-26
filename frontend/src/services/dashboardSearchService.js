import api from './api';

export const getSearchLocations = () => api.get('/api/dashboard/search/locations');
export const startDashboardSearch = (options) => api.post('/api/dashboard/search/start', options);
export const getDashboardSearchStatus = () => api.get('/api/dashboard/search/status');
export const stopDashboardSearch = () => api.post('/api/dashboard/search/stop');
