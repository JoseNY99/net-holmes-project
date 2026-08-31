// Página de Login — iniciar sesión
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FaShieldAlt } from 'react-icons/fa';
import { useAuth } from '../context/AuthContext';
import { login as loginService } from '../services/authService';
import './Login.css';

export default function Login() {
  const [correo, setCorreo] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!correo.trim() || !password.trim()) {
      setError('Todos los campos son obligatorios');
      return;
    }

    setLoading(true);
    try {
      const response = await loginService(correo, password);
      const { access_token, user } = response.data;
      login(access_token, user);
      // La redirección ahora es manejada por AppRoutes y el useEffect
    } catch (err) {
      const msg = err.response?.data?.detail || 'Credenciales inválidas. Intenta de nuevo.';
      setError(typeof msg === 'string' ? msg : 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card glass-card">
        <div className="login-card__header">
          <div className="login-card__icon-wrapper">
            <img src="/netholmes-icon.png" alt="Net Holmes" className="login-card__logo-img" />
          </div>
          <h1 className="login-card__title">Iniciar Sesión</h1>
          <p className="login-card__subtitle">Accede a tu cuenta de Net Holmes</p>
        </div>

        {error && <div className="error-message">{error}</div>}

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-form__group">
            <label className="login-form__label">Correo electrónico</label>
            <input
              type="email"
              className="input-field"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              placeholder="tu@correo.com"
              autoComplete="email"
              autoFocus
            />
          </div>

          <div className="login-form__group">
            <label className="login-form__label">Contraseña</label>
            <input
              type="password"
              className="input-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className="btn-primary login-form__submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" />
                Ingresando...
              </>
            ) : (
              'Ingresar'
            )}
          </button>
        </form>

        <p className="login-card__footer">
          ¿No tienes cuenta? <Link to="/register">Regístrate aquí</Link>
        </p>
      </div>
    </div>
  );
}
