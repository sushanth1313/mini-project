import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { evaluateProperty, getGisConfig, reverseGeocode, searchLocations } from '../api/client';
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  Compass,
  Crosshair,
  Info,
  Loader2,
  Map as MapIcon,
  MapPin,
  Search,
  ShieldCheck,
} from 'lucide-react';
import PropertyMap from '../components/PropertyMap';
import { PageHeader, StatusBadge } from '../components/ui';
import { isGoogleMapsKeyConfigured, loadGoogleMapsApi } from '../utils/googleMapsLoader';

const TALUKS = [
  { value: 'Mysuru', label: 'Mysuru' },
  { value: 'Nanjangud', label: 'Nanjangud' },
  { value: 'HD Kote', label: 'H.D. Kote (Heggadadevanakote)' },
  { value: 'Periyapatna', label: 'Periyapatna' },
  { value: 'Hunsur', label: 'Hunsur' },
  { value: 'K. R. Nagar', label: 'K.R. Nagar (Krishnarajanagara)' },
  { value: 'T. Narasipura', label: 'T. Narasipura (Tirumakudalu Narasipura)' },
];
const REGION_TYPES = ['Auto', 'Urban', 'Peri-urban', 'Rural'];
const LAND_TYPES = [
  'Residential Plot',
  'Residential House',
  'Commercial Plot / Property',
  'Industrial Plot / Property',
  'Agricultural Land',
  'Converted Agricultural Land',
  'Unconverted Agricultural Land',
  'Mixed-Use Property',
  'Government-Allotted Site',
  'Other / Custom',
];
const SITE_ALLOTMENT_CATEGORIES = [
  'Not Applicable / Not Sure',
  'General allotment',
  'EWS',
  'LIG',
  'MIG',
  'HIG',
  'Government scheme allotment',
  'KHB allotment',
  'Development authority allotment',
  'Private developer allotment',
  'Revenue-site claim',
  'Other / Custom',
];
const LISTING_TYPES = ['New Plot', 'Resale', 'Builder Layout'];

