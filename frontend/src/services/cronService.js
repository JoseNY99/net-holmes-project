import api from './api';

export const getCronConfig = () => {
  return api.get(`/api/cron/config?t=${new Date().getTime()}`);
};

export const updateCronConfig = (data) => {
  return api.put('/api/cron/config', data);
};

export const toggleCron = (isActive) => {
  return api.post('/api/cron/toggle', typeof isActive === 'boolean' ? { is_active: isActive } : {});
};

export const triggerManualRun = () => {
  return api.post('/api/cron/start');
};

export const stopCron = () => {
  return api.post('/api/cron/stop');
};

export const getCronStatus = () => {
  return api.get('/api/cron/status');
};
