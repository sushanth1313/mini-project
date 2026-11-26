import { useState, useEffect } from 'react';
import { getProperties, deleteProperty } from '../api/client';
import { Trash2 } from 'lucide-react';

export default function AdminProperties() {
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProperties();
  }, []);

  const loadProperties = async () => {
    setLoading(true);
    try {
      const res = await getProperties();
      setProperties(res.data.properties);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const handleDelete = async (id) => {
    if (confirm("Are you sure you want to delete this property?")) {
      try {
        await deleteProperty(id);
        loadProperties();
      } catch (e) {
        alert("Failed to delete property.");
      }
    }
  };

  if (loading) return <div className="loading-state"><div className="spinner"></div>Loading...</div>;

  return (
    <div className="page-body">
      <div className="page-header fade-in">
        <div className="page-header-text">
          <h2>Manage Properties</h2>
          <p>View and delete student-entered properties.</p>
        </div>
      </div>
      <div className="card fade-in">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Locality</th>
              <th>Asking Price (₹)</th>
              <th>Evaluation</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {properties.map(p => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>{p.name || 'Unnamed'}</td>
                <td>{p.village_or_locality}</td>
                <td>{p.asking_price_inr ? p.asking_price_inr.toLocaleString() : 'N/A'}</td>
                <td>{p.latest_evaluation ? 'Completed' : 'Pending'}</td>
                <td>
                  <button className="btn btn-ghost" onClick={() => handleDelete(p.id)} style={{color: 'var(--danger)'}}>
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {properties.length === 0 && (
              <tr>
                <td colSpan="6" style={{textAlign: 'center', color: 'var(--text-3)'}}>No properties found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
