import React, { useState, useEffect, useMemo } from 'react';
import { 
  FaUserPlus, FaUserEdit, FaPowerOff, FaShieldAlt, FaCrown, FaTrashAlt, 
  FaSearch, FaFilter, FaLock, FaCheckCircle, FaExclamationTriangle, FaTimes, FaKey
} from 'react-icons/fa';
import { getUsers, createUser, updateUser, toggleUserStatus, deleteUser } from '../services/userService';
import { useAuth } from '../context/AuthContext';
import Modal from '../components/Modal';
import './UserManagement.css';

const ITEMS_PER_PAGE = 10;

export default function UserManagement() {
  const { user: currentUser, isSuperAdmin } = useAuth();
  
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [currentPage, setCurrentPage] = useState(1);
  
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  
  const [selectedUser, setSelectedUser] = useState(null);
  const [formData, setFormData] = useState({
    nombre: '', apellido: '', correo: '', celular: '', ci: '', password: '', rol: 'analista'
  });
  const [editFormData, setEditFormData] = useState({
    nombre: '', apellido: '', correo: '', celular: '', ci: '', password: '', rol: 'analista'
  });
  
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await getUsers();
      setUsers(res.data);
    } catch (err) {
      console.error("Error fetching users:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // Filter and pagination
  const filteredUsers = useMemo(() => {
    return users.filter(u => {
      const fullText = `${u.nombre} ${u.apellido} ${u.correo}`.toLowerCase();
      const matchesSearch = fullText.includes(searchTerm.toLowerCase().trim());
      const matchesRole = roleFilter === 'all' || u.rol.toLowerCase() === roleFilter.toLowerCase();
      return matchesSearch && matchesRole;
    });
  }, [users, searchTerm, roleFilter]);

  const totalPages = Math.ceil(filteredUsers.length / ITEMS_PER_PAGE) || 1;
  const paginatedUsers = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredUsers.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredUsers, currentPage]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, roleFilter]);

  const showNotification = (msg, isError = false) => {
    if (isError) {
      setErrorMsg(msg);
      setTimeout(() => setErrorMsg(''), 4000);
    } else {
      setSuccessMsg(msg);
      setTimeout(() => setSuccessMsg(''), 4000);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      await createUser(formData);
      setShowCreateModal(false);
      setFormData({ nombre: '', apellido: '', correo: '', celular: '', ci: '', password: '', rol: 'analista' });
      showNotification("¡Usuario creado exitosamente!");
      fetchUsers();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Error al crear usuario');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      const payload = {
        nombre: editFormData.nombre,
        apellido: editFormData.apellido,
        celular: editFormData.celular || null,
        ci: editFormData.ci || null,
        correo: editFormData.correo,
      };
      
      // Solo SUP_ADMIN puede cambiar el rol
      if (isSuperAdmin && editFormData.rol) {
        payload.rol = editFormData.rol;
      }
      
      // Si se especificó nueva contraseña
      if (editFormData.password && editFormData.password.trim()) {
        payload.password = editFormData.password.trim();
      }

      await updateUser(selectedUser.id, payload);
      setShowEditModal(false);
      setSelectedUser(null);
      showNotification("¡Usuario actualizado correctamente!");
      fetchUsers();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Error al actualizar usuario');
    } finally {
      setSubmitting(false);
    }
  };

  const openEdit = (u) => {
    setSelectedUser(u);
    setEditFormData({
      nombre: u.nombre || '',
      apellido: u.apellido || '',
      correo: u.correo || '',
      celular: u.celular || '',
      ci: u.ci || '',
      password: '',
      rol: u.rol || 'analista'
    });
    setErrorMsg('');
    setShowEditModal(true);
  };

  const handleToggleStatus = async (u) => {
    if (u.rol === 'sup_admin') {
      showNotification("Las cuentas SUP_ADMIN son inmunes y no pueden ser desactivadas.", true);
      return;
    }
    if (u.id === currentUser?.id) {
      showNotification("No puedes desactivar tu propia cuenta en sesión.", true);
      return;
    }
    if (u.rol === 'admin' && !isSuperAdmin) {
      showNotification("Solo un Super Administrador puede suspender a otro Administrador.", true);
      return;
    }

    try {
      await toggleUserStatus(u.id);
      showNotification(`Estado de ${u.correo} actualizado.`);
      fetchUsers();
    } catch (err) {
      showNotification(err.response?.data?.detail || "Error al cambiar estado", true);
    }
  };

  const openDelete = (u) => {
    if (u.rol === 'sup_admin') {
      showNotification("Las cuentas SUP_ADMIN están blindadas y no pueden ser eliminadas.", true);
      return;
    }
    if (u.id === currentUser?.id) {
      showNotification("No puedes eliminar tu propia cuenta en sesión.", true);
      return;
    }
    if (u.rol === 'admin' && !isSuperAdmin) {
      showNotification("Solo un Super Administrador puede eliminar a otro Administrador.", true);
      return;
    }
    setSelectedUser(u);
    setShowDeleteModal(true);
  };

  const handleDelete = async () => {
    if (!selectedUser) return;
    setSubmitting(true);
    try {
      await deleteUser(selectedUser.id);
      setShowDeleteModal(false);
      setSelectedUser(null);
      showNotification("Usuario eliminado permanentemente.");
      fetchUsers();
    } catch (err) {
      showNotification(err.response?.data?.detail || "Error al eliminar usuario", true);
    } finally {
      setSubmitting(false);
    }
  };

  const renderRoleBadge = (rol) => {
    const r = (rol || '').toLowerCase();
    if (r === 'sup_admin') {
      return (
        <span className="role-badge role-sup-admin">
          <FaCrown className="role-icon-crown" /> SUP_ADMIN
        </span>
      );
    }
    if (r === 'admin') {
      return (
        <span className="role-badge role-admin">
          <FaShieldAlt className="role-icon-admin" /> ADMIN
        </span>
      );
    }
    return (
      <span className="role-badge role-analista">
        ANALISTA
      </span>
    );
  };

  return (
    <div className="page-container fade-in">
      <div className="glass-card user-management-container">
        
        {/* Header */}
        <div className="user-management-header">
          <div className="header-title-block">
            <h2><FaShieldAlt style={{ marginRight: '10px' }}/> Administración de Accesos</h2>
            <p className="header-subtitle">Control jerárquico de roles, operadores y credenciales de seguridad</p>
          </div>
          <button className="btn-primary btn-add-user" onClick={() => {
            setFormData({ nombre: '', apellido: '', correo: '', celular: '', ci: '', password: '', rol: 'analista' });
            setErrorMsg('');
            setShowCreateModal(true);
          }}>
            <FaUserPlus /> Nuevo Usuario
          </button>
        </div>

        {/* Notificaciones */}
        {successMsg && (
          <div className="alert-banner alert-success slide-up">
            <FaCheckCircle /> {successMsg}
          </div>
        )}
        {errorMsg && (
          <div className="alert-banner alert-error slide-up">
            <FaExclamationTriangle /> {errorMsg}
          </div>
        )}

        {/* Barra de Filtros y Búsqueda */}
        <div className="user-filters-bar">
          <div className="search-box">
            <FaSearch className="search-icon" />
            <input 
              type="text" 
              className="search-input" 
              placeholder="Buscar por nombre o correo electrónico..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="clear-search-btn" onClick={() => setSearchTerm('')}>
                <FaTimes />
              </button>
            )}
          </div>

          <div className="filter-role-box">
            <FaFilter className="filter-icon" />
            <select 
              className="filter-role-select"
              value={roleFilter}
              onChange={e => setRoleFilter(e.target.value)}
            >
              <option value="all">Todos los Roles ({users.length})</option>
              <option value="sup_admin">  SUP_ADMIN</option>
              <option value="admin">  ADMIN</option>
              <option value="analista">  ANALISTA</option>
            </select>
          </div>
        </div>

        {/* Tabla de Usuarios */}
        <div className="table-responsive">
          <table className="custom-table user-table">
            <thead>
              <tr>
                <th style={{ width: '60px' }}>ID</th>
                <th>NOMBRE COMPLETO</th>
                <th>EMAIL</th>
                <th>ROL</th>
                <th>ESTADO</th>
                <th style={{ textAlign: 'center', width: '160px' }}>ACCIONES</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: '40px' }}>
                    <div className="spinner spinner--dark" style={{ margin: '0 auto' }}></div>
                  </td>
                </tr>
              ) : paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
                    No se encontraron usuarios con los filtros aplicados.
                  </td>
                </tr>
              ) : (
                paginatedUsers.map(u => {
                  const isRowSupAdmin = u.rol === 'sup_admin';
                  const isRowAdmin = u.rol === 'admin';
                  const isSelf = u.id === currentUser?.id;
                  
                  // Reglas de habilitación
                  // SUP_ADMIN: Inmune a toggle y delete
                  const canToggle = !isRowSupAdmin && !isSelf && (isSuperAdmin || !isRowAdmin);
                  // BORRADO: Exclusivo de SUP_ADMIN
                  const canDelete = isSuperAdmin && !isRowSupAdmin && !isSelf;
                  const canEdit = isSuperAdmin || (!isRowSupAdmin && (!isRowAdmin || isSelf));

                  return (
                    <tr key={u.id} className={isRowSupAdmin ? 'row-sup-admin' : ''}>
                      <td><strong>#{u.id}</strong></td>
                      <td>
                        <span className="user-fullname">{u.nombre} {u.apellido}</span>
                        {isSelf && <span className="self-badge">(Tú)</span>}
                      </td>
                      <td className="user-email-cell">{u.correo}</td>
                      <td>{renderRoleBadge(u.rol)}</td>
                      <td>
                        <span className={`status-pill ${u.is_active ? 'pill-active' : 'pill-inactive'}`}>
                          <span className="pill-dot"></span>
                          {u.is_active ? 'ACTIVO' : 'INACTIVO'}
                        </span>
                      </td>
                      <td>
                        <div className="actions-cell">
                          {/* Botón Editar */}
                          <button 
                            className="action-icon-btn btn-edit"
                            onClick={() => canEdit && openEdit(u)}
                            disabled={!canEdit}
                            title={isRowSupAdmin && !isSuperAdmin ? "Inmune: Solo SUP_ADMIN puede modificar" : "Editar Usuario"}
                          >
                            {isRowSupAdmin && !isSuperAdmin ? <FaLock /> : <FaUserEdit />}
                          </button>

                          {/* Botón Toggle Activo/Inactivo */}
                          <button 
                            className={`action-icon-btn ${u.is_active ? 'btn-toggle-on' : 'btn-toggle-off'}`}
                            onClick={() => canToggle && handleToggleStatus(u)}
                            disabled={!canToggle}
                            title={
                              isRowSupAdmin 
                                ? "Inmune: No se puede suspender al SUP_ADMIN" 
                                : isSelf 
                                ? "No puedes suspender tu propia cuenta" 
                                : isRowAdmin && !isSuperAdmin
                                ? "Solo SUP_ADMIN puede suspender administradores"
                                : u.is_active ? "Desactivar Acceso" : "Activar Acceso"
                            }
                          >
                            {isRowSupAdmin ? <FaLock size={12} /> : <FaPowerOff />}
                          </button>

                          {/* Botón Eliminar — EXCLUSIVO DE SUP_ADMIN */}
                          <button 
                            className="action-icon-btn btn-delete"
                            onClick={() => canDelete && openDelete(u)}
                            disabled={!canDelete}
                            title={
                              !isSuperAdmin
                                ? "Solo el Super Administrador (SUP_ADMIN) puede eliminar cuentas"
                                : isRowSupAdmin 
                                ? "Inmune: No se puede eliminar al SUP_ADMIN" 
                                : isSelf 
                                ? "No puedes eliminar tu propia cuenta" 
                                : "Eliminar Usuario Definitivamente"
                            }
                          >
                            {!isSuperAdmin || isRowSupAdmin ? <FaLock size={12} /> : <FaTrashAlt />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Paginación */}
        {filteredUsers.length > 0 && (
          <div className="pagination-bar">
            <span className="pagination-info">
              Mostrando {Math.min((currentPage - 1) * ITEMS_PER_PAGE + 1, filteredUsers.length)} - {Math.min(currentPage * ITEMS_PER_PAGE, filteredUsers.length)} de {filteredUsers.length} usuarios
            </span>

            <div className="pagination-controls">
              <button 
                className="page-btn" 
                onClick={() => setCurrentPage(1)} 
                disabled={currentPage === 1}
              >
                «
              </button>
              <button 
                className="page-btn" 
                onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} 
                disabled={currentPage === 1}
              >
                ‹
              </button>
              
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                <button
                  key={page}
                  className={`page-btn ${currentPage === page ? 'page-btn-active' : ''}`}
                  onClick={() => setCurrentPage(page)}
                >
                  {page}
                </button>
              ))}

              <button 
                className="page-btn" 
                onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} 
                disabled={currentPage === totalPages}
              >
                ›
              </button>
              <button 
                className="page-btn" 
                onClick={() => setCurrentPage(totalPages)} 
                disabled={currentPage === totalPages}
              >
                »
              </button>
            </div>
          </div>
        )}

        {/* Modal Crear */}
        {showCreateModal && (
          <Modal isOpen={true} title="Alta de Operador del Sistema" onClose={() => setShowCreateModal(false)}>
            <form onSubmit={handleCreate} className="user-form">
              {errorMsg && <div className="error-message">{errorMsg}</div>}
              
              <div className="form-row-2">
                <div className="form-group">
                  <label>Nombre *</label>
                  <input required className="input-field" type="text" value={formData.nombre} onChange={e => setFormData({...formData, nombre: e.target.value})} placeholder="Ej: Juan" />
                </div>
                <div className="form-group">
                  <label>Apellido *</label>
                  <input required className="input-field" type="text" value={formData.apellido} onChange={e => setFormData({...formData, apellido: e.target.value})} placeholder="Ej: Perez" />
                </div>
              </div>

              <div className="form-group">
                <label>Correo Electrónico *</label>
                <input required className="input-field" type="email" value={formData.correo} onChange={e => setFormData({...formData, correo: e.target.value})} placeholder="usuario@correo.com" />
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label>Teléfono / Celular (Opcional)</label>
                  <input className="input-field" type="text" value={formData.celular} onChange={e => setFormData({...formData, celular: e.target.value})} placeholder="+54 9 11..." />
                </div>
                <div className="form-group">
                  <label>DNI / CI (Opcional)</label>
                  <input className="input-field" type="text" value={formData.ci} onChange={e => setFormData({...formData, ci: e.target.value})} placeholder="35.123.456" />
                </div>
              </div>

              <div className="form-group">
                <label>Contraseña Provisional *</label>
                <input required className="input-field" type="password" value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} placeholder="Mínimo 6 caracteres" />
              </div>

              <div className="form-group">
                <label>Nivel de Acceso (Rol) *</label>
                <select className="input-field" value={formData.rol} onChange={e => setFormData({...formData, rol: e.target.value})}>
                  <option value="analista">  Analista OSINT (Operador)</option>
                  {isSuperAdmin && (
                    <>
                      <option value="admin">  Administrador Global</option>
                      <option value="sup_admin">  Super Administrador (SUP_ADMIN)</option>
                    </>
                  )}
                </select>
              </div>

              <div className="form-actions">
                <button type="button" className="btn-ghost" onClick={() => setShowCreateModal(false)}>Cancelar</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Creando...' : 'Crear Credenciales'}
                </button>
              </div>
            </form>
          </Modal>
        )}

        {/* Modal Editar */}
        {showEditModal && selectedUser && (
          <Modal isOpen={true} title={`Modificar Usuario #${selectedUser.id}`} onClose={() => setShowEditModal(false)}>
            <form onSubmit={handleEdit} className="user-form">
              {errorMsg && <div className="error-message">{errorMsg}</div>}
              
              <div className="form-row-2">
                <div className="form-group">
                  <label>Nombre *</label>
                  <input required className="input-field" type="text" value={editFormData.nombre} onChange={e => setEditFormData({...editFormData, nombre: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Apellido *</label>
                  <input required className="input-field" type="text" value={editFormData.apellido} onChange={e => setEditFormData({...editFormData, apellido: e.target.value})} />
                </div>
              </div>

              <div className="form-group">
                <label>Correo Electrónico</label>
                <input required className="input-field" type="email" value={editFormData.correo} onChange={e => setEditFormData({...editFormData, correo: e.target.value})} />
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label>Teléfono / Celular</label>
                  <input className="input-field" type="text" value={editFormData.celular} onChange={e => setEditFormData({...editFormData, celular: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>DNI / CI</label>
                  <input className="input-field" type="text" value={editFormData.ci} onChange={e => setEditFormData({...editFormData, ci: e.target.value})} />
                </div>
              </div>

              <div className="form-group">
                <label><FaKey style={{ marginRight: '6px' }} /> Cambiar Contraseña (Dejar en blanco para no modificar)</label>
                <input className="input-field" type="password" value={editFormData.password} onChange={e => setEditFormData({...editFormData, password: e.target.value})} placeholder="Nueva contraseña..." />
              </div>

              {isSuperAdmin && (
                <div className="form-group">
                  <label>Nivel de Acceso (Rol)</label>
                  <select className="input-field" value={editFormData.rol} onChange={e => setEditFormData({...editFormData, rol: e.target.value})}>
                    <option value="analista">  Analista OSINT</option>
                    <option value="admin">  Administrador Global</option>
                    <option value="sup_admin">  Super Administrador (SUP_ADMIN)</option>
                  </select>
                </div>
              )}

              <div className="form-actions">
                <button type="button" className="btn-ghost" onClick={() => setShowEditModal(false)}>Cancelar</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Guardando...' : 'Guardar Cambios'}
                </button>
              </div>
            </form>
          </Modal>
        )}

        {/* Modal Confirmar Eliminación */}
        {showDeleteModal && selectedUser && (
          <Modal isOpen={true} title="Confirmar Eliminación de Usuario" onClose={() => setShowDeleteModal(false)}>
            <div className="delete-modal-content">
              <div className="delete-warning-icon">
                <FaExclamationTriangle size={48} color="var(--danger)" />
              </div>
              <h4 style={{ textAlign: 'center', fontSize: '1.1rem', marginTop: '10px', color: 'var(--text-primary)' }}>
                ¿Estás seguro de que deseas eliminar este usuario?
              </h4>
              
              <div style={{ background: 'var(--bg-secondary)', padding: '14px 18px', borderRadius: '10px', border: '1px solid var(--border-color)', margin: '16px 0', width: '100%', textAlign: 'center' }}>
                <div style={{ fontSize: '1.05rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>
                  {selectedUser.nombre} {selectedUser.apellido}
                </div>
                <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginTop: '4px', fontFamily: 'monospace' }}>
                  {selectedUser.correo}
                </div>
                <div style={{ marginTop: '8px' }}>
                  {renderRoleBadge(selectedUser.rol)}
                </div>
              </div>

              <div style={{ background: 'rgba(231, 76, 60, 0.12)', border: '1px solid rgba(231, 76, 60, 0.35)', color: 'var(--danger)', padding: '10px 14px', borderRadius: '8px', fontSize: '0.86rem', fontWeight: 600, textAlign: 'center', width: '100%' }}>
                  Esta acción es permanente y no se podrá deshacer.
              </div>

              <div className="form-actions" style={{ width: '100%', marginTop: '20px' }}>
                <button type="button" className="btn-ghost" onClick={() => setShowDeleteModal(false)}>Cancelar</button>
                <button type="button" className="btn-danger" onClick={handleDelete} disabled={submitting}>
                  {submitting ? 'Eliminando...' : 'Sí, Eliminar Definitivamente'}
                </button>
              </div>
            </div>
          </Modal>
        )}

      </div>
    </div>
  );
}
