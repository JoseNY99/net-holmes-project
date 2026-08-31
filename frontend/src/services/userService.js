import api from './api';

export const getUsers = () => api.get('/api/users/');
export const createUser = (data) => api.post('/api/users/', data);
export const updateUser = (id, data) => api.put(`/api/users/${id}`, data);
export const toggleUserStatus = (id) => api.patch(`/api/users/${id}/toggle`);
export const deleteUser = (id) => api.delete(`/api/users/${id}`);
