import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import chatService from '../services/chatService';
import { useAuth } from '../context/AuthContext';
import Modal from '../components/Modal';
import { 
  FaSearch, FaRobot, FaUserEdit, FaCommentDots, FaArrowLeft, 
  FaPaperPlane, FaWhatsapp, FaBrain, FaPlus, FaRocket, FaRedo, 
  FaTrash, FaCheckCircle, FaExclamationTriangle, FaShieldAlt, FaSpinner 
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

  const [startingBot, setStartingBot] = useState(false);
  const [deliveryNotice, setDeliveryNotice] = useState(null);
  const [feedbackModal, setFeedbackModal] = useState({
    isOpen: false,
    title: '',
    type: 'info',
    message: '',
    details: ''
  });

  const chatEndRef = useRef(null);
  const prevUnreadRef = useRef({});

  const playNotificationSound = () => {
    const audio = new Audio("data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU"+Array(300).join("A"));
    audio.play().catch(() => {});
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
    const interval = setInterval(() => fetchConversations(true), 4000);
    return () => clearInterval(interval);
  }, [activeConvId]);

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
      }
    } catch (error) {
      console.error("Error sending chat", error);
      setDeliveryNotice({
        type: 'error',
        text: 'Error al enviar mensaje.',
        detail: error.response?.data?.detail || error.message
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

    if (simSender === 'infractor') {
      setCurtisTyping(true);
    }

    try {
      await chatService.sendCurtisMessage(textToSend, simSender);
      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);
    } catch (error) {
      console.error("Error sending curtis message", error);
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
                        {activeConversation.whatsapp_phone || activeConversation.reporte?.titular_cuenta || 'Chat WhatsApp'}
                      </>
                    )}
                  </h3>
                  <small style={{ color: 'var(--text-secondary)' }}>
                    {isCurtisActive 
                      ? 'Simulador de Honeypot y extracción NLP (Solo Administradores)'
                      : `Vinculado a Reporte #${activeConvId} • ${activeConversation.reporte?.marca_afectada || 'Inbound'}`}
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
                    style={{ padding: '8px 15px', borderRadius: '20px' }}
                  >
                    {activeConversation.is_bot_active ? <><FaRobot/> Tomar Control (Manual)</> : <><FaUserEdit/> Reactivar Bot</>}
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
                  <span style={{ fontSize: '0.75rem', color: '#c084fc', fontWeight: 'bold' }}>Simular rápido:</span>
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
                    onClick={() => setChatInput("Hola! ¿Por qué zona están para retirar en persona hoy? ¿Tienen showroom o local en Flores?")}
                  >
                    📍 Pedir Retiro en Local
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
                    onClick={() => setChatInput("Mi DNI es 37.890.123 y el CUIT 20-37890123-4. ¿Cuánto sale el envío a Capital?")}
                  >
                    🆔 DNI y CUIT
                  </button>
                </div>
              )}

              {/* Contenedor de Mensajes */}
              <div className="chat-active-messages">
                {activeConversation.messages && activeConversation.messages.length > 0 ? (
                  activeConversation.messages.map((msg, idx) => {
                    const entities = parseEntities(msg.extracted_entities);
                    const isCurtisMessage = isCurtisActive && msg.sender === 'bot';

                    return (
                      <div key={msg.id || idx} style={{ alignSelf: msg.sender === 'infractor' ? 'flex-start' : 'flex-end', maxWidth: '80%' }}>
                        <div className={`chat-bubble ${msg.sender === 'bot' || msg.sender === 'analista' ? 'bot' : 'infractor'}`} style={{ 
                          background: isCurtisMessage
                            ? 'linear-gradient(135deg, rgba(147, 51, 234, 0.25), rgba(59, 130, 246, 0.25))'
                            : msg.sender === 'analista' 
                              ? 'rgba(52, 152, 219, 0.18)' 
                              : (msg.sender === 'bot' ? 'rgba(90, 46, 152, 0.25)' : 'rgba(255,255,255,0.06)'),
                          border: isCurtisMessage
                            ? '1px solid rgba(168, 85, 247, 0.5)'
                            : msg.sender === 'analista' 
                              ? '1px solid rgba(52, 152, 219, 0.4)' 
                              : (msg.sender === 'bot' ? '1px solid rgba(90, 46, 152, 0.4)' : '1px solid rgba(255,255,255,0.1)'),
                          padding: '12px 16px',
                          borderRadius: '12px',
                          borderBottomLeftRadius: msg.sender === 'infractor' ? '2px' : '12px',
                          borderBottomRightRadius: (msg.sender === 'bot' || msg.sender === 'analista') ? '2px' : '12px',
                        }}>
                          <strong style={{ 
                            display: 'block', 
                            fontSize: '0.75rem', 
                            marginBottom: '6px', 
                            color: isCurtisMessage 
                              ? '#c084fc' 
                              : msg.sender === 'analista' 
                                ? '#3498db' 
                                : (msg.sender === 'bot' ? '#9b66d9' : 'var(--text-secondary)') 
                          }}>
                            {isCurtisMessage 
                              ? '🤖 CURTIS HOLMES (HONEYPOT AI)' 
                              : msg.sender === 'bot' 
                                ? '🤖 HONEYPOT AI' 
                                : msg.sender === 'analista' 
                                  ? '👤 ANALISTA' 
                                  : isCurtisActive 
                                    ? '🎭 VENDEDOR SIMULADO' 
                                    : '🎯 INFRACTOR'}
                            <span style={{ opacity: 0.6, marginLeft: '8px', fontWeight: 'normal' }}>
                              {new Date(msg.timestamp).toLocaleTimeString('es-AR', {hour: '2-digit', minute:'2-digit'})}
                            </span>
                          </strong>
                          <span style={{ lineHeight: '1.45', fontSize: '0.92rem' }}>{msg.text || msg.content}</span>
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
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Hablar en simulación como:</span>
                    <div className="sim-sender-toggle">
                      <button 
                        type="button" 
                        className={`sim-sender-btn ${simSender === 'infractor' ? 'active' : ''}`}
                        onClick={() => setSimSender('infractor')}
                      >
                        🎭 Vendedor / Infractor (para que el Bot responda)
                      </button>
                      <button 
                        type="button" 
                        className={`sim-sender-btn ${simSender === 'analista' ? 'active' : ''}`}
                        onClick={() => setSimSender('analista')}
                      >
                        👤 Analista
                      </button>
                    </div>
                  </div>

                  <form onSubmit={handleSendCurtisSimulation} style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="text"
                      className="input-field"
                      placeholder={simSender === 'infractor' ? "Escribe como vendedor para que Curtis Holmes te extraiga datos..." : "Escribe como analista..."}
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
              ) : !activeConversation.is_bot_active ? (
                /* Modo Manual para WhatsApp real */
                <div className="chat-active-input">
                  <form onSubmit={handleSendChat} style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="text"
                      className="input-field"
                      placeholder="Escribe un mensaje manual (se enviará directamente por WhatsApp)..."
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
              ) : (
                /* Modo Bot Automático para WhatsApp real */
                <div className="chat-active-input" style={{ textAlign: 'center' }}>
                  <div className="chat-bot-active-banner">
                    🤖 El bot está activo respondiendo automáticamente. Cambia a modo manual para intervenir o haz clic en <strong>"Dar Orden de Arrancar al Bot"</strong> para enviarle un nuevo gancho.
                  </div>
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
            <div style={{ marginTop: '6px' }}>
              <button
                type="button"
                className="scenario-chip"
                onClick={() => setAddForm(prev => ({ ...prev, phone: '+595984716528', name: 'Sujeto de Prueba (+595984716528)' }))}
              >
                📲 Usar número de prueba (+595984716528)
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

