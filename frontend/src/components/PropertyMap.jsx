import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Circle, ScaleControl, useMapEvents, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { Crosshair, RefreshCw, AlertTriangle } from 'lucide-react';
import { isGoogleMapsKeyConfigured, loadGoogleMapsApi } from '../utils/googleMapsLoader';

// Fix leaflet default icon issue in React
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const createIcon = (color) => {
  const markerHtmlStyles = `
    background-color: ${color};
    width: 18px;
    height: 18px;
    display: block;
    left: -9px;
    top: -9px;
    position: relative;
    border-radius: 50%;
    border: 2px solid #FFFFFF;
    box-shadow: 0 1px 4px rgba(0,0,0,0.45);
  `;
  return L.divIcon({
    className: 'custom-pin',
    iconAnchor: [0, 9],
    labelAnchor: [-6, 0],
    popupAnchor: [0, -9],
    html: `<span style="${markerHtmlStyles}" />`
  });
};

const facilityColors = {
  school: '#d97706',
  hospital: '#dc2626',
  clinic: '#ef4444',
  supermarket: '#16a34a',
  market: '#15803d',
  pharmacy: '#ea580c',
  bus_stop: '#2563eb',
  railway_station: '#7c3aed',
  bank: '#0d9488',
  police: '#334155',
  atm: '#0891b2',
  park: '#22c55e',
  waterbody: '#0284c7',
  canal: '#0369a1',
};

