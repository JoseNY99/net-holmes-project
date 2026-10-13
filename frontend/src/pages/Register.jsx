// Página de Registro — crear nueva cuenta
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FaUserPlus } from 'react-icons/fa';
import { register as registerService } from '../services/authService';
import { useAuth } from '../context/AuthContext';
import './Register.css';

export default function Register() {
  const [form, setForm] = useState({
    nombre: '',
    apellido: '',
    celular: '',
    ci_ruc: '',
    correo: '',
    password: '',
    confirmPassword: '',
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Actualizar campos del formulario
  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  // Validación del lado del cliente
  const validate = () => {
    if (!form.nombre.trim() || !form.apellido.trim() || !form.correo.trim() || !form.password) {
      return 'Completa todos los campos obligatorios';
    }
    // Validar formato de correo
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(form.correo)) {
      return 'Ingresa un correo electrónico válido';
    }
    if (form.password.length < 6) {
      return 'La contraseña debe tener al menos 6 caracteres';
    }
    if (form.password !== form.confirmPassword) {
      return 'Las contraseñas no coinciden';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      // Enviar datos sin confirmPassword, mapeando ci_ruc a ci
      const { confirmPassword, ci_ruc, ...rest } = form;
      const data = { ...rest, ci: ci_ruc };
      await registerService(data);
      setSuccess('¡Cuenta creada exitosamente! Redirigiendo al login...');
      setTimeout(() => navigate('/login', { replace: true }), 2000);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Error al crear la cuenta. Intenta de nuevo.';
      setError(typeof msg === 'string' ? msg : 'Error en el registro');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="register-page">
      <div className="register-card glass-card">
        <div className="register-card__header">
          <h1 className="register-card__title">Crear Cuenta</h1>
          <p className="register-card__subtitle">Completa los datos para solicitar acceso</p>
        </div>

        {error && <div className="error-message" style={{ marginBottom: 20 }}>{error}</div>}
        {success && <div className="success-message" style={{ marginBottom: 20 }}>{success}</div>}

        <form className="register-form" onSubmit={handleSubmit}>
          <div className="register-form__grid">
            <div className="register-form__group">
              <label className="register-form__label">
                Nombre <span className="register-form__required">*</span>
              </label>
              <input
                type="text"
                name="nombre"
                className="input-field"
                value={form.nombre}
                onChange={handleChange}
                placeholder="Tu nombre"
                autoFocus
              />
            </div>

            <div className="register-form__group">
              <label className="register-form__label">
                Apellido <span className="register-form__required">*</span>
              </label>
              <input
                type="text"
                name="apellido"
                className="input-field"
                value={form.apellido}
                onChange={handleChange}
                placeholder="Tu apellido"
              />
            </div>

            <div className="register-form__group">
              <label className="register-form__label">Celular</label>
              <input
                type="tel"
                name="celular"
                className="input-field"
                value={form.celular}
                onChange={handleChange}
                placeholder="+591 70000000"
              />
            </div>

            <div className="register-form__group">
              <label className="register-form__label">CI / RUC</label>
              <input
                type="text"
                name="ci_ruc"
                className="input-field"
                value={form.ci_ruc}
                onChange={handleChange}
                placeholder="Documento de identidad"
              />
            </div>

            <div className="register-form__group register-form__group--full">
              <label className="register-form__label">
                Correo electrónico <span className="register-form__required">*</span>
              </label>
              <input
                type="email"
                name="correo"
                className="input-field"
                value={form.correo}
                onChange={handleChange}
                placeholder="tu@correo.com"
                autoComplete="email"
              />
            </div>

            <div className="register-form__group">
              <label className="register-form__label">
                Contraseña <span className="register-form__required">*</span>
              </label>
              <input
                type="password"
                name="password"
                className="input-field"
                value={form.password}
                onChange={handleChange}
                placeholder="Mín. 6 caracteres"
                autoComplete="new-password"
              />
            </div>

            <div className="register-form__group">
              <label className="register-form__label">
                Confirmar <span className="register-form__required">*</span>
              </label>
              <input
                type="password"
                name="confirmPassword"
                className="input-field"
                value={form.confirmPassword}
                onChange={handleChange}
                placeholder="Repetir contraseña"
                autoComplete="new-password"
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary register-form__submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" />
                Registrando...
              </>
            ) : (
              'Crear Cuenta'
            )}
          </button>
        </form>

        <p className="register-card__footer">
          ¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link>
        </p>
      </div>
    </div>
  );
}
