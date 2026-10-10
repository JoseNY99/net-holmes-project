// Servicio de Autenticación — registro, login, perfil
import api from './api';

// Registrar nuevo usuario
export const register = (data) => api.post('/api/auth/register', data);

// Iniciar sesión
export const login = (correo, password) =>
  api.post('/api/auth/login', { correo, password });

// Obtener datos del usuario actual
export const getMe = () => api.get('/api/auth/me');
