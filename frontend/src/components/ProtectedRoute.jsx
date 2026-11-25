// Ruta Protegida — requiere autenticación y opcionalmente rol de admin
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children, adminOnly = false, clientAllowed = false }) {
  const { isAuthenticated, isAdmin, isClient, loading } = useAuth();

  // Mostrar spinner mientras verifica sesión
  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '80vh',
      }}>
        <div className="spinner spinner--dark" style={{ width: 40, height: 40 }} />
      </div>
    );
  }

  // Redirigir si no está autenticado
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (isClient && !clientAllowed) {
    return <Navigate to="/seizure-reports" replace />;
  }

  // Redirigir si requiere admin y no lo es
  if (adminOnly && !isAdmin) {
    return <Navigate to={isClient ? '/seizure-reports' : '/dashboard'} replace />;
  }

  return children;
}
