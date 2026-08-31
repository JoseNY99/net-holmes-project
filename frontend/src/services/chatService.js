import api from './api';

const chatService = {
  // Obtener todas las conversaciones
  getAllConversations: () => {
    return api.get('/api/chat/all');
  },

  // Obtener conversación con historial de mensajes
  getConversation: (reporteId) => {
    return api.get(`/api/chat/${reporteId}`);
  },

  // Alternar entre modo Bot (automático) y Analista (manual)
  toggleMode: (reporteId, mode) => {
    return api.post(`/api/chat/${reporteId}/toggle-mode`, { mode });
  },

  // Enviar mensaje manual del analista (se envía por WhatsApp si está vinculado)
  sendMessage: (reporteId, text) => {
    return api.post(`/api/chat/${reporteId}/send`, { text });
  },

  // Vincular número de WhatsApp a la conversación
  linkWhatsApp: (reporteId, whatsappPhone) => {
    return api.post(`/api/chat/${reporteId}/link-whatsapp`, { whatsapp_phone: whatsappPhone });
  },
};

export default chatService;
