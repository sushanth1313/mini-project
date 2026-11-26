import { MapPin, Info } from 'lucide-react';

const ICONS = {
  school: '🏫',
  hospital: '🏥',
  supermarket: '🛒',
  bus_stop: '🚏',
  railway_station: '🚆',
  bank: '🏦',
  police: '👮',
};

const LABELS = {
  school: 'Schools',
  hospital: 'Hospitals / Clinics',
  supermarket: 'Supermarkets',
  bus_stop: 'Bus Stops',
  railway_station: 'Railway Stations',
  bank: 'Banks',
  police: 'Police Stations',
};

export default function FacilityList({ facilities }) {
  if (!facilities || Object.keys(facilities).length === 0) {
    return <div className="empty-state"><p>No facility data available</p></div>;
  }

  return (
    <div>
      {Object.entries(facilities).map(([type, data]) => {
        if (!data || data.nearest === null) return null;
        
        return (
          <div key={type} className="facility-item">
            <div>
              <div className="facility-name">
                <span>{ICONS[type] || '📍'}</span>
                <span style={{ fontWeight: 500 }}>{LABELS[type] || type}</span>
              </div>
              <div className="facility-count">
                {data.count_within_3km} within 3km
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="facility-dist">{data.nearest_distance_km} km</div>
              <div className="facility-count" style={{ color: 'var(--text-2)', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={data.nearest.name || 'Unnamed'}>
                {data.nearest.name || 'Unnamed'}
              </div>
            </div>
          </div>
        );
      })}
      
      <div className="alert alert-info" style={{ marginTop: 16 }}>
        <Info size={16} />
        <div>
          <strong>Data source:</strong> OpenStreetMap (Overpass API). Distance is calculated as straight-line (Haversine).
        </div>
      </div>
    </div>
  );
}
