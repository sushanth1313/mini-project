import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, FileSearch } from 'lucide-react';
import { getProperty, getProperties } from '../api/client';
import { PageHeader } from '../components/ui';
import DocumentAnalyzerApp from '../modules/documentAnalyzer/DocumentAnalyzerApp.jsx';

export default function Documents() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const propertyId = searchParams.get('property_id');

  const [property, setProperty] = useState(null);
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reloadProperty = async (targetId = propertyId) => {
    if (!targetId) return;
    try {
      const res = await getProperty(targetId);
      setProperty(res.data);
    } catch {
      // ignore silent refresh errors
    }
  };

  const analyzerPropertyInfo = useMemo(() => {
    if (!property) return null;
    const loc = property.village_or_locality || property.locality || '';
    const areaVal = property.land_area_sqft ?? property.area_sqft;
    return {
      property_id: String(property.id),
      property_label: property.property_name || property.name || loc || `Property #${property.id}`,
      district: property.district || 'Mysuru',
      taluk: property.taluk || '',
      locality: loc,
      village: loc,
      latitude: property.latitude != null ? String(property.latitude) : '',
      longitude: property.longitude != null ? String(property.longitude) : '',
      survey_number: property.survey_number || '',
      hissa_number: property.hissa_number || '',
      plot_number: property.plot_number || '',
      property_type: (property.property_type || 'residential_plot').toLowerCase().replace(/\s+/g, '_'),
      land_area: areaVal ? `${Math.round(Number(areaVal)).toLocaleString()} sq.ft.` : '',
    };
  }, [property]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (propertyId) {
          const res = await getProperty(propertyId);
          setProperty(res.data);
        }
        const listRes = await getProperties();
        setProperties(listRes.data.properties || []);

        if (!propertyId && listRes.data.properties?.length > 0) {
          navigate(`/student/documents?property_id=${listRes.data.properties[0].id}`, { replace: true });
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [propertyId, navigate]);

  if (loading) return <div className="loading-state"><div className="spinner"></div>Loading...</div>;

  return (
    <div className="page-body fade-in">
      <PageHeader
        eyebrow="Karnataka Land Records Scrutiny"
        title="AI Land Document Due-Diligence Analyzer"
        subtitle="Upload property papers once for multi-document classification, cross-document comparison, and due-diligence PDF report."
        icon={FileSearch}
        breadcrumbs={['Dashboard', 'Document Analyzer']}
        actions={
          <select
            className="form-control"
            style={{ width: 250 }}
            value={propertyId || ''}
            onChange={(e) => navigate(`/student/documents?property_id=${e.target.value}`)}
          >
            {properties.length === 0 && <option value="">Standalone Analysis</option>}
            {properties.map(p => (
              <option key={p.id} value={p.id}>{p.name || `Prop #${p.id}`} ({p.village_or_locality})</option>
            ))}
          </select>
        }
      />

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      <div style={{ marginBottom: 28 }}>
        <DocumentAnalyzerApp
          initialPropertyInfo={analyzerPropertyInfo}
          onAnalysisComplete={() => reloadProperty(property?.id)}
        />
      </div>
    </div>
  );
}
