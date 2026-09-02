// Componente principal de la aplicación — rutas y layout
import { Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import BrandsManager from './pages/BrandsManager';
import CronConfig from './pages/CronConfig';
import ManualScan from './pages/ManualScan';
import ScanResults from './pages/ScanResults';
import Investigation from './pages/Investigation';
import SuspectDetail from './pages/SuspectDetail';
import Reports from './pages/Reports';
import UserManagement from './pages/UserManagement';
import AdminLogs from './pages/AdminLogs';
import RedCorrelacionesPage from './pages/RedCorrelacionesPage';
import ChatCenter from './pages/ChatCenter';
import WhatsAppSettings from './pages/WhatsAppSettings';
import ScraperSettings from './pages/ScraperSettings';

import { Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';

function AppRoutes() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return <div className="page-container"><div className="spinner-container"><div className="spinner spinner--dark"></div></div></div>;
  }

  return (
    <Routes>
      <Route path="/" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />} />
      <Route path="/home" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />} />
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/register" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Register />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/brands"
        element={
          <ProtectedRoute adminOnly>
            <BrandsManager />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cron"
        element={
          <ProtectedRoute adminOnly>
            <CronConfig />
          </ProtectedRoute>
        }
      />
      <Route
        path="/scan-results"
        element={
          <ProtectedRoute>
            <ScanResults />
          </ProtectedRoute>
        }
      />
      <Route
        path="/manual-scan"
        element={
          <ProtectedRoute>
            <ManualScan />
          </ProtectedRoute>
        }
      />
      <Route
        path="/investigation"
        element={
          <ProtectedRoute>
            <Investigation />
          </ProtectedRoute>
        }
      />
      <Route
        path="/suspects/:id"
        element={
          <ProtectedRoute>
            <SuspectDetail />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <Reports />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute adminOnly>
            <UserManagement />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/logs"
        element={
          <ProtectedRoute adminOnly>
            <AdminLogs />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/whatsapp-settings"
        element={
          <ProtectedRoute adminOnly>
            <WhatsAppSettings />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/scrapers"
        element={
          <ProtectedRoute adminOnly>
            <ScraperSettings />
          </ProtectedRoute>
        }
      />
      <Route
        path="/correlations"
        element={
          <ProtectedRoute>
            <RedCorrelacionesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat"
        element={
          <ProtectedRoute>
            <ChatCenter />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Navbar />
      <main>
        <AppRoutes />
      </main>
    </AuthProvider>
  );
}
