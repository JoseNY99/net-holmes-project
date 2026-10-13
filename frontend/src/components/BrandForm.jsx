// Formulario de Marca — crear/editar marcas
import { useState, useEffect } from 'react';
import { FaTrash, FaPlus, FaShieldAlt } from 'react-icons/fa';
import './BrandForm.css';

const PLATFORMS = [
  { value: 'todas', label: 'Todas las Plataformas' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'mercadolibre', label: 'Mercado Libre' },
];

export default function BrandForm({ initialData, onSubmit, loading }) {
  const [nombre, setNombre] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [cuentasOficiales, setCuentasOficiales] = useState([]);
  const [nuevoHandle, setNuevoHandle] = useState('');
  const [nuevaPlataforma, setNuevaPlataforma] = useState('todas');

  // Prellenar datos si se está editando
  useEffect(() => {
    if (initialData) {
      setNombre(initialData.nombre || '');
      setDescripcion(initialData.descripcion || '');
      setCuentasOficiales(initialData.cuentas_oficiales || []);
    }
  }, [initialData]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!nombre.trim()) return;
    onSubmit({ 
      nombre: nombre.trim(), 
      descripcion: descripcion.trim(),
      cuentas_oficiales: cuentasOficiales
    });
  };

  const handleAddCuenta = () => {
    if (!nuevoHandle.trim()) return;
    setCuentasOficiales([...cuentasOficiales, {
      plataforma: nuevaPlataforma,
      handle_oficial: nuevoHandle.trim()
    }]);
    setNuevoHandle('');
  };

  const handleRemoveCuenta = (index) => {
    setCuentasOficiales(cuentasOficiales.filter((_, i) => i !== index));
  };

  return (
    <form className="brand-form" onSubmit={handleSubmit}>
      <div className="brand-form__group">
        <label className="brand-form__label">
          Nombre <span className="brand-form__required">*</span>
        </label>
        <input
          type="text"
          className="input-field"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Nombre de la marca"
          required
          autoFocus
        />
      </div>

      <div className="brand-form__group">
        <label className="brand-form__label">Descripción</label>
        <textarea
          className="input-field"
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          placeholder="Descripción de la marca (opcional)"
          rows={3}
        />
      </div>

      <div className="brand-form__section">
        <h4 className="brand-form__section-title"><FaShieldAlt /> Cuentas y Handles Oficiales (Exclusión)</h4>
        <p className="brand-form__section-help">
          Las cuentas listadas aquí serán ignoradas automáticamente por los motores de búsqueda y scrapers.
        </p>
        
        <div className="brand-form__add-cuenta">
          <select 
            className="input-field platform-select"
            value={nuevaPlataforma}
            onChange={(e) => setNuevaPlataforma(e.target.value)}
          >
            {PLATFORMS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <input 
            type="text"
            className="input-field handle-input"
            value={nuevoHandle}
            onChange={(e) => setNuevoHandle(e.target.value)}
            placeholder="Ej: @adidasar, nikestore"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleAddCuenta();
              }
            }}
          />
          <button type="button" className="btn-secondary add-btn" onClick={handleAddCuenta} disabled={!nuevoHandle.trim()}>
            <FaPlus /> Agregar
          </button>
        </div>

        {cuentasOficiales.length > 0 ? (
          <ul className="brand-form__cuentas-list">
            {cuentasOficiales.map((cuenta, idx) => (
              <li key={idx} className="brand-form__cuenta-item">
                <span className="cuenta-platform">{PLATFORMS.find(p => p.value === cuenta.plataforma)?.label}</span>
                <span className="cuenta-handle">{cuenta.handle_oficial}</span>
                <button 
                  type="button" 
                  className="btn-icon text-danger" 
                  onClick={() => handleRemoveCuenta(idx)}
                  title="Eliminar"
                >
                  <FaTrash />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted text-sm mt-2">No hay cuentas oficiales registradas para esta marca.</p>
        )}
      </div>

      <div className="brand-form__actions">
        <button type="submit" className="btn-primary" disabled={loading || !nombre.trim()}>
          {loading ? (
            <>
              <span className="spinner" />
              Guardando...
            </>
          ) : (
            initialData ? 'Actualizar Marca' : 'Crear Marca'
          )}
        </button>
      </div>
    </form>
  );
}
