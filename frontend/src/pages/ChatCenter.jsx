import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import chatService from '../services/chatService';
import { FaSearch, FaRobot, FaUserEdit, FaCommentDots, FaArrowLeft, FaPaperPlane, FaWhatsapp, FaBrain } from 'react-icons/fa';
import './ChatCenter.css';

export default function ChatCenter() {
  const [conversations, setConversations] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeConvId, setActiveConvId] = useState(null);
  const [activeConversation, setActiveConversation] = useState(null);
  const [chatInput, setChatInput] = useState('');
  const [sendingChat, setSendingChat] = useState(false);
  const [loading, setLoading] = useState(true);
  
  const chatEndRef = useRef(null);
  // Ref to store previous unread counts to detect new messages
  const prevUnreadRef = useRef({});

  const playNotificationSound = () => {
    // Sonido simple de beep en base64
    const audio = new Audio("data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU"+Array(300).join("A"));
    audio.play().catch(e => console.log("Audio play failed (maybe auto-play policy)"));
  };

  const fetchConversations = async (isPolling = false) => {
    try {
      if (!isPolling) setLoading(true);
      const res = await chatService.getAllConversations();
      const newConvs = res.data.data;
      setConversations(newConvs);
      
      // Detect new unread messages for sound alert
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
      
      // If there's an active conversation, fetch its latest messages too
      if (activeConvId) {
        const chatRes = await chatService.getConversation(activeConvId);
        setActiveConversation(chatRes.data);
      }
      
    } catch (e) {
      console.error("Error fetching conversations:", e);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations();
    const interval = setInterval(() => fetchConversations(true), 5000);
    return () => clearInterval(interval);
  }, [activeConvId]);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeConversation?.messages]);

  const handleSelectConversation = async (conv) => {
    setActiveConvId(conv.reporte_id); // getConversation takes reporte_id
    try {
      const chatRes = await chatService.getConversation(conv.reporte_id);
      setActiveConversation(chatRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || sendingChat || !activeConvId) return;
    setSendingChat(true);
    try {
      await chatService.sendMessage(activeConvId, chatInput.trim());
      setChatInput('');
      const chatRes = await chatService.getConversation(activeConvId);
      setActiveConversation(chatRes.data);
    } catch (error) {
      console.error("Error sending chat", error);
    } finally {
      setSendingChat(false);
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

  if (loading) return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;

  return (
    <div className="page-container fade-in">
      <div className="detail-header">
        <div className="detail-title-row">
          <div className="title-left">
            <div className="avatar-large"><FaCommentDots /></div>
            <div>
              <h2>Chat Center Global</h2>
              <p className="text-secondary">Monitoreo de Honeypots y Webhook de WhatsApp</p>
            </div>
          </div>
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
            {filteredConvs.map(conv => (
              <div 
                key={conv.id} 
                className={`chat-list-item ${activeConvId === conv.reporte_id ? 'active' : ''}`}
                onClick={() => handleSelectConversation(conv)}
              >
                <div className="chat-item-header">
                  <div className="chat-item-title">
                    {conv.reporte?.titular_cuenta || conv.whatsapp_phone || 'Desconocido'}
                    {conv.unread_count > 0 && <span className="unread-badge">{conv.unread_count}</span>}
                  </div>
                  <span className="chat-item-date">
                    {conv.last_message?.timestamp ? new Date(conv.last_message.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ''}
                  </span>
                </div>
                <div className="chat-item-body">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--accent)' }}>{conv.reporte?.marca_afectada}</span>
                    <span className="bot-badge" style={{ background: conv.is_bot_active ? 'var(--success)' : 'var(--warning)', color: '#000' }}>
                      {conv.is_bot_active ? 'Bot' : 'Manual'}
                    </span>
                  </div>
                  <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.8 }}>
                    {conv.last_message?.text || 'No hay mensajes'}
                  </div>
                </div>
              </div>
            ))}
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
              <div className="chat-active-header">
                <div>
                  <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {activeConversation.whatsapp_phone ? <><FaWhatsapp color="#25D366" /> {activeConversation.whatsapp_phone}</> : 'Chat Interno'}
                  </h3>
                  <small style={{ color: 'var(--text-secondary)' }}>Vinculado a Reporte #{activeConvId}</small>
                </div>
                
                <button 
                  className={`switch-btn ${!activeConversation.is_bot_active ? 'manual' : ''}`} 
                  onClick={toggleChatMode}
                  style={{ padding: '8px 15px', borderRadius: '20px' }}
                >
                  {activeConversation.is_bot_active ? <><FaRobot/> Tomar Control (Manual)</> : <><FaUserEdit/> Reactivar Bot</>}
                </button>
              </div>

              <div className="chat-active-messages">
                {activeConversation.messages && activeConversation.messages.length > 0 ? (
                  activeConversation.messages.map((msg, idx) => {
                    const entities = parseEntities(msg.extracted_entities);
                    return (
                      <div key={msg.id || idx} style={{ alignSelf: msg.sender === 'infractor' ? 'flex-start' : 'flex-end', maxWidth: '80%' }}>
                        <div className={`chat-bubble ${msg.sender === 'bot' || msg.sender === 'analista' ? 'bot' : 'infractor'}`} style={{ 
                          background: msg.sender === 'analista' ? 'rgba(52, 152, 219, 0.15)' : (msg.sender === 'bot' ? 'rgba(90, 46, 152, 0.2)' : 'rgba(255,255,255,0.05)'),
                          border: msg.sender === 'analista' ? '1px solid rgba(52, 152, 219, 0.4)' : (msg.sender === 'bot' ? '1px solid rgba(90, 46, 152, 0.4)' : '1px solid rgba(255,255,255,0.1)'),
                          padding: '12px 16px',
                          borderRadius: '12px',
                          borderBottomLeftRadius: msg.sender === 'infractor' ? '2px' : '12px',
                          borderBottomRightRadius: (msg.sender === 'bot' || msg.sender === 'analista') ? '2px' : '12px',
                        }}>
                          <strong style={{ display: 'block', fontSize: '0.75rem', marginBottom: '6px', color: msg.sender === 'analista' ? '#3498db' : (msg.sender === 'bot' ? '#9b66d9' : 'var(--text-secondary)') }}>
                            {msg.sender === 'bot' ? '🤖 HONEYPOT AI' : msg.sender === 'analista' ? '👤 ANALISTA (TÚ)' : '🎯 INFRACTOR'}
                            <span style={{ opacity: 0.6, marginLeft: '8px', fontWeight: 'normal' }}>{new Date(msg.timestamp).toLocaleTimeString('es-AR', {hour: '2-digit', minute:'2-digit'})}</span>
                          </strong>
                          <span style={{ lineHeight: '1.4', fontSize: '0.9rem' }}>{msg.text || msg.content}</span>
                        </div>
                        
                        {/* LLM Extraction Badges */}
                        {entities && Object.keys(entities).length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px', paddingLeft: '8px' }}>
                            <FaBrain size={10} color="var(--warning)" title="Extraído por NLP" />
                            {Object.entries(entities).map(([key, val]) => (
                              <span key={key} style={{ fontSize: '0.7rem', background: 'rgba(255,215,0,0.15)', color: 'var(--warning)', padding: '2px 6px', borderRadius: '4px', border: '1px solid rgba(255,215,0,0.3)' }} title={String(val)}>
                                {key.replace('_', ' ')}: {String(val).substring(0, 20)}
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
                <div ref={chatEndRef} />
              </div>

              {!activeConversation.is_bot_active ? (
                <div className="chat-active-input">
                  <form onSubmit={handleSendChat} style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="text"
                      className="input-field"
                      placeholder="Escribe un mensaje como analista (se enviará por WhatsApp)..."
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
                <div className="chat-active-input" style={{ textAlign: 'center' }}>
                  <div className="chat-bot-active-banner">
                    🤖 El bot está respondiendo automáticamente. Cambia a modo manual para intervenir.
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <FaCommentDots className="empty-icon" style={{ fontSize: '4rem', opacity: 0.2, marginBottom: '20px' }} />
              <h3>Ningún chat seleccionado</h3>
              <p>Selecciona una conversación del panel izquierdo para monitorear o intervenir.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
