import axios from 'axios';
import { API_BASE_URL } from '../config/api';

const BASE_URL = API_BASE_URL;

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('user_access_token') || localStorage.getItem('admin_access_token');
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Properties
export const getProperties = () => api.get('/properties');
export const getProperty = (id) => api.get(`/properties/${id}`);
export const createProperty = (data) => api.post('/properties', data);
export const updateProperty = (id, data) => api.put(`/properties/${id}`, data);
export const deleteProperty = (id) => api.delete(`/properties/${id}`);
export const getDatasetRecords = (params) => api.get('/properties/dataset', { params });

// GIS
export const getPropertyGIS = (id) => api.get(`/properties/${id}/gis`);
export const getPropertyFacilities = (id) => api.get(`/properties/${id}/facilities`);
export const searchLocations = (query, limit = 8) =>
  api.get('/gis/search', { params: { q: query, limit } });
export const reverseGeocode = (lat, lon, landType = null) =>
  api.post('/reverse-geocode', { latitude: lat, longitude: lon, land_type: landType });
export const getGisConfig = () => api.get('/gis/config');

// Verification
export const getVerificationItems = (id) => api.get(`/properties/${id}/verification`);
export const updateVerificationItem = (propId, itemId, data) =>
  api.put(`/properties/${propId}/verification/${itemId}`, data);

// Evaluation
export const evaluateProperty = (data) => api.post('/evaluate', data);
export const predictPrice = (data) => api.post('/predict-price', data);

// Documents
export const uploadDocument = (propertyId, file, onProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('property_id', propertyId);
  return api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  });
};
export const getDocument = (id) => api.get(`/documents/${id}`);
export const deleteDocument = (id) => api.delete(`/documents/${id}`);

// Reports
export const generateReport = (propertyId) => api.post(`/properties/${propertyId}/report`, {}, { responseType: 'blob' });
export const getReport = (id) => api.get(`/reports/${id}`);
export const getReports = () => api.get('/reports');
export const downloadReportUrl = (id) => `${BASE_URL}/reports/${id}/download`;

// Model
export const getModelMetrics = () => api.get('/model/metrics');

// Data sources
export const getDataSources = () => api.get('/data-sources');

// Health
export const getHealth = () => api.get('/health');

// Customer Workspace & Account
export const getCustomerDashboardSummary = () => api.get('/customer/dashboard-summary');
export const getCustomerProfile = () => api.get('/customer/profile');
export const updateCustomerProfile = (data) => api.put('/customer/profile', data);
export const changeCustomerPassword = (data) => api.post('/auth/change-password', data);
export const getSavedProperties = () => api.get('/customer/saved-properties');
export const toggleSavedProperty = (propertyId, note = '') =>
  api.post('/customer/saved-properties', { property_id: propertyId, note });
export const getCustomerEnquiries = () => api.get('/customer/enquiries');
export const submitCustomerEnquiry = (data) => api.post('/customer/enquiries', data);

// User Support Tickets & Persistent Notifications
export const getUserSupportTickets = () => api.get('/customer/support/tickets');
export const getUserSupportTicket = (ticketId) => api.get(`/customer/support/tickets/${ticketId}`);
export const createUserSupportTicket = (formDataOrPayload) => {
  if (formDataOrPayload instanceof FormData) {
    return api.post('/customer/support/tickets', formDataOrPayload, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  }
  return api.post('/customer/support/tickets', formDataOrPayload);
};
export const replyUserSupportTicket = (ticketId, payload) =>
  api.post(`/customer/support/tickets/${ticketId}/reply`, payload);
export const userTicketAttachmentUrl = (ticketId) =>
  `${BASE_URL}/customer/support/tickets/${ticketId}/attachment`;
export const getUserNotifications = () => api.get('/customer/notifications');
export const markUserNotificationRead = (notificationId) =>
  api.post(`/customer/notifications/${notificationId}/read`);
export const markAllUserNotificationsRead = () => api.post('/customer/notifications/read-all');

export default api;