export default function EvaluateProperty() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialQuery = (searchParams.get('q') || '').trim();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [analysisStep, setAnalysisStep] = useState(-1);
  const analysisSteps = [
    'Resolving property location & KGIS boundaries',
    'Checking nearby facilities (GIS)',
    'Analyzing road accessibility & 4 infrastructure factors',
    'Calculating indicative price (ML)',
    'Running environmental & risk checks',
    'Preparing evaluation score & summary',
  ];

  const [formData, setFormData] = useState({
    name: '',
    taluk: 'Mysuru',
    village_or_locality: '',
    region_type: 'Auto',
    land_type: 'Residential Plot',
    custom_land_type: '',
    planning_authority: 'Approval status unknown',
    site_allotment_category: 'Not Applicable / Not Sure',
    custom_allotment_category: '',
    approval_reference_no: '',
    land_conversion_status: 'Not Sure',
    land_use_zoning: 'Not Sure',
    layout_sanction_status: 'Not Sure',
    layout_release_status: 'Not Sure',
    building_plan_approval: 'Not Sure',
    khata_status: 'Not Sure',
    property_tax_status: 'Not Sure',
    rera_registration: 'Not Sure',
    allotment_conditions: '',
    acquisition_concerns: 'Not Sure',
    listing_type: 'Resale',
    land_area_sqft: '',
    latitude: '',
    longitude: '',
    coordinate_status: 'USER_ENTERED',
    asking_price_inr: '',
    road_width_ft: '',
    road_quality: 'Unknown',
    road_access: 'Unknown',
    public_transport_available: 'Unknown',
    electricity_available: 'Unknown',
    water_supply: 'Unknown',
    water_source_type: 'Unknown',
  });
  const [showClassificationCorrection, setShowClassificationCorrection] = useState(false);

  const [revLoading, setRevLoading] = useState(false);
  const [revInfo, setRevInfo] = useState(null);
  const [revError, setRevError] = useState(null);
  const [showMapPicker, setShowMapPicker] = useState(true);
  const [mapView, setMapView] = useState({ center: [12.3052, 76.6552], zoom: 12 });

  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState(null);
  const [landmarkAck, setLandmarkAck] = useState(false);
  const [mapEngineMode, setMapEngineMode] = useState(isGoogleMapsKeyConfigured() ? 'google' : 'fallback_no_key');
  const [gisBackendCaps, setGisBackendCaps] = useState(null);
  const [userEditedLocality, setUserEditedLocality] = useState(false);
  const [locationConfirmed, setLocationConfirmed] = useState(false);

  const searchCacheRef = useRef({});
  const searchWrapRef = useRef(null);
  const searchInputRef = useRef(null);
  const revSeqRef = useRef(0);

  useEffect(() => {
    getGisConfig()
      .then((res) => setGisBackendCaps(res.data || null))
      .catch(() => setGisBackendCaps(null));
  }, []);

  useEffect(() => {
    const onDocClick = (e) => {
      if (searchWrapRef.current && !searchWrapRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  useEffect(() => {
    if (!isGoogleMapsKeyConfigured() || !searchInputRef.current) return;
    let listener = null;
    let cancelled = false;
    loadGoogleMapsApi()
      .then((gmaps) => {
        if (cancelled || !searchInputRef.current || !gmaps?.places?.Autocomplete) return;
        const mysuruBounds = new gmaps.LatLngBounds(
          new gmaps.LatLng(11.6, 75.8),
          new gmaps.LatLng(12.8, 77.4)
        );
        const ac = new gmaps.places.Autocomplete(searchInputRef.current, {
          bounds: mysuruBounds,
          strictBounds: false,
          componentRestrictions: { country: 'in' },
          fields: ['place_id', 'name', 'formatted_address', 'geometry', 'types'],
        });
        listener = ac.addListener('place_changed', () => {
          const place = ac.getPlace();
          const loc = place?.geometry?.location;
          if (!loc) return;
          const la = Number(loc.lat().toFixed(6));
          const lo = Number(loc.lng().toFixed(6));
          if (la < 11.6 || la > 12.8 || lo < 75.8 || lo > 77.4) {
            setRevError('Selected Google place falls outside Mysuru District bounds (11.6°–12.8° N, 75.8°–77.4° E).');
            return;
          }
          const gtypes = place.types || [];
          const isLandmark =
            gtypes.some((t) =>
              ['bus_station', 'transit_station', 'train_station', 'school', 'hospital', 'police', 'bank', 'atm', 'shopping_mall'].includes(t)
            ) &&
            !gtypes.some((t) => ['sublocality', 'sublocality_level_1', 'sublocality_level_2', 'locality', 'neighborhood'].includes(t));

          setSelectedSuggestion({
            name: place.name || place.formatted_address,
            place_type_label: isLandmark ? 'Landmark / Transit Point (Google Places)' : 'Google Places Selection',
            is_non_settlement_landmark: isLandmark,
          });
          setLandmarkAck(!isLandmark);
          setUserEditedLocality(false);
          setSearchQuery(place.formatted_address || place.name || '');
          setShowSuggestions(false);
          setRevInfo(null);
          setRevError(null);
          setLocationConfirmed(false);
          setFormData((prev) => ({
            ...prev,
            latitude: la.toFixed(6),
            longitude: lo.toFixed(6),
            village_or_locality: '',
            coordinate_status: 'GEOCODED',
            coordinate_source: 'Google Places + KGIS Boundary Verification',
          }));
          setMapView({ center: [la, lo], zoom: isLandmark ? 17 : 15 });
          runReverseGeocode(la, lo);
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (listener && window.google?.maps?.event) {
        window.google.maps.event.removeListener(listener);
      }
    };
  }, []);

  useEffect(() => {
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      setSearchError(null);
      return;
    }
    const key = q.toLowerCase();
    if (searchCacheRef.current[key]) {
      setSearchResults(searchCacheRef.current[key]);
      setSearchError(null);
      return;
    }
    const timer = setTimeout(async () => {
      setSearchLoading(true);
      setSearchError(null);
      try {
        const res = await searchLocations(q, 8);
        const list = res.data?.results || [];
        searchCacheRef.current[key] = list;
        setSearchResults(list);
        setShowSuggestions(true);
      } catch (err) {
        setSearchError(err.response?.data?.error || 'Location search failed.');
      } finally {
        setSearchLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const runReverseGeocode = async (latVal, lonVal) => {
    const la = Number(latVal);
    const lo = Number(lonVal);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) return;
    const reqId = ++revSeqRef.current;
    setRevLoading(true);
    setRevError(null);
    setRevInfo(null);
    try {
      const res = await reverseGeocode(la, lo, formData.land_type);
      if (reqId !== revSeqRef.current) return; // ignore stale response
      const data = res.data;
      setRevInfo(data);
      setUserEditedLocality(false);
      if (data.status === 'SUCCESS' && data.locality) {
        setFormData((prev) => ({
          ...prev,
          village_or_locality: data.locality,
          taluk: data.taluk || prev.taluk,
        }));
      } else if (data.status === 'AMBIGUOUS' || data.uncertain) {
        setFormData((prev) => ({
          ...prev,
          village_or_locality: 'Locality Requires Verification',
          taluk: data.taluk || prev.taluk,
        }));
      }
    } catch (err) {
      if (reqId !== revSeqRef.current) return;
      setRevInfo(null);
      setRevError(err.response?.data?.error || 'Reverse geocoding failed or unavailable; enter locality manually.');
    } finally {
      if (reqId === revSeqRef.current) {
        setRevLoading(false);
      }
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (name === 'village_or_locality') {
      setUserEditedLocality(true);
    }
    if (['latitude', 'longitude', 'taluk', 'village_or_locality', 'coordinate_status'].includes(name)) {
      setLocationConfirmed(false);
    }
    if (name === 'latitude' || name === 'longitude') {
      setRevInfo(null);
      setRevError(null);
      const nextLat = name === 'latitude' ? Number(value) : Number(formData.latitude);
      const nextLon = name === 'longitude' ? Number(value) : Number(formData.longitude);
      if (Number.isFinite(nextLat) && Number.isFinite(nextLon) && nextLat >= 11.6 && nextLat <= 12.8 && nextLon >= 75.8 && nextLon <= 77.4) {
        setMapView({ center: [nextLat, nextLon], zoom: 15 });
      }
    }
  };

  const handleSelectSuggestion = (item) => {
    const la = Number(item.latitude).toFixed(6);
    const lo = Number(item.longitude).toFixed(6);
    setSelectedSuggestion(item);
    setLandmarkAck(!item.is_non_settlement_landmark);
    setUserEditedLocality(false);
    setRevInfo(null);
    setRevError(null);
    setLocationConfirmed(false);
    setFormData((prev) => ({
      ...prev,
      latitude: la,
      longitude: lo,
      coordinate_status: 'GEOCODED',
      village_or_locality: item.locality || '',
      taluk: item.taluk || prev.taluk,
    }));
    setSearchQuery(item.display_name || item.name);
    setShowSuggestions(false);
    setMapView({ center: [Number(la), Number(lo)], zoom: item.appropriate_zoom || 15 });
    runReverseGeocode(la, lo);
  };

  const handleUseMyLocation = () => {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const la = pos.coords.latitude.toFixed(6);
          const lo = pos.coords.longitude.toFixed(6);
          setSelectedSuggestion(null);
          setLandmarkAck(true);
          setUserEditedLocality(false);
          setRevInfo(null);
          setRevError(null);
          setLocationConfirmed(false);
          setFormData((prev) => ({
            ...prev,
            latitude: la,
            longitude: lo,
            village_or_locality: '',
            coordinate_status: 'DEVICE_GPS',
          }));
          setMapView({ center: [Number(la), Number(lo)], zoom: 16 });
          runReverseGeocode(la, lo);
        },
        (err) => {
          setRevError(`Geolocation unavailable: ${err.message}`);
        }
      );
    } else {
      setRevError('Browser geolocation is not supported.');
    }
  };

  const handleMapPick = (latVal, lonVal) => {
    const la = latVal.toFixed(6);
    const lo = lonVal.toFixed(6);
    setSelectedSuggestion(null);
    setLandmarkAck(true);
    setUserEditedLocality(false);
    setRevInfo(null);
    setRevError(null);
    setLocationConfirmed(false);
    setFormData((prev) => ({
      ...prev,
      latitude: la,
      longitude: lo,
      village_or_locality: '',
      coordinate_status: 'MAP_SELECTED',
    }));
    setMapView((prev) => ({ center: [Number(la), Number(lo)], zoom: Math.max(prev.zoom || 14, 15) }));
    runReverseGeocode(la, lo);
  };

  const handlePickCandidateLocality = (candLocality) => {
    setUserEditedLocality(false);
    setLocationConfirmed(false);
    setFormData((prev) => ({
      ...prev,
      village_or_locality: candLocality,
      taluk: revInfo?.taluk || prev.taluk,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError(null);

    const areaVal = Number(formData.land_area_sqft);
    if (!Number.isFinite(areaVal) || areaVal <= 0 || areaVal > 50000000) {
      setError('Land area must be a positive number between 1 and 50,000,000 sq.ft.');
      window.scrollTo(0, 0);
      return;
    }
    if (formData.asking_price_inr !== '' && (!Number.isFinite(Number(formData.asking_price_inr)) || Number(formData.asking_price_inr) < 0)) {
      setError('Asking price must be a non-negative number.');
      window.scrollTo(0, 0);
      return;
    }

    const hasLat = formData.latitude !== '' && formData.latitude !== null && formData.latitude !== undefined;
    const hasLon = formData.longitude !== '' && formData.longitude !== null && formData.longitude !== undefined;
    if (hasLat !== hasLon) {
      setError('Provide both Latitude and Longitude, or leave both blank for automatic locality geocoding.');
      window.scrollTo(0, 0);
      return;
    }
    if (hasLat && hasLon) {
      const latVal = Number(formData.latitude);
      const lonVal = Number(formData.longitude);
      if (!Number.isFinite(latVal) || !Number.isFinite(lonVal) || latVal < 11.6 || latVal > 12.8 || lonVal < 75.8 || lonVal > 77.4) {
        setError('Coordinates lie outside Mysuru District bounds (Latitude 11.6°–12.8° N, Longitude 75.8°–77.4° E).');
        window.scrollTo(0, 0);
        return;
      }
    }

    if (!locationConfirmed) {
      setError('Please review and click "Confirm Property Location" in Step 2 before running evaluation & GIS analysis.');
      document.getElementById('step-2-location')?.scrollIntoView({ behavior: 'smooth' });
      return;
    }

    setLoading(true);
    setAnalysisStep(0);
    const interval = setInterval(() => {
      setAnalysisStep((prev) => (prev < 5 ? prev + 1 : prev));
    }, 1200);

    try {
      const res = await evaluateProperty(formData);
      clearInterval(interval);
      setAnalysisStep(6);
      setTimeout(() => {
        navigate(`/student/map?property_id=${res.data.evaluation.property.id}`);
      }, 700);
    } catch (err) {
      clearInterval(interval);
      setAnalysisStep(-1);
      const isTimeout = err.code === 'ECONNABORTED' || String(err.message || '').toLowerCase().includes('timeout');
      setError(
        err.response?.data?.error ||
        (isTimeout
          ? 'External GIS services took longer than expected. Click "Run Valuation & GIS Analysis" to retry.'
          : err.message)
      );
      window.scrollTo(0, 0);
    } finally {
      setLoading(false);
    }
  };

  if (analysisStep >= 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 150px)' }}>
        <div
          style={{
            width: '100%',
            maxWidth: 500,
            padding: '2.25rem',
            background: '#FFFFFF',
            border: '1px solid #E3E8E4',
            borderRadius: 16,
            boxShadow: '0 12px 32px rgba(16,36,24,0.08)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
            <span className="badge badge-success" style={{ marginBottom: 8 }}>SLV-GIS Engine Running</span>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', color: '#144D29', margin: 0 }}>
              Evaluating Property &amp; Spatial Context
            </h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            {analysisSteps.map((step, idx) => {
              const isPast = idx < analysisStep;
              const isCurrent = idx === analysisStep;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.85rem',
                    padding: '0.55rem 0.75rem',
                    borderRadius: 10,
                    background: isCurrent ? '#ECF5EE' : isPast ? '#F6F8F6' : 'transparent',
                    color: isPast ? '#14532D' : isCurrent ? '#144D29' : '#6E7B73',
                    fontWeight: isCurrent ? 700 : isPast ? 600 : 400,
                  }}
                >
                  {isPast ? (
                    <CheckCircle2 size={18} color="#14532D" />
                  ) : isCurrent ? (
                    <Loader2 size={18} color="#144D29" style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <div style={{ width: 18, height: 18, border: '2px solid #D2DBD4', borderRadius: '50%' }} />
                  )}
                  <span style={{ fontSize: '0.88rem' }}>{step}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  const isExactCoords = Boolean(formData.latitude && formData.longitude);
  const step1Done = Boolean(formData.name.trim() && formData.land_area_sqft);
  const step2Done = locationConfirmed;

  return (
    <div className="fade-in" style={{ maxWidth: 1120, margin: '0 auto' }}>
      <PageHeader
        eyebrow="Mysuru District · Property Evaluation Pipeline"
        title="Evaluate Property"
        subtitle="Select parcel coordinates on the GIS map, verify multi-source locality boundaries, and run ML + 4-factor infrastructure analysis."
        icon={MapPin}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span
              style={{
                padding: '4px 10px',
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                background: step1Done ? '#E7F5EC' : '#ECF5EE',
                color: '#144D29',
                border: '1px solid #BCE0C8',
              }}
            >
              1. Property Details {step1Done ? '✓' : ''}
            </span>
            <span
              style={{
                padding: '4px 10px',
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                background: step2Done ? '#E7F5EC' : '#F6F8F6',
                color: step2Done ? '#14532D' : '#4A5750',
                border: `1px solid ${step2Done ? '#BCE0C8' : '#E3E8E4'}`,
              }}
            >
              2. Location &amp; GIS {step2Done ? '✓' : ''}
            </span>
            <span
              style={{
                padding: '4px 10px',
                borderRadius: 999,
                fontSize: 11,
                fontWeight: 700,
                background: '#F6F8F6',
                color: '#4A5750',
                border: '1px solid #E3E8E4',
              }}
            >
              3. Infrastructure &amp; Submit
            </span>
          </div>
        }
      />

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: 18 }}>
          <AlertCircle size={18} /> {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* STEP 1: PROPERTY DETAILS */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div className="card-title">
              <span style={{ background: '#ECF5EE', color: '#144D29', padding: '2px 9px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                STEP 1
              </span>
              <span>Property Details &amp; Valuation Inputs</span>
            </div>
            <span style={{ fontSize: 12, color: '#6E7B73' }}>Fields marked * are required</span>
          </div>

          <div className="form-group" style={{ marginBottom: 14 }}>
            <label className="form-label">Property Title / Name <span className="req">*</span></label>
            <input
              type="text"
              name="name"
              className="form-control"
              required
              placeholder="e.g. 30x40 Residential Site in Udayagiri / NR Mohalla"
              value={formData.name}
              onChange={handleChange}
            />
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Taluk <span className="req">*</span></label>
              <select name="taluk" className="form-control" required value={formData.taluk} onChange={handleChange}>
                {TALUKS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group" style={{ gridColumn: 'span 2' }}>
              <label className="form-label">
                Village / Urban Locality {!isExactCoords && <span className="req">*</span>}
                {userEditedLocality && (
                  <span style={{ marginLeft: 8, fontSize: 10, padding: '2px 8px', borderRadius: 999, background: '#FEF6E6', color: '#85520E', border: '1px solid #EDD49F', fontWeight: 700 }}>
                    User-Edited Override
                  </span>
                )}
              </label>
              <input
                type="text"
                name="village_or_locality"
                className="form-control"
                required={!isExactCoords}
                placeholder={revLoading ? 'Resolving from coordinates...' : 'Auto-resolved on map click, or enter manually'}
                value={formData.village_or_locality}
                onChange={handleChange}
              />
              <div className="form-hint">
                Cross-checked between KGIS boundary polygons and independent geocoding; disagreements are highlighted in Step 2.
              </div>
            </div>
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Region Type</label>
              <select name="region_type" className="form-control" value={formData.region_type} onChange={handleChange}>
                {REGION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Land Type</label>
              <select name="land_type" className="form-control" value={formData.land_type} onChange={handleChange}>
                {LAND_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Listing Type</label>
              <select name="listing_type" className="form-control" value={formData.listing_type} onChange={handleChange}>
                {LISTING_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Land Area (sq.ft) <span className="req">*</span></label>
              <input
                type="number"
                name="land_area_sqft"
                className="form-control"
                required
                min="1"
                max="50000000"
                step="any"
                placeholder="e.g. 1200"
                value={formData.land_area_sqft}
                onChange={handleChange}
                onWheel={(e) => e.target.blur()}
              />
              {formData.land_area_sqft > 0 && (
                <div className="form-hint">
                  = {Number(formData.land_area_sqft).toLocaleString()} sq.ft ({(Number(formData.land_area_sqft) / 1089).toFixed(2)} Gunta)
                </div>
              )}
            </div>
            <div className="form-group" style={{ gridColumn: 'span 2' }}>
              <label className="form-label">Asking Price (Total ₹)</label>
              <input
                type="number"
                name="asking_price_inr"
                className="form-control"
                min="0"
                step="any"
                placeholder="Optional. Leave blank to rely strictly on ML valuation."
                value={formData.asking_price_inr}
                onChange={handleChange}
                onWheel={(e) => e.target.blur()}
              />
              {formData.asking_price_inr > 0 && (
                <div className="form-hint">
                  = {Number(formData.asking_price_inr) >= 1e7
                    ? `₹${(Number(formData.asking_price_inr) / 1e7).toFixed(2)} Crore`
                    : Number(formData.asking_price_inr) >= 1e5
                    ? `₹${(Number(formData.asking_price_inr) / 1e5).toFixed(2)} Lakh`
                    : `₹${Number(formData.asking_price_inr).toLocaleString()}`}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* STEP 2: INTERACTIVE GIS MAP, SEARCH & CONFIRMATION */}
        <div id="step-2-location" className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div className="card-title">
              <span style={{ background: '#ECF5EE', color: '#144D29', padding: '2px 9px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                STEP 2
              </span>
              <span>Interactive GIS Map, Coordinates &amp; Verification</span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <StatusBadge status={mapEngineMode === 'google' ? 'VERIFIED' : 'INFO'}>
                {mapEngineMode === 'google'
                  ? 'Google Maps JS + KGIS'
                  : mapEngineMode === 'fallback_error'
                  ? 'Leaflet Fallback (Key/Billing Error)'
                  : 'Leaflet + KGIS Polygons'}
              </StatusBadge>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowMapPicker((p) => !p)}>
                <MapIcon size={14} /> {showMapPicker ? 'Hide Map' : 'Show Map'}
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleUseMyLocation}>
                <Crosshair size={14} /> Use Current GPS
              </button>
            </div>
          </div>

          {/* Search Bar */}
          <div ref={searchWrapRef} style={{ position: 'relative', marginBottom: 14 }}>
            <label className="form-label">Search Locality, Village, Ward, Street, or Taluk (Mysuru District)</label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Search size={16} style={{ position: 'absolute', left: 12, color: '#6E7B73', pointerEvents: 'none' }} />
              <input
                ref={searchInputRef}
                type="text"
                className="form-control"
                style={{ paddingLeft: 38, paddingRight: 38, background: '#FFFFFF' }}
                placeholder="Search e.g. Udayagiri, NR Mohalla, Nazarbad, Sathagalli, Vijayanagar, Nanjangud..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => searchResults.length > 0 && setShowSuggestions(true)}
              />
              {searchLoading && (
                <Loader2 size={16} style={{ position: 'absolute', right: 12, color: '#144D29', animation: 'spin 1s linear infinite' }} />
              )}
            </div>
            {searchError && <div style={{ fontSize: 12, color: '#8C2D23', marginTop: 6 }}>{searchError}</div>}
            {showSuggestions && searchResults.length > 0 && (
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: '100%',
                  zIndex: 1200,
                  background: '#FFFFFF',
                  border: '1px solid #BCE0C8',
                  borderRadius: 10,
                  marginTop: 4,
                  maxHeight: 280,
                  overflowY: 'auto',
                  boxShadow: '0 14px 32px rgba(16, 36, 24, 0.14)',
                }}
              >
                {searchResults.map((s, idx) => (
                  <button
                    key={s.place_id || idx}
                    type="button"
                    onClick={() => handleSelectSuggestion(s)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '10px 14px',
                      background: '#FFFFFF',
                      border: 'none',
                      borderBottom: '1px solid #E3E8E4',
                      cursor: 'pointer',
                      color: '#141C17',
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 700, color: s.is_non_settlement_landmark ? '#85520E' : '#144D29', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span>{s.name}</span>
                      <span
                        style={{
                          fontSize: 10,
                          padding: '2px 8px',
                          borderRadius: 999,
                          fontWeight: 700,
                          background: s.is_non_settlement_landmark ? '#FEF6E6' : '#E7F5EC',
                          color: s.is_non_settlement_landmark ? '#85520E' : '#14532D',
                          border: `1px solid ${s.is_non_settlement_landmark ? '#EDD49F' : '#BCE0C8'}`,
                        }}
                      >
                        {s.place_type_label || s.place_type}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#4A5750', marginTop: 3 }}>
                      {s.locality}, {s.taluk} Taluk, {s.district} District · {Number(s.latitude).toFixed(5)}°N, {Number(s.longitude).toFixed(5)}°E
                    </div>
                  </button>
                ))}
                {searchResults.length > 1 && (
                  <div style={{ padding: '8px 14px', fontSize: 11, color: '#4A5750', background: '#F6F8F6' }}>
                    Tip: Choose the settlement / ward entry, then click or drag the map pin onto the exact parcel.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Two-Column GIS Workspace: Large Interactive Map + Coordinates & Controls */}
          <div style={{ display: 'grid', gridTemplateColumns: showMapPicker ? 'minmax(0, 1.55fr) minmax(290px, 1fr)' : '1fr', gap: 16, alignItems: 'start' }} className="gis-workspace">
            {showMapPicker && (
              <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid #D2DBD4', background: '#FFFFFF' }}>
                <div style={{ padding: '8px 12px', fontSize: 12, background: '#F6F8F6', color: '#4A5750', borderBottom: '1px solid #E3E8E4', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <span>
                    Click anywhere in Mysuru District or <strong>drag the marker</strong> to inspect exact boundaries.
                  </span>
                  {gisBackendCaps && (
                    <span style={{ fontSize: 11, color: '#144D29', fontWeight: 600 }}>
                      Resolver: {gisBackendCaps.google_geocoding_enabled ? 'KGIS + Google Geocoding' : 'KGIS Polygons + OSM Cross-Check'}
                    </span>
                  )}
                </div>
                <PropertyMap
                  interactive={true}
                  lat={isExactCoords ? Number(formData.latitude) : null}
                  lon={isExactCoords ? Number(formData.longitude) : null}
                  centerLat={mapView.center[0]}
                  centerLon={mapView.center[1]}
                  zoom={mapView.zoom}
                  label={revInfo?.locality || formData.village_or_locality || 'Selected Parcel'}
                  status={formData.coordinate_status}
                  onPick={handleMapPick}
                  onMapModeChange={setMapEngineMode}
                  height={420}
                />
              </div>
            )}

            {/* Right Controls Column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ padding: 14, borderRadius: 12, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#144D29', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Compass size={14} /> Coordinates &amp; Precision
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: 11 }}>Latitude (11.6°–12.8° N)</label>
                    <input
                      type="number"
                      name="latitude"
                      className="form-control"
                      min="11.6"
                      max="12.8"
                      step="any"
                      placeholder="12.324942"
                      value={formData.latitude}
                      onChange={handleChange}
                      onWheel={(e) => e.target.blur()}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: 11 }}>Longitude (75.8°–77.4° E)</label>
                    <input
                      type="number"
                      name="longitude"
                      className="form-control"
                      min="75.8"
                      max="77.4"
                      step="any"
                      placeholder="76.674615"
                      value={formData.longitude}
                      onChange={handleChange}
                      onWheel={(e) => e.target.blur()}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: 10, marginBottom: 10 }}>
                  <label className="form-label" style={{ fontSize: 11 }}>Coordinate Source / Precision</label>
                  <select name="coordinate_status" className="form-control" value={formData.coordinate_status} onChange={handleChange}>
                    <option value="USER_ENTERED">USER_ENTERED — Manual Coordinates (Not surveyed)</option>
                    <option value="MAP_SELECTED">MAP_SELECTED — Selected / Dragged on Map</option>
                    <option value="GEOCODED">GEOCODED — Search Geocoded</option>
                    <option value="DEVICE_GPS">DEVICE_GPS — Browser / Device GPS</option>
                    <option value="LOCALITY_CENTROID">LOCALITY_CENTROID — Approximate Centroid</option>
                    <option value="SURVEY_GPS">SURVEY_GPS — Surveyed / DGPS Coordinates</option>
                  </select>
                </div>

                {isExactCoords && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm btn-full"
                    disabled={revLoading}
                    onClick={() => runReverseGeocode(formData.latitude, formData.longitude)}
                  >
                    {revLoading ? 'Identifying Boundaries...' : 'Identify Locality from Coordinates'}
                  </button>
                )}
              </div>

              {/* Landmark notice if applicable */}
              {selectedSuggestion?.is_non_settlement_landmark && (
                <div className="alert alert-warn" style={{ fontSize: 12 }}>
                  <AlertTriangle size={16} />
                  <div style={{ flex: 1 }}>
                    <strong>Landmark Selected:</strong> <em>{selectedSuggestion.name}</em>. Drag pin to the actual land parcel if needed.
                    <div style={{ marginTop: 6 }}>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontWeight: 600 }}>
                        <input type="checkbox" checked={landmarkAck} onChange={(e) => setLandmarkAck(e.target.checked)} />
                        Confirm using this coordinate
                      </label>
                    </div>
                  </div>
                </div>
              )}

              {/* Quick KGIS Coverage Info Box */}
              <div style={{ padding: 12, borderRadius: 12, background: '#ECF5EE', border: '1px solid #BCE0C8', fontSize: 12, color: '#144D29' }}>
                <div style={{ fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Info size={14} /> Authoritative Boundary Hierarchy
                </div>
                <div style={{ fontSize: 11, color: '#4A5750', lineHeight: 1.5 }}>
                  Point-in-polygon checks run against KGIS Taluks, Hoblis, Revenue Villages, Urban Local Bodies, and Municipal Wards, cross-checked with Geocoder addresses.
                </div>
              </div>
            </div>
          </div>

          {/* STRUCTURED LOCATION CONFIRMATION PANEL (A3) */}
          {revLoading && (
            <div style={{ marginTop: 16, padding: 14, borderRadius: 10, background: '#F6F8F6', border: '1px solid #E3E8E4', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#144D29' }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
              Resolving KGIS boundary polygons and cross-checking geocoder address for ({Number(formData.latitude).toFixed(5)}, {Number(formData.longitude).toFixed(5)})...
            </div>
          )}

          {revError && (
            <div className="alert alert-danger" style={{ marginTop: 14, fontSize: 13 }}>
              <AlertCircle size={16} /> {revError}
            </div>
          )}

          {revInfo && (
            <div
              style={{
                marginTop: 16,
                padding: 16,
                borderRadius: 12,
                background: revInfo.source_disagreement || revInfo.status === 'AMBIGUOUS' ? '#FEF6E6' : '#F2F9F4',
                border: `1px solid ${revInfo.source_disagreement || revInfo.status === 'AMBIGUOUS' ? '#EDD49F' : '#BCE0C8'}`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#141C17', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ShieldCheck size={17} color={revInfo.source_disagreement || revInfo.status === 'AMBIGUOUS' ? '#85520E' : '#144D29'} />
                  Location Resolution &amp; Source Verification
                </div>
                <StatusBadge status={revInfo.verification_status || revInfo.status}>
                  {revInfo.verification_status === 'SOURCE_DISAGREEMENT'
                    ? 'SOURCE DISAGREEMENT — REVIEW REQUIRED'
                    : revInfo.verification_status === 'VERIFIED'
                    ? 'VERIFIED AGREEMENT'
                    : revInfo.verification_status || revInfo.status}
                </StatusBadge>
              </div>

              {/* Distinct structured fields per A3 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
                <div style={{ padding: 10, borderRadius: 8, background: '#FFFFFF', border: '1px solid #E3E8E4' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>Selected Coordinates</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#141C17', marginTop: 3 }}>
                    {isExactCoords ? `${Number(formData.latitude).toFixed(6)}°N, ${Number(formData.longitude).toFixed(6)}°E` : 'Centroid Mode'}
                  </div>
                  <div style={{ fontSize: 11, color: '#4A5750', marginTop: 2 }}>Precision: {formData.coordinate_status}</div>
                </div>

                <div style={{ padding: 10, borderRadius: 8, background: '#FFFFFF', border: '1px solid #E3E8E4' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>KGIS Boundary Locality</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#144D29', marginTop: 3 }}>
                    {revInfo.locality || revInfo.locality_display || 'Locality Requires Verification'}
                  </div>
                  <div style={{ fontSize: 11, color: '#4A5750', marginTop: 2 }}>
                    {revInfo.ward_number ? `Ward ${revInfo.ward_number}${revInfo.ward_name ? ` (${revInfo.ward_name})` : ''}` : 'Outside Municipal Ward'}
                  </div>
                </div>

                <div style={{ padding: 10, borderRadius: 8, background: '#FFFFFF', border: '1px solid #E3E8E4' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>
                    Geocoder Address ({revInfo.google_geocoder_status === 'OK' ? 'Google' : 'OSM Nominatim'})
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#141C17', marginTop: 3 }}>
                    {revInfo.geocoder_reported_locality || 'Unavailable / Not Returned'}
                  </div>
                  <div style={{ fontSize: 11, color: '#4A5750', marginTop: 2 }} title={revInfo.geocoder_reported_address || ''}>
                    {revInfo.geocoder_reported_address ? String(revInfo.geocoder_reported_address).slice(0, 72) : 'No geocoder street/suburb string'}
                  </div>
                </div>

                <div style={{ padding: 10, borderRadius: 8, background: '#FFFFFF', border: '1px solid #E3E8E4' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>Verified Administrative Units</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#141C17', marginTop: 3 }}>
                    Taluk: {revInfo.taluk || '—'} · Hobli: {revInfo.hobli || '—'}
                  </div>
                  <div style={{ fontSize: 11, color: '#4A5750', marginTop: 2 }}>
                    Rev. Village: {revInfo.revenue_village || '—'}
                    {revInfo.gram_panchayat_lgd_code ? ` · GP LGD: ${revInfo.gram_panchayat_lgd_code}` : ''}
                  </div>
                  <div style={{ fontSize: 11, color: '#6E7B73', marginTop: 2 }}>
                    Constituency: {revInfo.assembly_constituency || 'Unavailable (AC layer not loaded)'}
                  </div>
                </div>
              </div>

              {/* Disagreement resolution banner */}
              {revInfo.source_disagreement && (
                <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: '#FFFFFF', border: '1px solid #EDD49F' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#85520E', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={15} /> Source Disagreement Detected — Confirm Applicable Locality
                  </div>
                  <p style={{ fontSize: 12, color: '#4A5750', marginTop: 4 }}>{revInfo.disagreement_reason}</p>
                  {Array.isArray(revInfo.candidate_localities) && revInfo.candidate_localities.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                      {revInfo.candidate_localities.map((cand) => {
                        const active = (formData.village_or_locality || '').trim().toLowerCase() === cand.locality.toLowerCase();
                        return (
                          <button
                            key={`${cand.locality}-${cand.source}`}
                            type="button"
                            onClick={() => handlePickCandidateLocality(cand.locality)}
                            style={{
                              padding: '6px 12px',
                              borderRadius: 8,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: 'pointer',
                              border: `1.5px solid ${active ? '#144D29' : '#D2DBD4'}`,
                              background: active ? '#E7F5EC' : '#F6F8F6',
                              color: active ? '#144D29' : '#141C17',
                            }}
                          >
                            {active ? '✓ ' : ''}Use &ldquo;{cand.locality}&rdquo; <span style={{ fontWeight: 400, color: '#4A5750' }}>({cand.source})</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {revInfo.status === 'AMBIGUOUS' && (
                <div className="alert alert-warn" style={{ marginTop: 12, fontSize: 12 }}>
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Locality Requires Verification:</strong> {revInfo.error} Enter a verified locality in Step 1 if known.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Mandatory Confirmation Action Bar */}
          <div
            style={{
              marginTop: 14,
              padding: '12px 16px',
              borderRadius: 10,
              background: locationConfirmed ? '#E7F5EC' : '#FEF6E6',
              border: `1px solid ${locationConfirmed ? '#BCE0C8' : '#EDD49F'}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 12,
            }}
          >
            <div style={{ fontSize: 13 }}>
              <div style={{ fontWeight: 700, color: locationConfirmed ? '#14532D' : '#85520E' }}>
                {locationConfirmed ? 'Location Confirmed for Evaluation & GIS Analysis' : 'Confirm Selected Locality & Coordinates Before Submitting'}
              </div>
              <div style={{ fontSize: 12, color: '#4A5750', marginTop: 2 }}>
                Selected Locality: <strong>{formData.village_or_locality || 'Not set'}</strong> · Taluk: <strong>{formData.taluk}</strong>
                {isExactCoords && ` · (${Number(formData.latitude).toFixed(5)}°N, ${Number(formData.longitude).toFixed(5)}°E)`}
              </div>
            </div>
            <button
              type="button"
              disabled={revLoading || Boolean(selectedSuggestion?.is_non_settlement_landmark && !landmarkAck)}
              className={`btn btn-sm ${locationConfirmed ? 'btn-secondary' : 'btn-primary'}`}
              onClick={() => setLocationConfirmed(true)}
            >
              <Check size={14} /> {locationConfirmed ? 'Location Confirmed' : 'Confirm Property Location'}
            </button>
          </div>
        </div>

        {/* STEP 2B: AUTOMATIC JURISDICTION & LAND CLASSIFICATION */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div className="card-title">
              <span style={{ background: '#ECF5EE', color: '#144D29', padding: '2px 9px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                JURISDICTION
              </span>
              <span>Automatic Property Jurisdiction &amp; Classification</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowClassificationCorrection((v) => !v)}
            >
              {showClassificationCorrection ? 'Hide Optional Correction' : 'Optional Statutory Details'}
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 12 }}>
            <div style={{ padding: 12, borderRadius: 10, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>Local Body (KGIS)</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#141C17', marginTop: 4 }}>
                {revInfo?.municipal_body || (isExactCoords ? 'Run "Identify Locality" or click map' : 'Detected upon coordinate selection')}
              </div>
            </div>
            <div style={{ padding: 12, borderRadius: 10, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>Planning Authority (Auto)</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#141C17', marginTop: 4 }}>
                {revInfo?.likely_planning_authority || 'Requires Verification'}
              </div>
            </div>
            <div style={{ padding: 12, borderRadius: 10, background: '#F6F8F6', border: '1px solid #E3E8E4' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#6E7B73', textTransform: 'uppercase' }}>Detected Classification</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#141C17', marginTop: 4 }}>
                {formData.land_type}{revInfo?.region_type ? ` · ${revInfo.region_type}` : ''}
              </div>
              <div style={{ fontSize: 11, color: '#6E7B73', marginTop: 2 }}>
                Layout Sanction: {formData.approval_reference_no ? 'User Reported — Not Officially Verified' : 'Not Independently Verified'}
              </div>
            </div>
          </div>

          <div className="form-hint" style={{ marginBottom: showClassificationCorrection ? 16 : 0 }}>
            Jurisdiction and local body are derived from KGIS boundary containment and do not substitute for legal title/Khata verification.
          </div>

          {formData.land_type === 'Other / Custom' && (
            <div className="form-group" style={{ marginTop: 12 }}>
              <label className="form-label">Custom Property / Land Category</label>
              <input type="text" name="custom_land_type" className="form-control" placeholder="e.g. Institutional Site, Farm House" value={formData.custom_land_type} onChange={handleChange} />
            </div>
          )}

          {showClassificationCorrection && (
            <div style={{ borderTop: '1px solid #E3E8E4', paddingTop: 14 }}>
              <div className="form-hint" style={{ marginBottom: 12, color: '#85520E' }}>
                Optional entries below are recorded strictly as <strong>User Reported — Not Officially Verified</strong>.
              </div>
              <div className="form-row-3">
                <div className="form-group">
                  <label className="form-label">Site / Allotment Category</label>
                  <select name="site_allotment_category" className="form-control" value={formData.site_allotment_category} onChange={handleChange}>
                    {SITE_ALLOTMENT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Layout Sanction &amp; Release</label>
                  <select name="layout_sanction_status" className="form-control" value={formData.layout_sanction_status} onChange={handleChange}>
                    <option value="Not Sure">Not Sure</option>
                    <option value="Approved Layout (Final Release)">Approved Layout (Final Release)</option>
                    <option value="Provisional / Partial Release">Provisional / Partial Release</option>
                    <option value="Unapproved / Revenue Layout">Unapproved / Revenue Layout</option>
                    <option value="Standalone Parcel (Not in Layout)">Standalone Parcel (Not in Layout)</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Approval / Order Reference</label>
                  <input type="text" name="approval_reference_no" className="form-control" placeholder="Optional sanction / allotment no." value={formData.approval_reference_no} onChange={handleChange} />
                </div>
              </div>
              {formData.site_allotment_category === 'Other / Custom' && (
                <div className="form-group">
                  <label className="form-label">Custom Site / Allotment Category</label>
                  <input type="text" name="custom_allotment_category" className="form-control" placeholder="Specify site/allotment category" value={formData.custom_allotment_category} onChange={handleChange} />
                </div>
              )}
              <div className="form-row-3">
                <div className="form-group">
                  <label className="form-label">Land Conversion Status</label>
                  <select name="land_conversion_status" className="form-control" value={formData.land_conversion_status} onChange={handleChange}>
                    <option value="Not Sure">Not Sure</option>
                    <option value="DC Converted (Sec 95 KLR)">DC Converted (Sec. 95 KLR)</option>
                    <option value="Agricultural (RTC / Pahani Maintained)">Agricultural (RTC / Pahani Maintained)</option>
                    <option value="Pending / Unconverted">Pending / Unconverted</option>
                    <option value="Pre-Urbanized / Gramatana">Pre-Urbanized / Gramatana</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Khata / e-Khata / PID Status</label>
                  <select name="khata_status" className="form-control" value={formData.khata_status} onChange={handleChange}>
                    <option value="Not Sure">Not Sure</option>
                    <option value="A-Khata / e-Khata (Municipal)">A-Khata / e-Khata (Municipal)</option>
                    <option value="e-Swathu Form 9/11 (Panchayat)">e-Swathu Form 9/11 (Gram Panchayat)</option>
                    <option value="B-Khata / Unregularised Register">B-Khata / Unregularised Register</option>
                    <option value="Not Available / Pending">Not Available / Pending</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Correction / Jurisdiction Note</label>
                  <input type="text" name="planning_authority" className="form-control" placeholder="Optional user correction" value={formData.planning_authority === 'Approval status unknown' ? '' : formData.planning_authority} onChange={handleChange} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* STEP 3: 4 ESSENTIAL INFRASTRUCTURE FACTORS */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <div className="card-title">
              <span style={{ background: '#ECF5EE', color: '#144D29', padding: '2px 9px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                STEP 3
              </span>
              <span>Essential Infrastructure &amp; Connectivity (4 Factors)</span>
            </div>
            <span style={{ fontSize: 12, color: '#6E7B73' }}>Optional — leave &ldquo;Not Confirmed&rdquo; for GIS auto-check</span>
          </div>

          <div className="form-hint" style={{ marginBottom: 16 }}>
            Only <strong>Road, Water, Electricity, and Public Transport</strong> contribute to infrastructure scoring. Nearby schools, hospitals, banks, and amenities are fetched separately for informational reference.
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Road Access</label>
              <select name="road_access" className="form-control" value={formData.road_access} onChange={handleChange}>
                <option value="Unknown">Not Confirmed (Auto-Investigate GIS)</option>
                <option value="Yes">Yes — Direct Road Access</option>
                <option value="No">No — Not Available / Landlocked</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Road Width (ft)</label>
              <input type="number" name="road_width_ft" className="form-control" step="any" placeholder="Unknown (optional)" value={formData.road_width_ft} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label className="form-label">Road Quality</label>
              <select name="road_quality" className="form-control" value={formData.road_quality} onChange={handleChange}>
                <option value="Unknown">Unknown (Optional)</option>
                <option value="asphalt">Asphalt / Tar</option>
                <option value="concrete">Concrete</option>
                <option value="macadam/asphalt">Macadam / WBM</option>
                <option value="gravel">Gravel / Metal</option>
                <option value="mud">Mud / Earthen</option>
              </select>
            </div>
          </div>

          <div className="form-row-3">
            <div className="form-group">
              <label className="form-label">Water Availability</label>
              <select name="water_supply" className="form-control" value={formData.water_supply} onChange={handleChange}>
                <option value="Unknown">Not Confirmed (Auto-Investigate GIS)</option>
                <option value="Yes">Yes — Available</option>
                <option value="No">No — Not Available</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Electricity Availability</label>
              <select className="form-control" value={formData.electricity_available} onChange={(e) => setFormData((p) => ({ ...p, electricity_available: e.target.value }))}>
                <option value="Unknown">Not Confirmed (Auto-Investigate GIS)</option>
                <option value="Yes">Yes — Available</option>
                <option value="No">No — Not Available</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Public Transport</label>
              <select className="form-control" value={formData.public_transport_available} onChange={(e) => setFormData((p) => ({ ...p, public_transport_available: e.target.value }))}>
                <option value="Unknown">Not Confirmed (Auto-Investigate GIS)</option>
                <option value="Yes">Yes — Available</option>
                <option value="No">No — Not Available</option>
              </select>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, padding: '14px 18px', background: '#FFFFFF', border: '1px solid #E3E8E4', borderRadius: 12 }}>
          <div style={{ fontSize: 13, color: '#4A5750' }}>
            {locationConfirmed
              ? 'Location confirmed. Ready to run ML valuation, GIS facility lookup, and 4-factor scoring.'
              : 'Confirm your property location in Step 2 to proceed.'}
          </div>
          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            <Search size={18} /> Analyze Property
          </button>
        </div>
      </form>
    </div>
  );
}
