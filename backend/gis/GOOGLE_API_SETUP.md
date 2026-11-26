# Google Maps Platform API Setup Guide — SLV-GIS Mysuru

SLV-GIS integrates Google Maps Platform across both the backend (authoritative reverse geocoding fallback & Places lookup) and frontend (interactive Google Maps JS + Places Autocomplete) while keeping API keys strictly in environment variables.

## 1. Required Google Cloud APIs

Enable the following APIs in your Google Cloud Console project with billing active:

1. **Maps JavaScript API** — Interactive map rendering and property marker placement on the frontend.
2. **Geocoding API** — Backend coordinate-based reverse geocoding (`lat, lng` → address components, locality, sublocality, postal code, Place ID) and forward geocoding.
3. **Places API** (or Places API New) — Location search and autocomplete suggestions in `Evaluate Property`.

## 2. Environment Variables

### Backend (`c:\mini project\smart-land-eval\backend\.env`)
```env
GOOGLE_MAPS_API_KEY=your_server_side_google_api_key_here
```
- **Never** commit `.env` files or hardcode this key in source code.
- **Recommended Key Restriction (Google Cloud Console):**
  - Application restriction: **IP addresses** (server IP / localhost during dev).
  - API restriction: **Geocoding API**, **Places API**.

### Frontend (`c:\mini project\smart-land-eval\frontend\.env`)
```env
VITE_API_URL=http://localhost:5000/api
VITE_GOOGLE_MAPS_API_KEY=your_browser_google_api_key_here
```
- **Recommended Key Restriction (Google Cloud Console):**
  - Application restriction: **HTTP referrers (web sites)** (e.g., `http://localhost:5173/*`, `https://your-domain.com/*`).
  - API restriction: **Maps JavaScript API**, **Places API**.

## 3. Fallback Behavior (When Keys Are Not Configured)

- **Backend**: When `GOOGLE_MAPS_API_KEY` is unset, `GET /api/gis/config` returns `google_geocoding_enabled: false`. The geocoding pipeline uses **KGIS District Polygons** (Taluk → Hobli → Revenue Village → Town → MCC Ward) as primary authority and **OpenStreetMap Nominatim** as secondary fallback.
- **Frontend**: When `VITE_GOOGLE_MAPS_API_KEY` is unset, `PropertyMap.jsx` renders the **Leaflet + OpenStreetMap** map with a clear status badge (`Fallback Map Active`) and full click/drag/search functionality.
- When both keys are configured and services are restarted (`python app.py` and `npm run build` / `npm run dev`), the UI automatically upgrades to **Google Maps JS + KGIS Polygons**.
