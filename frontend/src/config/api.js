const rawApiUrl = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');

if (!rawApiUrl && import.meta.env.PROD) {
  console.error('[SLV-GIS] VITE_API_URL is not configured for production build.');
}

export const API_BASE_URL = rawApiUrl || (import.meta.env.DEV ? 'http://localhost:5000/api' : '/api');
