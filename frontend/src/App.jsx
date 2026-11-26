import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AdminAuthProvider } from './context/AdminAuthContext';
import ProtectedAdminRoute from './components/ProtectedAdminRoute';
import StudentLayout from './layouts/StudentLayout';
import AdminLayout from './layouts/AdminLayout';
import LandingShowcase from './pages/LandingShowcase';
import {
  PublicLightLayout,
  PublicAboutPage,
  PublicHelpPage,
  PublicContactPage,
  PublicLegalPage,
} from './pages/PublicPages';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import EvaluateProperty from './pages/EvaluateProperty';
import MapAnalysis from './pages/MapAnalysis';
import MyPropertiesReports from './pages/MyPropertiesReports';
import Documents from './pages/Documents';
import AccountHelp from './pages/AccountHelp';
import AdminLogin from './pages/AdminLogin';
import AdminDashboard from './pages/AdminDashboard';
import AdminUsers from './pages/AdminUsers';
import AdminEvaluations from './pages/AdminEvaluations';
import AdminDocuments from './pages/AdminDocuments';
import AdminDataModel from './pages/AdminDataModel';
import AdminGIS from './pages/AdminGIS';
import AdminAuditLogs from './pages/AdminAuditLogs';
import AdminSystemHealth from './pages/AdminSystemHealth';
import AdminSettings from './pages/AdminSettings';
import AdminSupport from './pages/AdminSupport';

export default function App() {
  return (
    <AdminAuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Showcase & Information Pages */}
          <Route path="/" element={<LandingShowcase />} />
          <Route element={<PublicLightLayout />}>
            <Route path="/about" element={<PublicAboutPage />} />
            <Route path="/help" element={<PublicHelpPage />} />
            <Route path="/contact" element={<PublicContactPage />} />
            <Route path="/privacy" element={<PublicLegalPage type="privacy" />} />
            <Route path="/terms" element={<PublicLegalPage type="terms" />} />
            <Route path="/disclaimers" element={<PublicLegalPage type="disclaimers" />} />
          </Route>

          {/* Customer Authentication & 5-Section Workspace */}
          <Route path="/login" element={<Login />} />
          <Route path="/student" element={<StudentLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="evaluate" element={<EvaluateProperty />} />
            <Route path="map" element={<MapAnalysis />} />
            <Route path="properties" element={<MyPropertiesReports />} />
            <Route path="documents" element={<Documents />} />
            <Route path="account" element={<AccountHelp />} />
            <Route path="compare" element={<MyPropertiesReports />} />
            <Route path="reports" element={<MyPropertiesReports />} />
            <Route path="saved" element={<MyPropertiesReports />} />
            <Route path="profile" element={<AccountHelp />} />
            <Route path="enquiries" element={<AccountHelp />} />
            <Route path="data-sources" element={<Navigate to="/student/evaluate" replace />} />
            <Route path="about" element={<Navigate to="/student/account" replace />} />
          </Route>

          {/* Safe alias for UI UX /app paths */}
          <Route path="/app" element={<Navigate to="/student" replace />} />
          <Route path="/app/dashboard" element={<Navigate to="/student" replace />} />
          <Route path="/app/evaluate" element={<Navigate to="/student/evaluate" replace />} />
          <Route path="/app/documents" element={<Navigate to="/student/documents" replace />} />
          <Route path="/app/properties" element={<Navigate to="/student/properties" replace />} />
          <Route path="/app/account" element={<Navigate to="/student/account" replace />} />

          {/* Protected Single Admin Login & 6-Section Console (SUPER_ADMIN & ADMIN) */}
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route
            path="/admin"
            element={
              <ProtectedAdminRoute requiredPermission="overview:view">
                <AdminLayout />
              </ProtectedAdminRoute>
            }
          >
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="dashboard" element={<AdminDashboard />} />
            <Route
              path="users"
              element={
                <ProtectedAdminRoute requiredPermission="users:view">
                  <AdminUsers />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="evaluations"
              element={
                <ProtectedAdminRoute requiredPermission="evaluations:view">
                  <AdminEvaluations />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="documents"
              element={
                <ProtectedAdminRoute requiredPermission="documents:view">
                  <AdminDocuments />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="data-model"
              element={
                <ProtectedAdminRoute requiredPermission={['models:view', 'datasets:view']}>
                  <AdminDataModel />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="gis"
              element={
                <ProtectedAdminRoute requiredPermission="gis:view">
                  <AdminGIS />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="audit"
              element={
                <ProtectedAdminRoute requiredPermission="audit:view">
                  <AdminAuditLogs />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="health"
              element={
                <ProtectedAdminRoute requiredPermission="health:view">
                  <AdminSystemHealth />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="support"
              element={
                <ProtectedAdminRoute requiredPermission="support:view">
                  <AdminSupport />
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="settings"
              element={
                <ProtectedAdminRoute requiredPermission="settings:view">
                  <AdminSettings />
                </ProtectedAdminRoute>
              }
            />
            <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AdminAuthProvider>
  );
}
