// Gestor de Marcas — CRUD completo de marcas y productos (solo admin)
import { useState, useEffect, useCallback } from 'react';
import {
  FaPlus,
  FaPen,
  FaPowerOff,
  FaTrash,
  FaShieldAlt,
  FaBoxOpen,
} from 'react-icons/fa';
import {
  getBrands,
  createBrand,
  updateBrand,
  toggleBrandStatus,
  deleteBrand,
  addProduct,
  updateProduct,
  deleteProduct,
  toggleProduct,
} from '../services/brandService';
import DataTable from '../components/DataTable';
import Modal from '../components/Modal';
import BrandForm from '../components/BrandForm';
import './BrandsManager.css';

import { getCronStatus } from '../services/cronService';

export default function BrandsManager() {
  // Estado principal
  const [brands, setBrands] = useState([]);
  const [filter, setFilter] = useState('todas');
  const [loading, setLoading] = useState(false);
  const [expandedBrand, setExpandedBrand] = useState(null);
  const [cronRunning, setCronRunning] = useState(false);

  // Estados de modales
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showProductModal, setShowProductModal] = useState(false);

  // Datos temporales para edición
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productForm, setProductForm] = useState({ nombre: '', descripcion: '' });
  const [formLoading, setFormLoading] = useState(false);

  // Cargar estado del cron y marcas
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const cronRes = await getCronStatus();
      setCronRunning(cronRes.data.is_running);
    } catch (e) {
      console.warn("Warning: Cron no está disponible", e);
    }
    
    try {
      const estado = filter === 'todas' ? undefined : filter;
      const response = await getBrands(estado);
      setBrands(response.data);
    } catch {
      setBrands([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchData();
    // Fetch cron status periodically
    const interval = setInterval(async () => {
      try {
        const cronRes = await getCronStatus();
        setCronRunning(cronRes.data.is_running);
      } catch (e) {}
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // === Acciones de Marcas ===

  const handleCreateBrand = async (data) => {
    setFormLoading(true);
    try {
      await createBrand(data);
      setShowCreateModal(false);
      fetchData();
    } catch (err) {
      console.error('Error al crear marca:', err);
    } finally {
      setFormLoading(false);
    }
  };

  const handleEditBrand = async (data) => {
    if (!selectedBrand) return;
    setFormLoading(true);
    try {
      await updateBrand(selectedBrand.id, data);
      setShowEditModal(false);
      setSelectedBrand(null);
      fetchData();
    } catch (err) {
      console.error('Error al actualizar marca:', err);
    } finally {
      setFormLoading(false);
    }
  };

  const handleToggleStatus = async (brand) => {
    try {
      await toggleBrandStatus(brand.id);
      fetchData();
    } catch (err) {
      console.error('Error al cambiar estado:', err);
    }
  };

  const handleDeleteBrand = async () => {
    if (!selectedBrand) return;
    setFormLoading(true);
    try {
      await deleteBrand(selectedBrand.id);
      setShowDeleteModal(false);
      setSelectedBrand(null);
      setExpandedBrand(null);
      fetchData();
    } catch (err) {
      console.error('Error al eliminar marca:', err);
    } finally {
      setFormLoading(false);
    }
  };

  // === Acciones de Productos ===

  const openAddProduct = (brand) => {
    setSelectedBrand(brand);
    setSelectedProduct(null);
    setProductForm({ nombre: '', descripcion: '' });
    setShowProductModal(true);
  };

  const openEditProduct = (brand, product) => {
    setSelectedBrand(brand);
    setSelectedProduct(product);
    setProductForm({ nombre: product.nombre, descripcion: product.descripcion || '' });
    setShowProductModal(true);
  };

  const handleProductSubmit = async (e) => {
    e.preventDefault();
    if (!productForm.nombre.trim()) return;
    setFormLoading(true);
    try {
      if (selectedProduct) {
        await updateProduct(selectedProduct.id, productForm);
      } else {
        await addProduct(selectedBrand.id, productForm);
      }
      setShowProductModal(false);
      fetchData();
    } catch (err) {
      console.error('Error con producto:', err);
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteProduct = async (productId) => {
    try {
      await deleteProduct(productId);
      fetchData();
    } catch (err) {
      console.error('Error al eliminar producto:', err);
    }
  };

  const handleToggleProductStatus = async (productId) => {
    try {
      await toggleProduct(productId);
      fetchData();
    } catch (err) {
      console.error('Error al cambiar estado del producto:', err);
    }
  };

  // Expandir/colapsar productos de una marca
  const toggleExpand = (brandId) => {
    setExpandedBrand(expandedBrand === brandId ? null : brandId);
  };

  // === Definición de Columnas ===
  const columns = [
    {
      key: 'nombre',
      label: 'Nombre',
      render: (row) => (
        <span className="brands__brand-name" onClick={() => toggleExpand(row.id)}>
          {row.nombre}
        </span>
      ),
    },
    {
      key: 'descripcion',
      label: 'Descripción',
      render: (row) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
          {row.descripcion || '—'}
        </span>
      ),
    },
    {
      key: 'estado',
      label: 'Estado',
      render: (row) => (
        <span className={row.estado === 'activa' ? 'badge-active' : 'badge-inactive'}>
          {row.estado === 'activa' ? 'Activa' : 'Inactiva'}
        </span>
      ),
    },
    {
      key: 'productos',
      label: 'Productos',
      render: (row) => (
        <span className="brands__product-count">
          {row.products?.length || 0}
        </span>
      ),
    },
    {
      key: 'acciones',
      label: 'Acciones',
      render: (row) => (
        <div className="brands__actions">
          <button
            className="brands__action-btn brands__action-btn--add"
            onClick={(e) => {
              e.stopPropagation();
              setExpandedBrand(row.id);
              openAddProduct(row);
            }}
            title="Agregar Keyword/Producto"
            disabled={cronRunning}
          >
            <FaPlus />
          </button>
          <button
            className="brands__action-btn brands__action-btn--edit"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedBrand(row);
              setShowEditModal(true);
            }}
            title="Editar"
            disabled={cronRunning}
          >
            <FaPen />
          </button>
          <button
            className="brands__action-btn brands__action-btn--toggle"
            onClick={(e) => {
              e.stopPropagation();
              handleToggleStatus(row);
            }}
            title={row.estado === 'activa' ? 'Desactivar' : 'Activar'}
            disabled={cronRunning}
          >
            <FaPowerOff />
          </button>
          <button
            className="brands__action-btn brands__action-btn--delete"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedBrand(row);
              setShowDeleteModal(true);
            }}
            title="Eliminar"
            disabled={cronRunning}
          >
            <FaTrash />
          </button>
        </div>
      ),
    },
  ];

  // Filtrar tabs
  const filters = [
    { key: 'todas', label: 'Todas' },
    { key: 'activa', label: 'Activas' },
    { key: 'inactiva', label: 'Inactivas' },
  ];

  return (
    <div className="page-container brands-manager">
      {cronRunning && (
        <div style={{background: 'rgba(192,57,43,0.1)', color: 'var(--danger)', padding: '12px', borderRadius: '8px', marginBottom: '20px', border: '1px solid rgba(192,57,43,0.3)', fontWeight: 600}}>
          ⚠️ El motor Cron está actualmente en ejecución. La edición y eliminación de marcas está bloqueada para evitar corrupciones.
        </div>
      )}

      {/* Barra superior */}
      <div className="brands__topbar">
        <h1 className="brands__title">Gestión de Marcas</h1>
        <button
          className="btn-primary brands__new-btn"
          onClick={() => setShowCreateModal(true)}
          disabled={cronRunning}
        >
          <FaPlus /> Nueva Marca
        </button>
      </div>

      {/* Filtros de estado */}
      <div className="brands__filters">
        {filters.map((f) => (
          <button
            key={f.key}
            className={`brands__filter-btn ${filter === f.key ? 'brands__filter-btn--active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Tabla de marcas o estado vacío */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <div className="spinner spinner--dark" style={{ width: 40, height: 40, margin: '0 auto' }} />
        </div>
      ) : brands.length === 0 && filter === 'todas' ? (
        <div className="glass-card brands__empty">
          <div className="brands__empty-icon">
            <FaShieldAlt />
          </div>
          <h3 className="brands__empty-title">Aún no hay marcas registradas</h3>
          <p className="brands__empty-text">
            Comienza creando tu primera marca para protegerla con Net Holmes
          </p>
          <button
            className="btn-primary"
            onClick={() => setShowCreateModal(true)}
          >
            <FaPlus /> Crear primera marca
          </button>
        </div>
      ) : (
        <>
          <DataTable
            columns={columns}
            data={brands}
            emptyMessage="No se encontraron marcas con este filtro"
            onRowClick={(row) => toggleExpand(row.id)}
          />

          {/* Productos expandidos */}
          {expandedBrand && (
            <div className="brands__products fade-in" style={{ marginTop: 16 }}>
              <div className="brands__products-header">
                <h4 className="brands__products-title">
                  <FaBoxOpen style={{ marginRight: 6 }} />
                  Productos de {brands.find((b) => b.id === expandedBrand)?.nombre}
                </h4>
                <button
                  className="btn-primary brands__add-product-btn"
                  onClick={() => openAddProduct(brands.find((b) => b.id === expandedBrand))}
                  disabled={cronRunning}
                >
                  <FaPlus /> Agregar
                </button>
              </div>

              <div className="brands__product-list">
                {(brands.find((b) => b.id === expandedBrand)?.products || []).length === 0 ? (
                  <p className="brands__no-products">Esta marca no tiene productos registrados</p>
                ) : (
                  brands
                    .find((b) => b.id === expandedBrand)
                    ?.products.map((product) => (
                      <div key={product.id} className="brands__product-item">
                        <div>
                          <div className="brands__product-name" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {product.nombre}
                            <span className={product.estado === 'activa' ? 'badge-active' : 'badge-inactive'} style={{ fontSize: '0.7rem', padding: '2px 6px' }}>
                              {product.estado === 'activa' ? 'Activa' : 'Inactiva'}
                            </span>
                          </div>
                          {product.descripcion && (
                            <div className="brands__product-desc">{product.descripcion}</div>
                          )}
                        </div>
                        <div className="brands__product-actions">
                          <button
                            className="brands__action-btn brands__action-btn--toggle"
                            onClick={() => handleToggleProductStatus(product.id)}
                            title={product.estado === 'activa' ? 'Desactivar keyword' : 'Activar keyword'}
                            disabled={cronRunning}
                          >
                            <FaPowerOff />
                          </button>
                          <button
                            className="brands__action-btn brands__action-btn--edit"
                            onClick={() =>
                              openEditProduct(
                                brands.find((b) => b.id === expandedBrand),
                                product
                              )
                            }
                            title="Editar producto"
                            disabled={cronRunning}
                          >
                            <FaPen />
                          </button>
                          <button
                            className="brands__action-btn brands__action-btn--delete"
                            onClick={() => handleDeleteProduct(product.id)}
                            title="Eliminar producto"
                            disabled={cronRunning}
                          >
                            <FaTrash />
                          </button>
                        </div>
                      </div>
                    ))
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Modal: Crear Marca */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Nueva Marca"
      >
        <BrandForm onSubmit={handleCreateBrand} loading={formLoading} />
      </Modal>

      {/* Modal: Editar Marca */}
      <Modal
        isOpen={showEditModal}
        onClose={() => {
          setShowEditModal(false);
          setSelectedBrand(null);
        }}
        title="Editar Marca"
      >
        <BrandForm
          initialData={selectedBrand}
          onSubmit={handleEditBrand}
          loading={formLoading}
        />
      </Modal>

      {/* Modal: Confirmar Eliminación */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedBrand(null);
        }}
        title="Confirmar Eliminación"
        footer={
          <>
            <button
              className="btn-ghost"
              onClick={() => {
                setShowDeleteModal(false);
                setSelectedBrand(null);
              }}
            >
              Cancelar
            </button>
            <button
              className="btn-danger"
              onClick={handleDeleteBrand}
              disabled={formLoading}
            >
              {formLoading ? (
                <>
                  <span className="spinner" />
                  Eliminando...
                </>
              ) : (
                'Eliminar'
              )}
            </button>
          </>
        }
      >
        <p className="confirm-delete__text">
          ¿Estás seguro de que deseas eliminar la marca{' '}
          <span className="confirm-delete__name">{selectedBrand?.nombre}</span>?
          Esta acción no se puede deshacer.
        </p>
      </Modal>

      {/* Modal: Agregar/Editar Producto */}
      <Modal
        isOpen={showProductModal}
        onClose={() => {
          setShowProductModal(false);
          setSelectedProduct(null);
        }}
        title={selectedProduct ? 'Editar Producto' : 'Agregar Producto'}
      >
        <form className="product-form" onSubmit={handleProductSubmit}>
          <div className="product-form__group">
            <label className="product-form__label">Nombre del Producto *</label>
            <input
              type="text"
              className="input-field"
              value={productForm.nombre}
              onChange={(e) => setProductForm({ ...productForm, nombre: e.target.value })}
              placeholder="Nombre del producto"
              required
              autoFocus
            />
          </div>
          <div className="product-form__group">
            <label className="product-form__label">Descripción</label>
            <textarea
              className="input-field"
              value={productForm.descripcion}
              onChange={(e) => setProductForm({ ...productForm, descripcion: e.target.value })}
              placeholder="Descripción del producto (opcional)"
              rows={3}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setShowProductModal(false);
                setSelectedProduct(null);
              }}
            >
              Cancelar
            </button>
            <button type="submit" className="btn-primary" disabled={formLoading}>
              {formLoading ? (
                <>
                  <span className="spinner" />
                  Guardando...
                </>
              ) : selectedProduct ? (
                'Actualizar'
              ) : (
                'Agregar'
              )}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
