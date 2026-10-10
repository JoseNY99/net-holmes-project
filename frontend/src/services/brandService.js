// Servicio de Marcas — CRUD de marcas y productos
import api from './api';

// === Marcas ===

// Obtener todas las marcas (opcionalmente filtrar por estado)
export const getBrands = (estado) => {
  const params = estado ? { estado } : {};
  return api.get('/api/brands/', { params });
};

// Obtener marca por ID
export const getBrand = (id) => api.get(`/api/brands/${id}`);

// Crear nueva marca
export const createBrand = (data) => api.post('/api/brands/', data);

// Actualizar marca existente
export const updateBrand = (id, data) => api.put(`/api/brands/${id}`, data);

// Alternar estado activo/inactivo de marca
export const toggleBrandStatus = (id) => api.patch(`/api/brands/${id}/toggle`);

// Eliminar marca
export const deleteBrand = (id) => api.delete(`/api/brands/${id}`);

// === Productos ===

// Agregar producto a una marca
export const addProduct = (brandId, data) =>
  api.post(`/api/brands/${brandId}/products`, data);

// Actualizar producto
export const updateProduct = (productId, data) =>
  api.put(`/api/brands/products/${productId}`, data);

// Alternar estado de producto (Activa/Inactiva)
export const toggleProduct = (productId) =>
  api.patch(`/api/brands/products/${productId}/toggle`);

// Eliminar producto
export const deleteProduct = (productId) =>
  api.delete(`/api/brands/products/${productId}`);
