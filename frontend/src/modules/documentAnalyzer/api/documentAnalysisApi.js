import axios from 'axios';
import { API_BASE_URL } from '../../../config/api';

const BASE_URL = API_BASE_URL;

const docApi = axios.create({
  baseURL: `${BASE_URL}/document-analysis`,
  timeout: 120000,
});

function buildRoleHeaders() {
  const adminToken = localStorage.getItem('admin_access_token');
  const userToken = localStorage.getItem('user_access_token');
  const token = userToken || adminToken;
  const userRole = localStorage.getItem('user_role') || (adminToken ? 'admin' : 'user');
  const headers = {
    'X-User-Role': userRole,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export function hasDocumentAnalyzerAuthToken() {
  return Boolean(localStorage.getItem('user_access_token') || localStorage.getItem('admin_access_token'));
}

export async function downloadDocumentAnalysisPdf(analysisId) {
  const response = await docApi.get(`/${analysisId}/report/pdf`, {
    headers: buildRoleHeaders(),
    responseType: 'blob',
  });
  const blobUrl = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `AI_Land_Due_Diligence_Report_${analysisId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1500);
}

export async function getDocumentAnalyzerHealth() {
  const { data } = await docApi.get('/health', { headers: buildRoleHeaders() });
  return data;
}

export async function listDocumentAnalyses(propertyId = '') {
  const params = propertyId ? { property_id: propertyId } : {};
  const { data } = await docApi.get('', { params, headers: buildRoleHeaders() });
  return data;
}

export async function fetchAnalysisByProperty(propertyId) {
  const { data } = await docApi.get(`/by-property/${propertyId}`, { headers: buildRoleHeaders() });
  return data;
}

export async function analyzePropertyDocuments({
  propertyInfo,
  files,
  declaredTypes = {},
  manualCases = [],
  externalAiConsent = false,
}) {
  const formData = new FormData();
  Object.entries(propertyInfo || {}).forEach(([k, v]) => {
    formData.append(k, v == null ? '' : String(v));
  });
  formData.append('declared_types', JSON.stringify(declaredTypes));
  formData.append('manual_cases', JSON.stringify(manualCases));
  formData.append('external_ai_consent', String(Boolean(externalAiConsent)));

  (files || []).forEach((file) => {
    formData.append('uploaded_documents', file);
  });

  const { data } = await docApi.post('/analyze', formData, {
    headers: {
      ...buildRoleHeaders(),
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
}

export async function getAnalysis(analysisId) {
  const { data } = await docApi.get(`/${analysisId}`, { headers: buildRoleHeaders() });
  return data;
}

export async function saveManualCorrections(analysisId, documentId, corrections) {
  const { data } = await docApi.patch(
    `/${analysisId}/documents/${documentId}/corrections`,
    { corrections },
    { headers: buildRoleHeaders() }
  );
  return data;
}

export async function reclassifyDocumentType(analysisId, documentId, documentType) {
  const { data } = await docApi.patch(
    `/${analysisId}/documents/${documentId}/classification`,
    { document_type: documentType },
    { headers: buildRoleHeaders() }
  );
  return data;
}

export async function deleteUploadedDocument(analysisId, documentId) {
  const { data } = await docApi.delete(
    `/${analysisId}/documents/${documentId}`,
    { headers: buildRoleHeaders() }
  );
  return data;
}

export function getPdfReportDownloadUrl(analysisId) {
  return `${BASE_URL}/document-analysis/${analysisId}/report/pdf`;
}
