import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import chatService from '../services/chatService';
import { useAuth } from '../context/AuthContext';
import Modal from '../components/Modal';
import { 
  FaSearch, FaRobot, FaUserEdit, FaCommentDots, FaArrowLeft, 
  FaPaperPlane, FaWhatsapp, FaBrain, FaPlus, FaRocket, FaRedo, 
  FaTrash, FaCheckCircle, FaExclamationTriangle, FaShieldAlt, FaSpinner, FaEdit,
  FaTerminal, FaChevronDown, FaChevronUp
} from 'react-icons/fa';
import './ChatCenter.css';

export default function ChatCenter() {
  const { isAdmin } = useAuth();

  const [conversations, setConversations] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeConvId, setActiveConvId] = useState(null);
  const [activeConversation, setActiveConversation] = useState(null);
  const [chatInput, setChatInput] = useState('');
  const [sendingChat, setSendingChat] = useState(false);
  const [curtisTyping, setCurtisTyping] = useState(false);
  const [simSender, setSimSender] = useState('infractor'); // 'infractor' o 'analista'
  const [loading, setLoading] = useState(true);
  
  // Modales y acciones
  const [showAddModal, setShowAddModal] = useState(false);
  const [addingNumber, setAddingNumber] = useState(false);
  const [addForm, setAddForm] = useState({
    phone: '',
    name: '',
    initial_mode: 'bot',
    send_opening_message: true,
    custom_opening_text: ''
  });

  // Modal Editar Contacto / Número
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingContact, setEditingContact] = useState(false);
  const [editForm, setEditForm] = useState({ phone: '', titular: '' });

  const [startingBot, setStartingBot] = useState(false);
  const [deliveryNotice, setDeliveryNotice] = useState(null);
  const [feedbackModal, setFeedbackModal] = useState({
    isOpen: false,
    title: '',
    type: 'info',
    message: '',
    details: ''
  });

  // Consola de Logs del Sistema
  const [showLogConsole, setShowLogConsole] = useState(false);
  const [systemLogs, setSystemLogs] = useState([]);
  const [logFilter, setLogFilter] = useState('');
  const logEndRef = useRef(null);

  const chatEndRef = useRef(null);
  const prevUnreadRef = useRef({});

  const playNotificationSound = () => {
    const audio = new Audio("data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU"+Array(300).join("A"));
    audio.play().catch(() => {});
  };

  const getMediaUrl = (url) => {
    if (!url) return '';
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) {
      return url;
    }
    const backendBase = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '');
    return `${backendBase}${url}`;
  };

  const fetchConversations = async (isPolling = false) => {
    try {
      if (!isPolling) setLoading(true);
      const res = await chatService.getAllConversations();
      const newConvs = res.data.data || [];
      setConversations(newConvs);
      
      // Sonido de alerta al detectar nuevos mensajes del infractor
      let newMessagesDetected = false;
      newConvs.forEach(conv => {
        const prevUnread = prevUnreadRef.current[conv.id] || 0;
        if (conv.unread_count > prevUnread) {
          newMessagesDetected = true;
        }
        prevUnreadRef.current[conv.id] = conv.unread_count;
      });

      if (newMessagesDetected && isPolling) {
        playNotificationSound();
      }
      
      // Si hay una conversación activa, actualizar sus mensajes
      if (activeConvId) {
        const chatRes = await chatService.getConversation(activeConvId);
        setActiveConversation(chatRes.data);
      } else if (!isPolling && newConvs.length > 0) {
        // Seleccionar automáticamente la primera (Curtis Holmes si es admin)
        handleSelectConversation(newConvs[0]);
      }
      
    } catch (e) {
      console.error("Error fetching conversations:", e);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations();
    const interval = setInterval(() => fetchConversations(true), 2500);
    return () => clearInterval(interval);
  }, [activeConvId]);

  // Polling de logs del sistema cuando la consola está abierta
  const fetchSystemLogs = async () => {
    try {
      const res = await chatService.getSystemLogs(200, logFilter);
      setSystemLogs(res.data?.logs || []);
    } catch (e) { /* silencioso */ }
  };

  useEffect(() => {
    if (showLogConsole) {
      fetchSystemLogs();
      const logInterval = setInterval(fetchSystemLogs, 3000);
      return () => clearInterval(logInterval);
    }
  }, [showLogConsole, logFilter]);

  useEffect(() => {
    if (logEndRef.current && showLogConsole) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [systemLogs]);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeConversation?.messages, curtisTyping]);

  const handleSelectConversation = async (conv) => {
    setActiveConvId(conv.reporte_id);
    setDeliveryNotice(null);
    try {
      const chatRes = await chatService.getConversation(conv.reporte_id);
      setActiveConversation(chatRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  // Enviar mensaje en chat normal (Analista vía WhatsApp)
  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || sendingChat || !activeConvId) return;
    setSendingChat(true);
    setDeliveryNotice(null);
    try {
      const res = await chatService.sendMessage(activeConvId, chatInput.trim());
      setChatInput('');
      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);

      if (res.data?.whatsapp_sent === false && res.data?.whatsapp_detail) {
        setDeliveryNotice({
          type: 'warning',
          text: 'Mensaje guardado localmente, pero no pudo entregarse por WhatsApp.',
          detail: res.data.whatsapp_detail
        });
        setFeedbackModal({
          isOpen: true,
          title: 'Aviso de Entrega de WhatsApp',
          type: 'warning',
          message: 'El mensaje se guardó en Net Holmes, pero Meta no pudo entregarlo al destinatario.',
          details: res.data.whatsapp_detail
        });
      }
    } catch (error) {
      console.error("Error sending chat", error);
      setDeliveryNotice({
        type: 'error',
        text: 'Error al enviar mensaje.',
        detail: error.response?.data?.detail || error.message
      });
      setFeedbackModal({
        isOpen: true,
        title: 'Error de Envío',
        type: 'error',
        message: 'No se pudo procesar el envío del mensaje.',
        details: error.response?.data?.detail || error.message
      });
    } finally {
      setSendingChat(false);
    }
  };

  // Enviar mensaje en simulación @curtis_holmes
  const handleSendCurtisSimulation = async (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || sendingChat || curtisTyping) return;
    
    const textToSend = chatInput.trim();
    setChatInput('');
    setSendingChat(true);
    setCurtisTyping(true);

    try {
      const res = await chatService.sendCurtisMessage(
        textToSend, 
        simSender, 
        simSender === 'analista' ? 'seller' : 'honeypot'
      );

      // Si el backend reporta error de DeepSeek/LLM, mostrar modal informativo
      if (res?.data?.llm_error) {
        setFeedbackModal({
          isOpen: true,
          title: 'Aviso del Motor de IA (DeepSeek)',
          type: 'error',
          message: 'Falla al conectar con DeepSeek API',
          details: `${res.data.llm_error}. Se utilizó una respuesta contextual de respaldo.`
        });
      }

      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);
    } catch (error) {
      console.error("Error sending curtis message", error);
      const errMsg = error.response?.data?.detail || error.message || "Error al enviar mensaje de simulación";
      setFeedbackModal({
        isOpen: true,
        title: 'Error de Simulación',
        type: 'error',
        message: 'No se pudo enviar el mensaje al simulador',
        details: errMsg
      });
    } finally {
      setSendingChat(false);
      setCurtisTyping(false);
    }
  };

  // Reiniciar simulación de Curtis
  const handleResetCurtis = async () => {
    try {
      await chatService.resetCurtis();
      if (activeConvId) {
        const chatRes = await chatService.getConversation(activeConvId);
        setActiveConversation(chatRes.data);
      }
    } catch (error) {
      console.error("Error resetting curtis simulation", error);
    }
  };

  // Dar orden de arrancar al bot
  const handleStartBot = async () => {
    if (!activeConvId || startingBot) return;
    setStartingBot(true);
    try {
      const res = await chatService.startBot(activeConvId);
      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);

      setFeedbackModal({
        isOpen: true,
        title: 'Orden de Arranque Ejecutada',
        type: res.data?.whatsapp_sent ? 'success' : 'warning',
        message: res.data?.message || 'El bot ha sido activado.',
        details: res.data?.whatsapp_detail || 'El bot está en escucha activa para responder de forma autónoma.'
      });
    } catch (error) {
      console.error("Error starting bot", error);
      setFeedbackModal({
        isOpen: true,
        title: 'Error al Iniciar Bot',
        type: 'error',
        message: 'No se pudo activar el bot para este contacto.',
        details: error.response?.data?.detail || error.message
      });
    } finally {
      setStartingBot(false);
    }
  };


  // Agregar número temporal
  const handleAddTemporaryNumber = async (e) => {
    e.preventDefault();
    if (!addForm.phone?.trim()) return;
    setAddingNumber(true);
    try {
      const res = await chatService.addTemporaryNumber(addForm);
      setShowAddModal(false);
      setAddForm({
        phone: '',
        name: '',
        initial_mode: 'bot',
        send_opening_message: true,
        custom_opening_text: ''
      });

      await fetchConversations();
      if (res.data?.reporte_id) {
        setActiveConvId(res.data.reporte_id);
        const chatRes = await chatService.getConversation(res.data.reporte_id);
        setActiveConversation(chatRes.data);
      }

      setFeedbackModal({
        isOpen: true,
        title: 'Número Temporal Agregado',
        type: res.data?.whatsapp_sent ? 'success' : 'info',
        message: res.data?.message || 'El número se incorporó al Chat Center.',
        details: res.data?.whatsapp_detail || 'Ya puedes interactuar con el contacto o dejar que el bot opere.'
      });
    } catch (error) {
      console.error("Error adding temporary number", error);
      setFeedbackModal({
        isOpen: true,
        title: 'Error al Agregar Número',
        type: 'error',
        message: 'No se pudo registrar el número de prueba.',
        details: error.response?.data?.detail || error.message
      });
    } finally {
      setAddingNumber(false);
    }
  };

  // Abrir modal de edición con los datos del chat activo
  const openEditModal = () => {
    if (!activeConversation) return;
    setEditForm({
      phone: activeConversation.whatsapp_phone || activeConversation.reporte?.telefono_publico || '',
      titular: activeConversation.reporte?.titular_cuenta || ''
    });
    setShowEditModal(true);
  };

  // Guardar corrección de número / contacto
  const handleSaveEditedContact = async (e) => {
    if (e) e.preventDefault();
    if (!editForm.phone?.trim() || !activeConvId) return;
    setEditingContact(true);
    try {
      const res = await chatService.editContact(activeConvId, editForm);
      setShowEditModal(false);
      await fetchConversations(true);
      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);

      setFeedbackModal({
        isOpen: true,
        title: 'Número / Contacto Actualizado',
        type: 'success',
        message: res.data?.message || 'El número se corrigió con éxito.',
        details: `Nuevo teléfono configurado: ${res.data?.whatsapp_phone}`
      });
    } catch (error) {
      console.error("Error editing contact", error);
      setFeedbackModal({
        isOpen: true,
        title: 'Error al Corregir Número',
        type: 'error',
        message: 'No se pudo actualizar el número.',
        details: error.response?.data?.detail || error.message
      });
    } finally {
      setEditingContact(false);
    }
  };

  const toggleChatMode = async () => {
    if (!activeConversation || !activeConvId) return;
    try {
      const newMode = activeConversation.is_bot_active ? 'analista' : 'bot';
      const res = await chatService.toggleMode(activeConvId, newMode);
      setActiveConversation(prev => ({ ...prev, is_bot_active: res.data.is_bot_active, mode: res.data.mode }));
    } catch (error) {
      console.error("Error toggling mode", error);
    }
  };

  const parseEntities = (entitiesStr) => {
    if (!entitiesStr) return null;
    try { return JSON.parse(entitiesStr); } catch { return null; }
  };

  const filteredConvs = conversations.filter(c => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      (c.whatsapp_phone && c.whatsapp_phone.toLowerCase().includes(term)) ||
      (c.reporte?.titular_cuenta && c.reporte.titular_cuenta.toLowerCase().includes(term)) ||
      (c.reporte?.marca_afectada && c.reporte.marca_afectada.toLowerCase().includes(term))
    );
  });

  const isCurtisActive = Boolean(activeConversation?.is_curtis || activeConversation?.whatsapp_phone === '@curtis_holmes');

  if (loading) return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;

  return (
    <div className="page-container fade-in">
      {/* Header General */}
      <div className="detail-header" style={{ marginBottom: '16px' }}>
        <div className="detail-title-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
          <div className="title-left" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className="avatar-large" style={{ background: 'linear-gradient(135deg, #10b981, #3b82f6)' }}><FaCommentDots /></div>
            <div>
              <h2 style={{ margin: 0 }}>Chat Center Global</h2>
              <p className="text-secondary" style={{ margin: '4px 0 0 0' }}>Monitoreo de Honeypots, Webhook de WhatsApp y Simulador Curtis</p>
            </div>
          </div>

          {isAdmin && (
            <div style={{ display: 'flex', gap: '10px' }}>
              <button 
                type="button" 
                className="btn-primary" 
                onClick={() => setShowAddModal(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px', borderRadius: '8px', cursor: 'pointer' }}
              >
                <FaPlus /> Agregar Número Temporal
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="chat-center-container">
        {/* Left Panel: Conversation List */}
        <div className="glass-card chat-list-panel">
          <div className="chat-list-header">
            <div style={{ position: 'relative' }}>
              <FaSearch style={{ position: 'absolute', top: '12px', left: '15px', color: 'rgba(255,255,255,0.5)' }} />
              <input 
                type="text" 
                className="chat-search-input" 
                placeholder="Buscar por teléfono o titular..." 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{ paddingLeft: '40px' }}
              />
            </div>
          </div>
          
          <div className="chat-list">
            {filteredConvs.map(conv => {
              const isCurtis = conv.is_curtis || conv.whatsapp_phone === '@curtis_holmes';
              return (
                <div 
                  key={conv.id} 
                  className={`chat-list-item ${activeConvId === conv.reporte_id ? 'active' : ''} ${isCurtis ? 'curtis-item' : ''}`}
                  onClick={() => handleSelectConversation(conv)}
                >
                  <div className="chat-item-header">
                    <div className="chat-item-title">
                      {isCurtis ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#c084fc', fontWeight: 'bold' }}>
                          <FaRobot color="#c084fc" /> @curtis_holmes
                        </span>
                      ) : (
                        <span>{conv.reporte?.titular_cuenta || conv.whatsapp_phone || 'Contacto'}</span>
                      )}
                      {conv.unread_count > 0 && <span className="unread-badge">{conv.unread_count}</span>}
                    </div>
                    <span className="chat-item-date">
                      {conv.last_message?.timestamp ? new Date(conv.last_message.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ''}
                    </span>
                  </div>

                  <div className="chat-item-body">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.8rem', color: isCurtis ? '#c084fc' : 'var(--accent)' }}>
                        {isCurtis ? 'Simulador Honeypot' : (conv.reporte?.marca_afectada || 'WhatsApp')}
                      </span>
                      {isCurtis ? (
                        <span className="curtis-badge"><FaShieldAlt size={9} /> Simulador</span>
                      ) : (
                        <span className="bot-badge" style={{ background: conv.is_bot_active ? 'var(--success)' : 'var(--warning)', color: '#000' }}>
                          {conv.is_bot_active ? 'Bot' : 'Manual'}
                        </span>
                      )}
                    </div>
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.8, fontSize: '0.85rem' }}>
                      {conv.last_message?.text || 'Sin mensajes aún'}
                    </div>
                  </div>
                </div>
              );
            })}

            {filteredConvs.length === 0 && (
              <div className="empty-state" style={{ marginTop: '20px' }}>
                <p>No se encontraron conversaciones.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Active Chat */}
        <div className="chat-active-panel">
          {activeConversation ? (
            <>
              {/* Header del Chat Activo */}
              <div className="chat-active-header">
                <div>
                  <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {isCurtisActive ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: '#c084fc' }}>
                        <FaRobot size={22} /> @curtis_holmes
                        <span className="curtis-badge"><FaShieldAlt size={10} /> Chat de Prueba Oficial</span>
                      </span>
                    ) : (
                      <>
                        <FaWhatsapp color="#25D366" />
                        <span>{activeConversation.whatsapp_phone || activeConversation.reporte?.telefono_publico || 'Chat WhatsApp'}</span>
                        {isAdmin && (
                          <button
                            type="button"
                            onClick={openEditModal}
                            title="Editar número o titular si fue ingresado con error"
                            style={{ 
                              background: 'rgba(16, 197, 201, 0.12)', 
                              border: '1px solid rgba(16, 197, 201, 0.35)', 
                              color: 'var(--accent-primary)', 
                              cursor: 'pointer', 
                              padding: '4px 10px', 
                              borderRadius: '6px', 
                              fontSize: '0.78rem',
                              fontWeight: '600',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px'
                            }}
                          >
                            <FaEdit size={12} /> Corregir Número
                          </button>
                        )}
                      </>
                    )}
                  </h3>
                  <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '2px' }}>
                    {isCurtisActive 
                      ? 'Simulador de Honeypot y extracción NLP (Solo Administradores)'
                      : `${activeConversation.reporte?.titular_cuenta ? `${activeConversation.reporte.titular_cuenta} • ` : ''}Vinculado a Reporte #${activeConvId} • ${activeConversation.reporte?.marca_afectada || 'Inbound'}`}
                  </small>
                </div>
                
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  {/* Botón Reiniciar para Curtis */}
                  {isCurtisActive && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleResetCurtis}
                      title="Borrar mensajes y reiniciar simulación"
                      style={{ padding: '8px 14px', borderRadius: '20px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', cursor: 'pointer' }}
                    >
                      <FaRedo /> Reiniciar Chat
                    </button>
                  )}

                  {/* Botón Dar Orden de Arrancar al Bot para WhatsApp real */}
                  {!isCurtisActive && isAdmin && (
                    <button
                      type="button"
                      className="btn-start-bot"
                      onClick={handleStartBot}
                      disabled={startingBot}
                      title="Envía el mensaje de apertura por WhatsApp y activa al bot para responder automáticamente"
                    >
                      <FaRocket /> {startingBot ? 'Arrancando...' : 'Dar Orden de Arrancar al Bot'}
                    </button>
                  )}

                  {/* Toggle Bot / Manual */}
                  <button 
                    type="button"
                    className={`switch-btn ${!activeConversation.is_bot_active ? 'manual' : ''}`} 
                    onClick={toggleChatMode}
                    style={{ padding: '8px 15px', borderRadius: '20px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    title={activeConversation.is_bot_active ? 'Haz clic para pausar el bot y chatear tú como analista humano' : 'Haz clic para activar el bot automático'}
                  >
                    {activeConversation.is_bot_active ? (
                      <><FaUserEdit /> Cambiar a Modo Manual (Analista)</>
                    ) : (
                      <><FaRobot /> Activar Bot Autónomo</>
                    )}
                  </button>
                </div>
              </div>

              {/* Banner de Aviso de Entrega WhatsApp */}
              {deliveryNotice && (
                <div style={{
                  padding: '10px 16px',
                  backgroundColor: deliveryNotice.type === 'error' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                  borderBottom: `1px solid ${deliveryNotice.type === 'error' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`,
                  color: deliveryNotice.type === 'error' ? '#f87171' : '#facc15',
                  fontSize: '0.88rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <strong>{deliveryNotice.text}</strong>
                    {deliveryNotice.detail && <p style={{ margin: '2px 0 0 0', opacity: 0.9, fontSize: '0.82rem' }}>{deliveryNotice.detail}</p>}
                  </div>
                  <button type="button" onClick={() => setDeliveryNotice(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>✕</button>
                </div>
              )}

              {/* Chips de Escenarios Rápidos para @curtis_holmes */}
              {isCurtisActive && (
                <div className="scenario-chips-container">
                  <span style={{ fontSize: '0.75rem', color: '#c084fc', fontWeight: 'bold' }}>
                    {simSender === 'analista' ? 'Preguntar al Vendedor:' : 'Simular como Vendedor:'}
                  </span>
                  {simSender === 'analista' ? (
                    <>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("¡Hola! ¿Cuánto salen las zapatillas y qué talles tenés disponibles?")}
                      >
                        👟 Preguntar Precio y Talles
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("Dale me sirve, ¿qué Alias o CBU me pasás para hacerte la transferencia ahora?")}
                      >
                        💳 Pedir Alias / CBU
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("¿Por qué zona están para pasar a retirar en persona hoy? ¿Tienen local?")}
                      >
                        📍 Preguntar Zona / Showroom
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("¿Hacés envíos en el día por motomensajería a Capital Federal?")}
                      >
                        📦 Consultar Envíos
                      </button>
                    </>
                  ) : (
                    <>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("Tengo zapatillas Nike a $65.000, transferime al alias fer.indumentaria.mp o CVU 0000003100012345678901")}
                      >
                        🏷️ Pasar Alias y CBU ($65.000)
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("Estamos en Flores cerca de Nazca y Avellaneda, atendemos de lunes a sábado.")}
                      >
                        📍 Showroom en Flores
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("¿Quién te dio mi número? ¿Sos de la policía o por qué tantas preguntas?")}
                      >
                        🛡️ Prueba Hostil / Evasiva
                      </button>
                      <button 
                        type="button" 
                        className="scenario-chip"
                        onClick={() => setChatInput("Mi DNI es 37.890.123 y el CUIT 20-37890123-4. Transferime y te las separo.")}
                      >
                        🆔 DNI y CUIT
                      </button>
                    </>
                  )}
                </div>
              )}

              {/* Contenedor de Mensajes */}
              <div className="chat-active-messages">
                {activeConversation.messages && activeConversation.messages.length > 0 ? (
                  activeConversation.messages.map((msg, idx) => {
                    const entities = parseEntities(msg.extracted_entities);
                    const isCurtisMessage = isCurtisActive && msg.sender === 'bot';
                    const isInfractor = msg.sender === 'infractor';

                    return (
                      <div key={msg.id || idx} style={{ alignSelf: isInfractor ? 'flex-start' : 'flex-end', maxWidth: '82%', width: 'fit-content' }}>
                        <div 
                          className={`chat-bubble ${isCurtisMessage ? 'curtis-ai' : (isInfractor ? 'infractor' : 'bot')}`}
                          style={{
                            padding: '12px 16px',
                            borderRadius: '12px',
                            borderBottomLeftRadius: isInfractor ? '2px' : '12px',
                            borderBottomRightRadius: !isInfractor ? '2px' : '12px',
                          }}
                        >
                          <strong style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: '12px',
                            fontSize: '0.75rem', 
                            marginBottom: '6px', 
                            color: isCurtisMessage 
                              ? '#c084fc' 
                              : msg.sender === 'analista' 
                                ? '#38bdf8' 
                                : (msg.sender === 'bot' ? '#10C5C9' : '#f59e0b') 
                          }}>
                            <span>
                              {isCurtisMessage 
                                ? '🤖 CURTIS HOLMES (HONEYPOT AI)' 
                                : msg.sender === 'bot' 
                                  ? '🤖 HONEYPOT AI' 
                                  : msg.sender === 'analista' 
                                    ? '👤 ANALISTA' 
                                    : isCurtisActive 
                                      ? '🎭 VENDEDOR SIMULADO' 
                                      : '👤 CONTACTO / INFRACTOR'}
                            </span>
                            <span style={{ opacity: 0.65, fontWeight: 'normal', fontSize: '0.72rem' }}>
                              {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('es-AR', {hour: '2-digit', minute:'2-digit'}) : ''}
                            </span>
                          </strong>
                          <span style={{ lineHeight: '1.5', fontSize: '0.94rem', display: 'block', wordBreak: 'break-word', color: 'inherit' }}>
                            {msg.text || msg.content}
                          </span>

                          {/* Renderizado de Multimedia Comprimida (Imágenes, Audios, Videos, Docs) */}
                          {msg.media_url && (
                            <div className="chat-media-attachment" style={{ marginTop: '8px' }}>
                              {/* Imagen con compresión WebP */}
                              {/\.(webp|jpg|jpeg|png|gif)$/i.test(msg.media_url) && (
                                <img 
                                  src={getMediaUrl(msg.media_url)} 
                                  alt="Evidencia adjunta" 
                                  style={{ 
                                    maxWidth: '100%', 
                                    maxHeight: '280px', 
                                    borderRadius: '8px', 
                                    objectFit: 'cover', 
                                    cursor: 'pointer',
                                    border: '1px solid rgba(255, 255, 255, 0.15)',
                                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                                    display: 'block'
                                  }} 
                                  onClick={() => window.open(getMediaUrl(msg.media_url), '_blank')}
                                  title="Click para ver evidencia en tamaño completo"
                                />
                              )}

                              {/* Audio o Nota de Voz con reproductor nativo */}
                              {/\.(ogg|mp3|wav|m4a|aac)$/i.test(msg.media_url) && (
                                <div style={{ background: 'rgba(0,0,0,0.12)', padding: '6px 8px', borderRadius: '8px' }}>
                                  <audio 
                                    controls 
                                    src={getMediaUrl(msg.media_url)} 
                                    style={{ width: '100%', minWidth: '220px', height: '36px' }} 
                                  />
                                </div>
                              )}

                              {/* Video comprimido */}
                              {/\.(mp4|mov|webm|3gp)$/i.test(msg.media_url) && (
                                <video 
                                  controls 
                                  src={getMediaUrl(msg.media_url)} 
                                  preload="metadata"
                                  style={{ 
                                    maxWidth: '100%', 
                                    maxHeight: '260px', 
                                    borderRadius: '8px', 
                                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                                    display: 'block'
                                  }} 
                                />
                              )}

                              {/* Documento o Archivo */}
                              {!/\.(webp|jpg|jpeg|png|gif|ogg|mp3|wav|m4a|aac|mp4|mov|webm|3gp)$/i.test(msg.media_url) && (
                                <a 
                                  href={getMediaUrl(msg.media_url)} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  style={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center', 
                                    gap: '6px', 
                                    padding: '6px 12px', 
                                    background: 'rgba(255, 255, 255, 0.1)', 
                                    borderRadius: '6px', 
                                    color: 'inherit', 
                                    textDecoration: 'underline',
                                    fontSize: '0.85rem' 
                                  }}
                                >
                                  📄 Abrir Documento Adjunto
                                </a>
                              )}
                            </div>
                          )}
                        </div>
                        
                        {/* Insignias de Extracción NLP */}
                        {entities && Object.keys(entities).length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '5px', paddingLeft: '8px' }}>
                            <FaBrain size={11} color="#facc15" title="Extraído automáticamente por NLP" style={{ alignSelf: 'center' }} />
                            {Object.entries(entities).map(([key, val]) => (
                              <span key={key} style={{ 
                                fontSize: '0.72rem', 
                                background: 'rgba(250, 204, 21, 0.12)', 
                                color: '#facc15', 
                                padding: '2px 8px', 
                                borderRadius: '4px', 
                                border: '1px solid rgba(250, 204, 21, 0.3)',
                                fontWeight: '500' 
                              }} title={String(val)}>
                                {key.replace(/_/g, ' ')}: <strong>{String(val).substring(0, 25)}</strong>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="chat-bubble system" style={{ textAlign: 'center', opacity: 0.6, alignSelf: 'center' }}>
                    No hay mensajes en esta conversación.
                  </div>
                )}

                {/* Indicador de escritura de Curtis */}
                {curtisTyping && (
                  <div className="typing-indicator">
                    <FaRobot style={{ marginRight: '4px' }} /> Curtis Holmes está analizando y respondiendo
                    <span className="typing-dot"></span>
                    <span className="typing-dot"></span>
                    <span className="typing-dot"></span>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Área de Entrada / Input */}
              {isCurtisActive ? (
                /* Input especial para el simulador @curtis_holmes */
                <div className="chat-active-input">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Rol activo en simulación:</span>
                    <div className="sim-sender-toggle" style={{ display: 'flex', gap: '6px' }}>
                      <button 
                        type="button" 
                        className={`sim-sender-btn ${simSender === 'analista' ? 'active' : ''}`}
                        onClick={() => setSimSender('analista')}
                        title="Tú investigas como Analista y DeepSeek responde como Vendedor infractor"
                      >
                        🎭 Bot es Vendedor Simulado (Tú investigas)
                      </button>
                      <button 
                        type="button" 
                        className={`sim-sender-btn ${simSender === 'infractor' ? 'active' : ''}`}
                        onClick={() => setSimSender('infractor')}
                        title="Tú eres el vendedor y DeepSeek responde como Analista Honeypot"
                      >
                        🤖 Bot es Analista Honeypot (Tú vendes)
                      </button>
                    </div>
                  </div>

                  <form onSubmit={handleSendCurtisSimulation} style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="text"
                      className="input-field"
                      placeholder={
                        simSender === 'analista' 
                          ? "Pregúntale al vendedor simulado (ej: ¿Cuánto salen las zapas? ¿Tenés CBU o Alias?)..." 
                          : "Escribe como vendedor informal para que Curtis te interrogue (ej: Sale $65.000, alias calzados.mp)..."
                      }
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      disabled={sendingChat || curtisTyping}
                      style={{ flex: 1, padding: '12px 15px' }}
                    />
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={sendingChat || curtisTyping || !chatInput.trim()}
                      style={{ padding: '12px 22px', display: 'flex', alignItems: 'center', gap: '8px', background: 'linear-gradient(135deg, #9333ea, #3b82f6)' }}
                    >
                      <FaPaperPlane /> {sendingChat ? '...' : 'Enviar'}
                    </button>
                  </form>
                </div>
              ) : (
                /* Modo WhatsApp Real: Input siempre disponible + banner de estado del bot */
                <div className="chat-active-input">
                  {activeConversation.is_bot_active && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', padding: '8px 14px', background: 'rgba(16, 197, 201, 0.08)', border: '1px solid rgba(16, 197, 201, 0.25)', borderRadius: '8px', fontSize: '0.82rem' }}>
                      <span style={{ color: 'var(--text-primary)' }}>
                        🤖 <strong>Bot Autónomo Activo:</strong> Responderá solo a los mensajes entrantes. Puedes enviar un mensaje manual en cualquier momento.
                      </span>
                      <button 
                        type="button" 
                        onClick={toggleChatMode} 
                        style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', fontWeight: '600', fontSize: '0.82rem', textDecoration: 'underline' }}
                      >
                        Pausar Bot (Modo Manual)
                      </button>
                    </div>
                  )}

                  {deliveryNotice && (
                    <div style={{
                      padding: '10px 14px',
                      marginBottom: '10px',
                      borderRadius: '8px',
                      backgroundColor: deliveryNotice.type === 'error' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                      border: `1px solid ${deliveryNotice.type === 'error' ? 'rgba(239, 68, 68, 0.35)' : 'rgba(234, 179, 8, 0.35)'}`,
                      color: deliveryNotice.type === 'error' ? '#f87171' : '#facc15',
                      fontSize: '0.86rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div>
                        <strong>⚠️ {deliveryNotice.text}</strong>
                        {deliveryNotice.detail && <p style={{ margin: '3px 0 0 0', opacity: 0.95, fontSize: '0.82rem' }}>{deliveryNotice.detail}</p>}
                      </div>
                      <button type="button" onClick={() => setDeliveryNotice(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1rem', padding: '0 4px' }}>✕</button>
                    </div>
                  )}
                  <form onSubmit={handleSendChat} style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="text"
                      className="input-field"
                      placeholder={activeConversation.is_bot_active ? "Escribe un mensaje para intervenir por WhatsApp..." : "Escribe un mensaje manual (se enviará directamente por WhatsApp)..."}
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      disabled={sendingChat}
                      style={{ flex: 1, padding: '12px 15px' }}
                    />
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={sendingChat || !chatInput.trim()}
                      style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                      <FaPaperPlane /> {sendingChat ? '...' : 'Enviar'}
                    </button>
                  </form>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <FaCommentDots className="empty-icon" style={{ fontSize: '4rem', opacity: 0.2, marginBottom: '20px' }} />
              <h3>Ningún chat seleccionado</h3>
              <p>Selecciona una conversación del panel izquierdo o inicia el simulador @curtis_holmes.</p>
            </div>
          )}
        </div>
      </div>

      {/* ─── Consola de Logs del Sistema ──────────────────────────── */}
      <div style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        transition: 'height 0.3s ease',
        height: showLogConsole ? '280px' : '36px',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#0d1117',
        borderTop: '2px solid #30363d',
        boxShadow: showLogConsole ? '0 -4px 20px rgba(0,0,0,0.5)' : 'none',
      }}>
        {/* Barra de título de la consola */}
        <div
          onClick={() => setShowLogConsole(!showLogConsole)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 16px',
            cursor: 'pointer',
            backgroundColor: '#161b22',
            borderBottom: showLogConsole ? '1px solid #30363d' : 'none',
            userSelect: 'none',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#58a6ff', fontSize: '0.82rem', fontWeight: 'bold' }}>
            <FaTerminal size={12} />
            Consola del Sistema
            <span style={{ 
              fontSize: '0.7rem', 
              padding: '1px 6px', 
              borderRadius: '8px', 
              backgroundColor: systemLogs.length > 0 ? 'rgba(88, 166, 255, 0.15)' : 'rgba(110,118,129,0.15)',
              color: systemLogs.length > 0 ? '#58a6ff' : '#6e7681',
            }}>
              {systemLogs.length} logs
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {showLogConsole && (
              <input
                type="text"
                placeholder="Filtrar logs..."
                value={logFilter}
                onChange={e => setLogFilter(e.target.value)}
                onClick={e => e.stopPropagation()}
                style={{
                  background: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '4px',
                  color: '#c9d1d9',
                  padding: '2px 8px',
                  fontSize: '0.75rem',
                  width: '180px',
                  outline: 'none',
                }}
              />
            )}
            {showLogConsole ? <FaChevronDown size={12} style={{ color: '#6e7681' }} /> : <FaChevronUp size={12} style={{ color: '#6e7681' }} />}
          </div>
        </div>

        {/* Cuerpo de logs */}
        {showLogConsole && (
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '8px 14px',
            fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
            fontSize: '0.72rem',
            lineHeight: '1.55',
            color: '#c9d1d9',
          }}>
            {systemLogs.length === 0 ? (
              <div style={{ color: '#6e7681', textAlign: 'center', paddingTop: '30px' }}>
                No hay logs del sistema aún. Los logs de WhatsApp, Bot, Webhook y NLP aparecerán aquí en tiempo real.
              </div>
            ) : (
              systemLogs.map((log, i) => {
                let color = '#c9d1d9';
                if (log.includes('✅') || log.includes('Éxito') || log.includes('exitosa')) color = '#3fb950';
                else if (log.includes('❌') || log.includes('Error') || log.includes('error')) color = '#f85149';
                else if (log.includes('⚠️') || log.includes('Warning')) color = '#d29922';
                else if (log.includes('🔄') || log.includes('🤖')) color = '#a5d6ff';
                else if (log.includes('[WhatsApp')) color = '#3fb950';
                else if (log.includes('[Curtis')) color = '#d2a8ff';
                else if (log.includes('[Honeypot')) color = '#f0883e';
                else if (log.includes('[NLP')) color = '#79c0ff';
                else if (log.includes('[Webhook')) color = '#56d4dd';

                return (
                  <div key={i} style={{ color, whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginBottom: '1px' }}>
                    {log}
                  </div>
                );
              })
            )}
            <div ref={logEndRef} />
          </div>
        )}
      </div>

      {/* Modal: Agregar Número Temporal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Agregar Número Temporal para Pruebas"
        footer={
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', width: '100%' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowAddModal(false)}
              disabled={addingNumber}
              style={{ padding: '8px 18px' }}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleAddTemporaryNumber}
              disabled={addingNumber || !addForm.phone?.trim()}
              style={{ padding: '8px 20px', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {addingNumber ? <><FaSpinner className="spin" /> Guardando...</> : 'Iniciar Conversación'}
            </button>
          </div>
        }
      >
        <form onSubmit={handleAddTemporaryNumber} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontWeight: 'bold' }}>Número de WhatsApp Destino *</label>
            <input 
              type="text" 
              className="input-field" 
              placeholder="Ej: +54 9 11 1234-5678 o 5491112345678" 
              value={addForm.phone}
              onChange={e => setAddForm(prev => ({ ...prev, phone: e.target.value }))}
              style={{ width: '100%' }}
              required
            />
            <small style={{ color: 'var(--text-secondary)' }}>Número con código de país (se sanitiza automáticamente a dígitos).</small>
            <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="scenario-chip"
                onClick={() => setAddForm(prev => ({ ...prev, phone: '+595971682207', name: 'Oliver Personal (+595971682207)' }))}
              >
                🇵🇾 Oliver Personal (+595971682207)
              </button>
              <button
                type="button"
                className="scenario-chip"
                onClick={() => setAddForm(prev => ({ ...prev, phone: '+595984716528', name: 'Sujeto de Prueba (+595984716528)' }))}
              >
                🇵🇾 Sujeto (+595984716528)
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontWeight: 'bold' }}>Nombre o Etiqueta (Opcional)</label>
            <input 
              type="text" 
              className="input-field" 
              placeholder="Ej: Sujeto de Prueba / Mi Celular / Vendedor Marketplace" 
              value={addForm.name}
              onChange={e => setAddForm(prev => ({ ...prev, name: e.target.value }))}
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontWeight: 'bold' }}>Modo Inicial</label>
            <div style={{ display: 'flex', gap: '15px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                <input 
                  type="radio" 
                  name="initial_mode" 
                  value="bot" 
                  checked={addForm.initial_mode === 'bot'} 
                  onChange={() => setAddForm(prev => ({ ...prev, initial_mode: 'bot' }))} 
                />
                🤖 Bot Automático (Curtis AI)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                <input 
                  type="radio" 
                  name="initial_mode" 
                  value="analista" 
                  checked={addForm.initial_mode === 'analista'} 
                  onChange={() => setAddForm(prev => ({ ...prev, initial_mode: 'analista' }))} 
                />
                👤 Control Manual (Analista)
              </label>
            </div>
          </div>

          <div style={{ backgroundColor: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 'bold' }}>
              <input 
                type="checkbox" 
                checked={addForm.send_opening_message} 
                onChange={e => setAddForm(prev => ({ ...prev, send_opening_message: e.target.checked }))} 
              />
              🚀 Enviar mensaje inicial de apertura por WhatsApp ahora
            </label>

            {addForm.send_opening_message && (
              <div style={{ marginTop: '10px' }}>
                <input 
                  type="text" 
                  className="input-field" 
                  placeholder="Dejar vacío para el mensaje estándar del bot..." 
                  value={addForm.custom_opening_text}
                  onChange={e => setAddForm(prev => ({ ...prev, custom_opening_text: e.target.value }))}
                  style={{ width: '100%' }}
                />
                <small style={{ color: 'var(--text-secondary)' }}>
                  Por defecto: "¡Hola! Buenas tardes, vi tu contacto/publicación. ¿Tenés stock disponible para entrega inmediata? ¿Cómo coordinamos el pago?"
                </small>
              </div>
            )}
          </div>
        </form>
      </Modal>

      {/* Modal: Editar Número o Titular de Contacto */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Editar Número o Titular de Contacto"
        footer={
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', width: '100%' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowEditModal(false)}
              disabled={editingContact}
              style={{ padding: '8px 18px' }}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSaveEditedContact}
              disabled={editingContact || !editForm.phone?.trim()}
              style={{ padding: '8px 22px', display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              {editingContact ? <><FaSpinner className="spin" /> Guardando...</> : 'Guardar Cambios'}
            </button>
          </div>
        }
      >
        <form onSubmit={handleSaveEditedContact} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontWeight: 'bold' }}>
              Número de Teléfono WhatsApp (E.164 con código de país) *
            </label>
            <input
              type="text"
              className="input-field"
              placeholder="Ej: +595984716528 o +5491133334444"
              value={editForm.phone}
              onChange={e => setEditForm(prev => ({ ...prev, phone: e.target.value }))}
              required
              style={{ width: '100%' }}
            />
            <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '5px' }}>
              💡 Si el usuario lo metió mal (ej: sin código de país o con un dígito errado), corrígelo aquí para que las respuestas se sincronicen por WhatsApp.
            </small>
            <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="scenario-chip"
                onClick={() => setEditForm(prev => ({ ...prev, phone: '+595971682207', titular: prev.titular || 'Oliver Personal' }))}
              >
                🇵🇾 Oliver Personal (+595971682207)
              </button>
              <button
                type="button"
                className="scenario-chip"
                onClick={() => setEditForm(prev => ({ ...prev, phone: '+595984716528', titular: prev.titular || 'Sujeto de Prueba' }))}
              >
                🇵🇾 Sujeto (+595984716528)
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '6px', fontWeight: 'bold' }}>
              Nombre o Titular Identificado
            </label>
            <input
              type="text"
              className="input-field"
              placeholder="Ej: Vendedor Calzados o Juan Pérez"
              value={editForm.titular}
              onChange={e => setEditForm(prev => ({ ...prev, titular: e.target.value }))}
              style={{ width: '100%' }}
            />
          </div>
        </form>
      </Modal>

      {/* Modal: Feedback y Notificaciones */}
      <Modal
        isOpen={feedbackModal.isOpen}
        onClose={() => setFeedbackModal(prev => ({ ...prev, isOpen: false }))}
        title={feedbackModal.title}
        footer={
          <button
            type="button"
            className="btn-primary"
            onClick={() => setFeedbackModal(prev => ({ ...prev, isOpen: false }))}
            style={{ padding: '8px 22px' }}
          >
            Aceptar
          </button>
        }
      >
        <div style={{ textAlign: 'center', padding: '15px 10px' }}>
          {feedbackModal.type === 'success' ? (
            <FaCheckCircle style={{ fontSize: '3rem', color: '#22c55e', marginBottom: '14px' }} />
          ) : feedbackModal.type === 'error' ? (
            <FaExclamationTriangle style={{ fontSize: '3rem', color: '#ef4444', marginBottom: '14px' }} />
          ) : (
            <FaRocket style={{ fontSize: '3rem', color: '#3b82f6', marginBottom: '14px' }} />
          )}

          <h4 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>{feedbackModal.message}</h4>
          {feedbackModal.details && (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', wordBreak: 'break-word', marginTop: '6px' }}>
              {feedbackModal.details}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}

