import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, MapPin, BarChart2, GitCompare,
  FileText, FileDown, Database, Info, Layers
} from 'lucide-react';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/evaluate', label: 'Evaluate Property', icon: BarChart2 },
  { to: '/map', label: 'Map Analysis', icon: MapPin },
  { to: '/compare', label: 'Compare', icon: GitCompare },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/reports', label: 'Reports', icon: FileDown },
  { to: '/data-sources', label: 'Data Sources', icon: Database },
  { to: '/about', label: 'About', icon: Info },
  { to: '/admin', label: 'Admin Portal', icon: Layers },
];

export default function Navbar() {
  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <h1>Smart Land<br/>Evaluation</h1>
        <p>Mysuru, Karnataka</p>
      </div>
      <div className="nav-section">
        <div className="nav-section-label">Navigation</div>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            <Icon size={15} />
            {label}
          </NavLink>
        ))}
      </div>
      <div className="nav-footer">
        <div>Decision-support tool</div>
        <div style={{ marginTop: 2 }}>Not a legal/valuation service</div>
      </div>
    </nav>
  );
}
