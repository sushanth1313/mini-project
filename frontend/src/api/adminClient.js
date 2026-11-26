import axios from 'axios';
import { API_BASE_URL } from '../config/api';

const BASE_URL = API_BASE_URL;
export const ADMIN_TOKEN_KEY = 'admin_access_token';
export const ADMIN_PROFILE_KEY = 'admin_profile';

const adminApi = axios.create({
  baseURL: `${BASE_URL}/admin`,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

adminApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(ADMIN_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

adminApi.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status;
    const code = err?.response?.data?.code;
    if (status === 401 || (status === 403 && (code === 'ACCOUNT_INACTIVE' || code === 'FORBIDDEN'))) {
      localStorage.removeItem(ADMIN_TOKEN_KEY);
      localStorage.removeItem(ADMIN_PROFILE_KEY);
    }
    return Promise.reject(err);
  }
);

// Auth & RBAC Sessions
export const adminLogin = (username, password) =>
  adminApi.post('/auth/login', { username, password });
export const adminLogout = () => adminApi.post('/auth/logout');
export const fetchAdminSession = () => adminApi.get('/auth/session');
export const fetchAdminAccounts = () => adminApi.get('/auth/admins');
export const createAdminAccount = (payload) => adminApi.post('/auth/admins', payload);
export const updateAdminAccountStatus = (adminId, payload) =>
  adminApi.patch(`/auth/admins/${adminId}/status`, payload);
export const fetchAdminLoginHistory = () => adminApi.get('/auth/login-history');

// Overview & Platform Governance
export const fetchOverviewMetrics = () => adminApi.get('/overview/metrics');

// Platform Users
export const fetchUsers = (params = {}) => adminApi.get('/users', { params });
export const fetchUserDetail = (userId) => adminApi.get(`/users/${userId}`);
export const updateUserStatus = (userId, payload) => adminApi.patch(`/users/${userId}/status`, payload);
export const updateUserRole = (userId, payload) => adminApi.patch(`/users/${userId}/role`, payload);
export const processUserDeletion = (userId, payload) =>
  adminApi.post(`/users/${userId}/deletion-request`, payload);

// Evaluations Oversight
export const fetchAdminEvaluations = (params = {}) => adminApi.get('/evaluations', { params });
export const fetchAdminEvaluationDetail = (evalId) => adminApi.get(`/evaluations/${evalId}`);
export const flagAdminEvaluation = (evalId, payload) =>
  adminApi.post(`/evaluations/${evalId}/flag`, payload);

// Datasets
export const fetchAdminDatasets = () => adminApi.get('/datasets');
export const fetchAdminDatasetDetail = (dsId) => adminApi.get(`/datasets/${dsId}`);
export const uploadAdminDataset = (payload) => adminApi.post('/datasets/upload', payload);
export const validateAdminDataset = (dsId) => adminApi.post(`/datasets/${dsId}/validate`);
export const cleanAdminDataset = (dsId, payload = {}) => adminApi.post(`/datasets/${dsId}/clean`, payload);
export const downloadAdminDatasetCsvUrl = (dsId) => `${BASE_URL}/admin/datasets/${dsId}/download`;

// ML Models
export const fetchAdminModels = () => adminApi.get('/models');
export const fetchAdminModelJobs = () => adminApi.get('/models/jobs');
export const compareAdminModels = () => adminApi.get('/models/compare');
export const trainCandidateModel = (payload) => adminApi.post('/models/train', payload);
export const approveModelDeployment = (modelId) =>
  adminApi.post(`/models/${modelId}/approve-deployment`);
export const rollbackAdminModel = (modelId) => adminApi.post(`/models/${modelId}/rollback`);

// Support Center & Persistent Notifications
export const fetchAdminSupportTickets = (params = {}) => adminApi.get('/support/tickets', { params });
export const fetchAdminSupportTicket = (ticketId) => adminApi.get(`/support/tickets/${ticketId}`);
export const replyAdminSupportTicket = (ticketId, payload) =>
  adminApi.post(`/support/tickets/${ticketId}/reply`, payload);
export const updateAdminSupportTicketStatus = (ticketId, payload) =>
  adminApi.patch(`/support/tickets/${ticketId}/status`, payload);
export const adminSupportAttachmentUrl = (ticketId) =>
  `${BASE_URL}/admin/support/tickets/${ticketId}/attachment`;
export const fetchAdminNotifications = () => adminApi.get('/notifications');
export const markAdminNotificationRead = (notificationId) =>
  adminApi.post(`/notifications/${notificationId}/read`);
export const markAllAdminNotificationsRead = () => adminApi.post('/notifications/read-all');

// Document file download helper (authenticated)
export const downloadAdminDocumentFileUrl = (jobId, docId) =>
  `${BASE_URL}/admin/documents/${jobId}/files/${docId}`;

// GIS Monitoring
export const fetchGisOverview = () => adminApi.get('/gis/overview');
export const fetchGisLogs = (params = {}) => adminApi.get('/gis/logs', { params });
export const updateGisConfig = (payload) => adminApi.patch('/gis/config', payload);
export const clearGisCache = () => adminApi.post('/gis/cache/clear');

// Documents Governance
export const fetchAdminDocuments = (params = {}) => adminApi.get('/documents', { params });
export const fetchAdminDocumentDetail = (jobId) => adminApi.get(`/documents/${jobId}`);
export const updateDocumentVerification = (jobId, payload) =>
  adminApi.patch(`/documents/${jobId}/verification-status`, payload);
export const processDocumentDeletion = (jobId, payload) =>
  adminApi.post(`/documents/${jobId}/process-deletion`, payload);

// Reports Governance
export const fetchAdminReports = (params = {}) => adminApi.get('/reports', { params });
export const fetchAdminReportDetail = (reportId) => adminApi.get(`/reports/${reportId}`);
export const checkReportConsistency = (reportId) =>
  adminApi.post(`/reports/${reportId}/consistency-check`);
export const downloadAdminReportUrl = (reportId) => `${BASE_URL}/admin/reports/${reportId}/download`;

// Health & Audit
export const fetchSystemHealth = () => adminApi.get('/monitoring/health');
export const probeSystemHealth = () => adminApi.post('/monitoring/health/probe');
export const fetchAuditLogs = (params = {}) => adminApi.get('/audit', { params });
export const fetchAdminCustomerEnquiries = () => axios.get(`${BASE_URL}/customer/admin/enquiries`, {
  headers: { Authorization: `Bearer ${localStorage.getItem(ADMIN_TOKEN_KEY) || ''}` },
});

// System Settings & Scoring Weightage
export const fetchSystemSettings = () => adminApi.get('/settings');
export const updateSystemSettings = (payload) => adminApi.patch('/settings', payload);
export const fetchWeightages = () => adminApi.get('/weightage');
export const updateWeightages = (payload) => adminApi.post('/weightage', payload);

export default adminApi;
