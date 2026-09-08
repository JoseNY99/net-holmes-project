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

  // Enviar mensaje en simulación @curtis_holmes (solo admin/sup_admin)
  sendCurtisMessage: (text, sender = 'infractor', bot_role = null) => {
    return api.post('/api/chat/curtis/message', { text, sender, bot_role });
  },

  // Reiniciar chat de prueba @curtis_holmes (solo admin/sup_admin)
  resetCurtis: () => {
    return api.post('/api/chat/curtis/reset');
  },

  // Agregar número temporal para pruebas por WhatsApp (solo admin/sup_admin)
  addTemporaryNumber: (payload) => {
    return api.post('/api/chat/add-number', payload);
  },

  // Dar orden de arrancar al bot en una conversación
  startBot: (reporteId, customMessage = null) => {
    return api.post(`/api/chat/${reporteId}/start-bot`, { custom_message: customMessage });
  },

  // Editar número de teléfono o titular de contacto
  editContact: (reporteId, payload) => {
    return api.put(`/api/chat/${reporteId}/edit-contact`, payload);
  },

  // Enviar plantilla oficial de WhatsApp (Message Template) para abrir ventana de 24h
  sendTemplate: (reporteId, templateName, languageCode = 'es') => {
    return api.post(`/api/chat/${reporteId}/send-template`, {
      template_name: templateName,
      language_code: languageCode
    });
  },

  // Obtener logs del sistema (WhatsApp, Bot, Webhook, NLP)
  getSystemLogs: (lastN = 150, filter = '') => {
    return api.get('/api/chat/system-logs', { params: { last_n: lastN, filter } });
  },

  // Obtener instrucciones y mensaje de apertura del bot
  getBotConfig: () => {
    return api.get('/api/chat/bot-config');
  },

  // Actualizar instrucciones y mensaje de apertura del bot
  updateBotConfig: (payload) => {
    return api.put('/api/chat/bot-config', payload);
  },

  // Editar y corregir el contenido de un mensaje individual (lapicito)
  editMessage: (messageId, text) => {
    return api.put(`/api/chat/message/${messageId}`, { text });
  },
};

export default chatService;