const TILE_PROVIDERS = {
  osm: {
    label: 'OpenStreetMap Standard',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  carto: {
    label: 'Carto Voyager (OSM Backup)',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
  },
};

function LeafletClickHandler({ interactive, onPick }) {
  useMapEvents({
    click(e) {
      if (interactive && onPick) {
        onPick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

/**
 * Fixes Leaflet grey/blank tiles when map mounts inside flex/grid containers,
 * animations (fade-in), hidden tabs, or window resizes.
 */
function LeafletLifecycleFix({ containerRef, height }) {
  const map = useMap();

  useEffect(() => {
    const invalidate = () => {
      try {
        map.invalidateSize({ animate: false });
      } catch {
        // ignore unmounted map
      }
    };
    invalidate();
    const t1 = setTimeout(invalidate, 80);
    const t2 = setTimeout(invalidate, 300);
    const t3 = setTimeout(invalidate, 750);

    let ro = null;
    if (typeof ResizeObserver !== 'undefined' && containerRef?.current) {
      ro = new ResizeObserver(() => {
        invalidate();
      });
      ro.observe(containerRef.current);
    }
    window.addEventListener('resize', invalidate);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      if (ro) ro.disconnect();
      window.removeEventListener('resize', invalidate);
    };
  }, [map, containerRef, height]);

  return null;
}

function LeafletViewController({ center, zoom }) {
  const map = useMap();
  const prevRef = useRef({ lat: null, lon: null, zoom: null });

  useEffect(() => {
    if (center && Number.isFinite(center[0]) && Number.isFinite(center[1])) {
      const targetZoom = zoom || 15;
      const moved =
        prevRef.current.lat !== center[0] ||
        prevRef.current.lon !== center[1] ||
        prevRef.current.zoom !== targetZoom;
      if (moved) {
        prevRef.current = { lat: center[0], lon: center[1], zoom: targetZoom };
        map.setView(center, targetZoom, { animate: true });
        setTimeout(() => {
          try {
            map.invalidateSize({ animate: false });
          } catch {
            // ignore
          }
        }, 120);
      }
    }
  }, [center?.[0], center?.[1], zoom, map]);

  return null;
}

function GoogleMapCanvas({
  centerLat,
  centerLon,
  hasPin,
  zoom,
  label,
  isApprox,
  status,
  interactive,
  onPick,
  facilities,
  hiddenTypes,
  height,
  onError,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const pinMarkerRef = useRef(null);
  const circleRef = useRef(null);
  const facMarkersRef = useRef([]);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    let cancelled = false;
    loadGoogleMapsApi()
      .then((gmaps) => {
        if (cancelled || !containerRef.current) return;
        const map = new gmaps.Map(containerRef.current, {
          center: { lat: centerLat, lng: centerLon },
          zoom: zoom || (isApprox ? 13 : 15),
          mapTypeControl: true,
          streetViewControl: false,
          fullscreenControl: true,
        });
        mapRef.current = map;

        if (interactive) {
          map.addListener('click', (ev) => {
            if (ev?.latLng && onPickRef.current) {
              onPickRef.current(ev.latLng.lat(), ev.latLng.lng());
            }
          });
        }
      })
      .catch((err) => {
        if (!cancelled && onError) {
          onError(err?.message || 'GOOGLE_MAPS_LOAD_FAILED');
        }
      });

    return () => {
      cancelled = true;
      if (pinMarkerRef.current) pinMarkerRef.current.setMap(null);
      if (circleRef.current) circleRef.current.setMap(null);
      facMarkersRef.current.forEach((m) => m.setMap(null));
      facMarkersRef.current = [];
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const gmaps = window.google?.maps;
    if (!map || !gmaps) return;

    map.panTo({ lat: centerLat, lng: centerLon });
    if (zoom) map.setZoom(zoom);

    if (pinMarkerRef.current) {
      pinMarkerRef.current.setMap(null);
      pinMarkerRef.current = null;
    }
    if (circleRef.current) {
      circleRef.current.setMap(null);
      circleRef.current = null;
    }

    if (hasPin) {
      const marker = new gmaps.Marker({
        position: { lat: centerLat, lng: centerLon },
        map,
        draggable: Boolean(interactive),
        title: label || 'Selected Property Location',
      });
      if (interactive) {
        marker.addListener('dragend', (ev) => {
          if (ev?.latLng && onPickRef.current) {
            onPickRef.current(ev.latLng.lat(), ev.latLng.lng());
          }
        });
      } else {
        const infoWin = new gmaps.InfoWindow({
          content: `<div style="color:#111;font-size:12px"><strong>${label || 'Property Location'}</strong><br/>${centerLat.toFixed(5)}, ${centerLon.toFixed(5)}${status ? `<br/><span style="color:#666">${status}</span>` : ''}</div>`,
        });
        marker.addListener('click', () => infoWin.open({ anchor: marker, map }));
      }
      pinMarkerRef.current = marker;

      if (!interactive && isApprox) {
        circleRef.current = new gmaps.Circle({
          map,
          center: { lat: centerLat, lng: centerLon },
          radius: 1500,
          strokeColor: '#144D29',
          strokeOpacity: 0.7,
          strokeWeight: 1,
          fillColor: '#1B6336',
          fillOpacity: 0.1,
        });
      }
    }

    facMarkersRef.current.forEach((m) => m.setMap(null));
    facMarkersRef.current = [];
    facilities.forEach((fac) => {
      if (hiddenTypes[fac.type] || !fac.lat || !fac.lon) return;
      const color = facilityColors[fac.type] || '#64748b';
      const fm = new gmaps.Marker({
        position: { lat: Number(fac.lat), lng: Number(fac.lon) },
        map,
        title: fac.name || fac.type,
        icon: {
          path: gmaps.SymbolPath.CIRCLE,
          scale: 6,
          fillColor: color,
          fillOpacity: 0.95,
          strokeColor: '#ffffff',
          strokeWeight: 1.5,
        },
      });
      const fw = new gmaps.InfoWindow({
        content: `<div style="color:#111;font-size:12px"><strong>${fac.name || 'Unnamed Facility'}</strong><br/>${String(fac.type).replace(/_/g, ' ')}${fac.distance_km != null ? `<br/>${Number(fac.distance_km).toFixed(2)} km` : ''}</div>`,
      });
      fm.addListener('click', () => fw.open({ anchor: fm, map }));
      facMarkersRef.current.push(fm);
    });
  }, [centerLat, centerLon, hasPin, zoom, label, isApprox, status, interactive, facilities, hiddenTypes]);

  return <div ref={containerRef} style={{ height, width: '100%' }} />;
}

export default function PropertyMap({
  lat,
  lon,
  centerLat,
  centerLon,
  zoom,
  label,
  status,
  facilities = [],
  height = 420,
  interactive = false,
  onPick = null,
  onMapModeChange = null,
}) {
  const [hiddenTypes, setHiddenTypes] = useState({});
  const [googleFailed, setGoogleFailed] = useState(false);
  const [tileProvider, setTileProvider] = useState('osm');
  const [tileErrorCount, setTileErrorCount] = useState(0);
  const [recenterTick, setRecenterTick] = useState(0);
  const mapWrapperRef = useRef(null);

  const hasPin =
    Number.isFinite(Number(lat)) &&
    Number.isFinite(Number(lon)) &&
    lat !== '' &&
    lon !== '' &&
    lat !== null &&
    lon !== null;
  const viewLat = hasPin ? Number(lat) : (Number.isFinite(Number(centerLat)) ? Number(centerLat) : 12.3052);
  const viewLon = hasPin ? Number(lon) : (Number.isFinite(Number(centerLon)) ? Number(centerLon) : 76.6552);

  const useGoogle = isGoogleMapsKeyConfigured() && !googleFailed;

  useEffect(() => {
    if (onMapModeChange) {
      onMapModeChange(useGoogle ? 'google' : (isGoogleMapsKeyConfigured() ? 'fallback_error' : 'fallback_no_key'));
    }
  }, [useGoogle, onMapModeChange]);

  if (!interactive && !hasPin) {
    return (
      <div
        className="map-container"
        style={{
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-subtle, #F0F4F1)',
          border: '1px solid var(--border-subtle, #E3E8E4)',
          borderRadius: '10px',
        }}
      >
        <p style={{ color: 'var(--text-secondary, #4A5750)', fontSize: 13 }}>Map coordinates unavailable for this record.</p>
      </div>
    );
  }

  const center = [viewLat, viewLon];
  const stUp = (status || '').toUpperCase();
  const isSurveyed = stUp === 'SURVEYED' || stUp === 'EXACT' || stUp === 'EXACT_PARCEL' || stUp === 'DGPS' || stUp === 'SURVEY_GPS';
  const isApprox = !isSurveyed;
  const resolvedZoom = zoom || (interactive ? (hasPin ? 15 : 11) : (isApprox ? 13 : 15));

  const validFacilities = facilities.filter((f) => f.lat && f.lon);
  const presentTypes = [...new Set(validFacilities.map((f) => f.type))];
  const activeTileCfg = TILE_PROVIDERS[tileProvider] || TILE_PROVIDERS.osm;

  const toggleType = (type) => {
    setHiddenTypes((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  return (
    <div style={{ position: 'relative' }}>
      {presentTypes.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            padding: '10px 14px',
            background: '#F6F8F6',
            borderBottom: '1px solid #E3E8E4',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 11, fontWeight: 700, color: '#4A5750', marginRight: 4, letterSpacing: '0.03em' }}>
            FACILITY LAYERS ({validFacilities.filter((f) => !hiddenTypes[f.type]).length}/{validFacilities.length}):
          </span>
          {presentTypes.map((type) => {
            const active = !hiddenTypes[type];
            const color = facilityColors[type] || '#64748b';
            return (
              <button
                key={type}
                type="button"
                onClick={() => toggleType(type)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '3px 10px',
                  borderRadius: 999,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                  background: active ? '#FFFFFF' : '#F0F4F1',
                  color: active ? '#141C17' : '#6E7B73',
                  border: `1px solid ${active ? color : '#D2DBD4'}`,
                  opacity: active ? 1 : 0.6,
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
                {type.replace(/_/g, ' ')}
              </button>
            );
          })}
        </div>
      )}

      {/* Map Toolbar (Tiles & Re-center) */}
      {!useGoogle && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
            padding: '6px 12px',
            background: '#FFFFFF',
            borderBottom: '1px solid #E3E8E4',
            fontSize: 11,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#4A5750' }}>
            <span style={{ fontWeight: 600, color: '#144D29' }}>Basemap:</span>
            <button
              type="button"
              onClick={() => {
                setTileProvider('osm');
                setTileErrorCount(0);
              }}
              style={{
                padding: '2px 8px',
                borderRadius: 6,
                border: `1px solid ${tileProvider === 'osm' ? '#144D29' : '#D2DBD4'}`,
                background: tileProvider === 'osm' ? '#ECF5EE' : '#FFFFFF',
                color: tileProvider === 'osm' ? '#144D29' : '#4A5750',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              OSM Street
            </button>
            <button
              type="button"
              onClick={() => {
                setTileProvider('carto');
                setTileErrorCount(0);
              }}
              style={{
                padding: '2px 8px',
                borderRadius: 6,
                border: `1px solid ${tileProvider === 'carto' ? '#144D29' : '#D2DBD4'}`,
                background: tileProvider === 'carto' ? '#ECF5EE' : '#FFFFFF',
                color: tileProvider === 'carto' ? '#144D29' : '#4A5750',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Light Basemap
            </button>
            {tileErrorCount > 3 && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#85520E', fontWeight: 600 }}>
                <AlertTriangle size={12} /> Slow/blocked map tiles detected — switched/retry available
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              type="button"
              onClick={() => setRecenterTick((t) => t + 1)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 9px',
                borderRadius: 6,
                border: '1px solid #D2DBD4',
                background: '#F6F8F6',
                color: '#141C17',
                fontWeight: 600,
                cursor: 'pointer',
              }}
              title="Re-center & refresh map tiles"
            >
              <Crosshair size={12} /> Re-center
            </button>
            <button
              type="button"
              onClick={() => {
                setTileErrorCount(0);
                setRecenterTick((t) => t + 1);
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 9px',
                borderRadius: 6,
                border: '1px solid #D2DBD4',
                background: '#F6F8F6',
                color: '#141C17',
                fontWeight: 600,
                cursor: 'pointer',
              }}
              title="Reload tiles"
            >
              <RefreshCw size={12} /> Refresh Tiles
            </button>
          </div>
        </div>
      )}

      <div
        ref={mapWrapperRef}
        className="map-container"
        style={{ height, width: '100%', background: '#E9EFEA', position: 'relative' }}
      >
        {useGoogle ? (
          <GoogleMapCanvas
            centerLat={viewLat}
            centerLon={viewLon}
            hasPin={hasPin}
            zoom={resolvedZoom}
            label={label}
            isApprox={isApprox}
            status={status}
            interactive={interactive}
            onPick={onPick}
            facilities={validFacilities}
            hiddenTypes={hiddenTypes}
            height={height}
            onError={() => setGoogleFailed(true)}
          />
        ) : (
          <MapContainer
            center={center}
            zoom={resolvedZoom}
            minZoom={9}
            maxZoom={19}
            scrollWheelZoom={interactive}
            style={{ height: '100%', width: '100%', background: '#E9EFEA' }}
          >
            <TileLayer
              key={`${tileProvider}-${recenterTick}`}
              attribution={activeTileCfg.attribution}
              url={activeTileCfg.url}
              maxZoom={activeTileCfg.maxZoom}
              keepBuffer={4}
              updateWhenIdle={false}
              eventHandlers={{
                tileerror: () => {
                  setTileErrorCount((c) => {
                    const next = c + 1;
                    if (next >= 6 && tileProvider === 'osm') {
                      setTileProvider('carto');
                    }
                    return next;
                  });
                },
              }}
            />
            <ScaleControl position="bottomleft" imperial={false} />
            <LeafletLifecycleFix containerRef={mapWrapperRef} height={height} />
            <LeafletViewController center={center} zoom={resolvedZoom} key={`vc-${recenterTick}`} />
            <LeafletClickHandler interactive={interactive} onPick={onPick} />

            {hasPin && (
              <Marker
                position={center}
                draggable={interactive}
                eventHandlers={
                  interactive && onPick
                    ? {
                        dragend: (e) => {
                          const ll = e.target.getLatLng();
                          onPick(ll.lat, ll.lng);
                        },
                      }
                    : undefined
                }
              >
                <Popup>
                  <div style={{ fontWeight: 700, color: '#141C17' }}>{label || 'Property Location'}</div>
                  {isApprox && (
                    <div style={{ fontSize: 11, color: '#8C2D23', marginTop: 4 }}>
                      {stUp === 'MAP_SELECTED'
                        ? 'User-selected map pin (Not surveyed)'
                        : stUp === 'BROWSER_GPS' || stUp === 'DEVICE_GPS'
                        ? 'Browser/device GPS (Approximate)'
                        : stUp === 'USER_ENTERED'
                        ? 'User-entered coords (Not surveyed)'
                        : 'Approximation (Locality centroid)'}
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: '#4A5750', marginTop: 4 }}>
                    {viewLat.toFixed(6)}, {viewLon.toFixed(6)}
                  </div>
                </Popup>
              </Marker>
            )}

            {!interactive && hasPin && isApprox && (
              <Circle center={center} radius={1500} pathOptions={{ color: '#144D29', fillColor: '#1B6336', fillOpacity: 0.1, weight: 1 }} />
            )}

            {validFacilities.map((fac, i) => {
              if (hiddenTypes[fac.type]) return null;
              const icon = createIcon(facilityColors[fac.type] || '#64748b');
              return (
                <Marker key={`${fac.type}-${i}`} position={[fac.lat, fac.lon]} icon={icon}>
                  <Popup>
                    <div style={{ fontWeight: 600 }}>{fac.name || 'Unnamed Facility'}</div>
                    <div style={{ fontSize: 11, color: '#4A5750', textTransform: 'capitalize' }}>
                      Type: {fac.type.replace(/_/g, ' ')}
                    </div>
                    {fac.distance_km !== null && fac.distance_km !== undefined && (
                      <div style={{ fontSize: 11, color: '#144D29', fontWeight: 600 }}>
                        {Number(fac.distance_km).toFixed(2)} km away
                      </div>
                    )}
                  </Popup>
                </Marker>
              );
            })}
          </MapContainer>
        )}
      </div>
    </div>
  );
}
