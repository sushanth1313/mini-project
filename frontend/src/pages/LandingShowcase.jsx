import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  MapPin,
  Search,
  ArrowRight,
  FileText,
  ShieldCheck,
  BarChart3,
  Map as MapIcon,
  ChevronDown,
  Sun,
  Moon,
  UserPlus,
  Menu,
  X,
  Compass,
  Building2,
  Crosshair,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import { getGisConfig } from '../api/client';

const PLATFORM_CARDS = [
  {
    title: 'AI Land Valuation',
    desc: 'Machine learning price-per-sq.ft estimates calibrated with Mysuru market comparables and SHAP driver transparency.',
    to: '/student/evaluate',
    icon: BarChart3,
  },
  {
    title: 'Geospatial Intelligence',
    desc: 'Interactive mapping across Mysuru District with spatial distance metrics and ward/village boundary verification.',
    to: '/student/evaluate',
    icon: MapIcon,
  },
  {
    title: 'Automatic Location Identification',
    desc: 'Point-in-polygon detection across KGIS taluks, hoblis, revenue villages, ULBs, and municipal wards with source cross-checking.',
    to: '/student/evaluate',
    icon: Crosshair,
  },
  {
    title: 'Nearby Facilities',
    desc: 'Informational audit across 14 neighborhood amenity categories (schools, hospitals, transit, banks, waterbodies) at 1, 3, and 5 km.',
    to: '/student/evaluate',
    icon: Layers,
  },
  {
    title: 'Infrastructure Assessment',
    desc: 'Structured 4-factor scoring covering Road access, Water availability, Electricity grid, and Public Transport.',
    to: '/student/evaluate',
    icon: Building2,
  },
  {
    title: 'AI Land Document Due Diligence',
    desc: 'OCR & consistency verification across Sale Deeds, RTC/Pahani, Mutation Extracts, Encumbrance Certificates, and Khata.',
    to: '/student/documents',
    icon: FileText,
  },
  {
    title: 'Comprehensive Evaluation Reports',
    desc: 'Audit-ready downloadable A4 PDF valuation and due-diligence packets with risk disclaimers and provenance.',
    to: '/student/properties',
    icon: ShieldCheck,
  },
];

const HOW_IT_WORKS = [
  {
    step: '01',
    title: 'Search or Pin Parcel Coordinates',
    desc: 'Select a Mysuru location via search or interactive map to inspect KGIS boundaries and resolve disagreements consciously.',
  },
  {
    step: '02',
    title: 'Verify Location & Classification',
    desc: 'Review KGIS Taluk, Hobli, Revenue Village, Ward, and geocoder cross-check status before confirming evaluation.',
  },
  {
    step: '03',
    title: 'Run ML Valuation & GIS Analysis',
    desc: 'Generate indicative market valuation alongside 4-factor infrastructure scoring and 14-category nearby facilities.',
  },
  {
    step: '04',
    title: 'Scrutinize Documents & Export PDF',
    desc: 'Upload property papers for cross-document consistency checks and download structured valuation & legal risk PDFs.',
  },
];

function PalaceBrandEmblem() {
  return (
    <svg width="42" height="30" viewBox="0 0 64 44" fill="none" aria-hidden="true">
      <path
        d="M32 4V9M29 12C29 9.5 35 9.5 35 12H29ZM25 18L32 12L39 18H25Z"
        stroke="#165332"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14 19V14M11 19H17M47 19H53M50 19V14M6 26H58M8 26V39H56V26"
        stroke="#165332"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15 39V30C15 28 19 28 19 30V39M24 39V28C24 25.5 29 25.5 29 28V39M35 39V28C35 25.5 40 25.5 40 28V39M45 39V30C45 28 49 28 49 30V39"
        stroke="#165332"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path d="M4 39H60" stroke="#165332" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function MysuruDistrictShape() {
  return (
    <svg width="118" height="106" viewBox="0 0 140 125" fill="none" aria-hidden="true">
      <path
        d="M36 22L54 14L75 18L92 12L108 26L121 44L114 66L126 84L107 103L84 114L62 104L45 109L28 94L15 74L22 50L16 34L36 22Z"
        fill="#E1ECE4"
        stroke="#CFE0D4"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function PalaceSkylineSilhouette() {
  return (
    <svg
      viewBox="0 0 1440 96"
      fill="none"
      preserveAspectRatio="none"
      style={{ width: '100%', height: 68, display: 'block', opacity: 0.22 }}
      aria-hidden="true"
    >
      <path
        d="M0 96V86H120V74H138V62H148V74H168V86H390V72H415V56H428V44H435V56H448V72H478V60H498V40L510 30L522 40V60H542V50H560V34L572 22L584 34V50H602V60H625V46H645V24L660 10L675 24V46H696V60H716V34L728 22L740 34V60H760V50H778V60H805V44L815 36L825 44V72H856V62H878V78H1060V66H1082V52H1094V66H1118V82H1300V72H1320V84H1440V96H0Z"
        fill="#7DA08A"
      />
    </svg>
  );
}

export default function LandingShowcase() {
  const navigate = useNavigate();
  const [quickQuery, setQuickQuery] = useState('');
  const [openMenu, setOpenMenu] = useState(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [softContrast, setSoftContrast] = useState(false);
  const [gisCov, setGisCov] = useState(null);

  useEffect(() => {
    getGisConfig()
      .then((res) => setGisCov(res.data?.kgis_coverage || null))
      .catch(() => setGisCov(null));
  }, []);

  const handleQuickSearch = (e) => {
    e.preventDefault();
    const q = quickQuery.trim();
    if (q) {
      navigate(`/student/evaluate?q=${encodeURIComponent(q)}`);
    } else {
      navigate('/student/evaluate');
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: softContrast ? '#F3F7F4' : '#FAFDFB',
        color: '#102019',
        fontFamily: "'Inter', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif",
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ── TOP HEADER BAR ───────────────────────────────────────────────────── */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 60,
          background: 'rgba(255, 255, 255, 0.96)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid #E6EFE9',
        }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: '0 auto',
            padding: '0 24px',
            height: 72,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 20,
          }}
        >
          {/* Left Logo */}
          <Link
            to="/"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              textDecoration: 'none',
              flexShrink: 0,
            }}
          >
            <PalaceBrandEmblem />
            <div style={{ lineHeight: 1.1 }}>
              <div style={{ fontSize: 19, fontWeight: 800, color: '#11261C', letterSpacing: '-0.02em' }}>
                SLV-GIS
              </div>
              <div style={{ fontSize: 11.5, fontWeight: 500, color: '#51675B', letterSpacing: '0.02em' }}>
                Mysuru
              </div>
            </div>
          </Link>

          {/* Center Navigation (Desktop) */}
          <nav
            className="slv-desktop-nav"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
            onMouseLeave={() => setOpenMenu(null)}
          >
            <Link
              to="/"
              style={{
                padding: '7px 16px',
                borderRadius: 9999,
                background: '#E7F0EA',
                color: '#174E31',
                fontSize: 13.5,
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Home
            </Link>

            <Link
              to="/about"
              style={{
                padding: '7px 14px',
                borderRadius: 9999,
                color: '#2B3E34',
                fontSize: 13.5,
                fontWeight: 500,
                textDecoration: 'none',
              }}
            >
              About
            </Link>

            {/* Features Dropdown */}
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setOpenMenu(openMenu === 'features' ? null : 'features')}
                onMouseEnter={() => setOpenMenu('features')}
                style={{
                  padding: '7px 14px',
                  borderRadius: 9999,
                  background: openMenu === 'features' ? '#F2F7F4' : 'transparent',
                  border: 'none',
                  color: '#2B3E34',
                  fontSize: 13.5,
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                Features <ChevronDown size={14} />
              </button>
              {openMenu === 'features' && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    marginTop: 6,
                    width: 245,
                    background: '#FFFFFF',
                    borderRadius: 14,
                    border: '1px solid #DFEAE3',
                    boxShadow: '0 14px 36px rgba(14, 42, 26, 0.12)',
                    padding: 8,
                    zIndex: 80,
                  }}
                >
                  {[
                    { label: 'GIS Property Evaluation', sub: 'Automated parcel & utility analysis', to: '/student/evaluate' },
                    { label: 'AI Document Analyzer', sub: 'RTC, Mutation, EC & Sale Deed OCR', to: '/student/documents' },
                    { label: 'Property Comparison', sub: 'Side-by-side parcel evaluation', to: '/student/compare' },
                    { label: 'Evaluation Dashboard', sub: 'Portfolio analytics & history', to: '/student' },
                  ].map((item) => (
                    <Link
                      key={item.label}
                      to={item.to}
                      onClick={() => setOpenMenu(null)}
                      style={{
                        display: 'block',
                        padding: '9px 12px',
                        borderRadius: 10,
                        textDecoration: 'none',
                        color: '#12251C',
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</div>
                      <div style={{ fontSize: 11.5, color: '#617469' }}>{item.sub}</div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Services Dropdown */}
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setOpenMenu(openMenu === 'services' ? null : 'services')}
                onMouseEnter={() => setOpenMenu('services')}
                style={{
                  padding: '7px 14px',
                  borderRadius: 9999,
                  background: openMenu === 'services' ? '#F2F7F4' : 'transparent',
                  border: 'none',
                  color: '#2B3E34',
                  fontSize: 13.5,
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                Services <ChevronDown size={14} />
              </button>
              {openMenu === 'services' && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    marginTop: 6,
                    width: 245,
                    background: '#FFFFFF',
                    borderRadius: 14,
                    border: '1px solid #DFEAE3',
                    boxShadow: '0 14px 36px rgba(14, 42, 26, 0.12)',
                    padding: 8,
                    zIndex: 80,
                  }}
                >
                  {[
                    { label: 'Land Price Prediction (ML)', sub: 'Mysuru District 7-taluk valuation', to: '/student/evaluate' },
                    { label: 'Utility & GIS Infrastructure', sub: 'Water, power, roads & ecology audit', to: '/student/evaluate' },
                    { label: 'PDF Intelligence Reports', sub: 'Download detailed 13-section PDFs', to: '/student/properties' },
                    { label: 'Admin Governance Portal', sub: 'Model metrics, audit & datasets', to: '/admin/login' },
                  ].map((item) => (
                    <Link
                      key={item.label}
                      to={item.to}
                      onClick={() => setOpenMenu(null)}
                      style={{
                        display: 'block',
                        padding: '9px 12px',
                        borderRadius: 10,
                        textDecoration: 'none',
                        color: '#12251C',
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</div>
                      <div style={{ fontSize: 11.5, color: '#617469' }}>{item.sub}</div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <Link
              to="/student/properties"
              style={{
                padding: '7px 14px',
                borderRadius: 9999,
                color: '#2B3E34',
                fontSize: 13.5,
                fontWeight: 500,
                textDecoration: 'none',
              }}
            >
              Reports
            </Link>

            <Link
              to="/help"
              style={{
                padding: '7px 14px',
                borderRadius: 9999,
                color: '#2B3E34',
                fontSize: 13.5,
                fontWeight: 500,
                textDecoration: 'none',
              }}
            >
              Help
            </Link>
          </nav>

          {/* Right Auth & Utility Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              type="button"
              onClick={() => setSoftContrast((s) => !s)}
              title="Toggle surface tone"
              aria-label="Toggle surface tone"
              style={{
                width: 34,
                height: 34,
                borderRadius: '50%',
                border: '1px solid #E3EDE7',
                background: '#FFFFFF',
                color: '#344B3E',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              {softContrast ? <Moon size={15} /> : <Sun size={15} />}
            </button>

            <span
              className="slv-desktop-nav"
              style={{ width: 1, height: 22, background: '#E2EBE5' }}
            />

            <Link
              to="/login"
              style={{
                padding: '8px 18px',
                borderRadius: 9999,
                border: '1px solid #C8D6CD',
                background: '#FFFFFF',
                color: '#183827',
                fontSize: 13.5,
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Login
            </Link>

            <Link
              to="/login?mode=register"
              className="slv-desktop-nav"
              style={{
                padding: '8px 18px',
                borderRadius: 9999,
                background: '#134D2C',
                color: '#FFFFFF',
                fontSize: 13.5,
                fontWeight: 600,
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: '0 4px 12px rgba(19, 77, 44, 0.22)',
              }}
            >
              <UserPlus size={14} /> Register
            </Link>

            <button
              type="button"
              onClick={() => setMobileNavOpen((o) => !o)}
              aria-label="Toggle navigation menu"
              className="slv-mobile-toggle"
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                border: '1px solid #D9E4DD',
                background: '#FFFFFF',
                color: '#12251C',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              {mobileNavOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>

        {/* Mobile Drawer */}
        {mobileNavOpen && (
          <div
            style={{
              padding: '12px 24px 18px',
              borderTop: '1px solid #E7EFE9',
              background: '#FFFFFF',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            {[
              { label: 'Home', to: '/' },
              { label: 'About', to: '/about' },
              { label: 'Evaluate Property', to: '/student/evaluate' },
              { label: 'AI Document Analyzer', to: '/student/documents' },
              { label: 'Reports', to: '/student/properties' },
              { label: 'Help', to: '/help' },
              { label: 'Register', to: '/login?mode=register' },
            ].map((m) => (
              <Link
                key={m.label}
                to={m.to}
                onClick={() => setMobileNavOpen(false)}
                style={{
                  padding: '9px 12px',
                  borderRadius: 10,
                  background: m.label === 'Home' ? '#E7F0EA' : 'transparent',
                  color: '#143323',
                  fontSize: 14,
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                {m.label}
              </Link>
            ))}
          </div>
        )}
      </header>

      {/* ── HERO SECTION ─────────────────────────────────────────────────────── */}
      <section
        style={{
          position: 'relative',
          overflow: 'hidden',
          background: '#EAF1EC',
          minHeight: 500,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        {/* Background Heritage Image anchored cleanly right-center */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: "url('/images/mysuru-palace-hero.jpg')",
            backgroundSize: 'cover',
            backgroundPosition: '76% center',
            backgroundRepeat: 'no-repeat',
          }}
        />

        {/* Soft bright atmospheric veil on left for crisp black/green typography */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background:
              'linear-gradient(92deg, rgba(250,253,251,0.96) 0%, rgba(247,251,248,0.91) 36%, rgba(244,249,245,0.62) 56%, rgba(255,255,255,0.06) 85%, rgba(255,255,255,0) 100%)',
          }}
        />

        {/* Subtle bottom-top soft ground mist */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background:
              'linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 40%, rgba(245,250,247,0.45) 100%)',
          }}
        />

        <div
          style={{
            position: 'relative',
            zIndex: 2,
            width: '100%',
            maxWidth: 1280,
            margin: '0 auto',
            padding: '56px 24px 96px',
          }}
        >
          <div style={{ maxWidth: 610 }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                padding: '6px 14px',
                borderRadius: 9999,
                background: '#E7F0EA',
                border: '1px solid #D3E3D8',
                color: '#195032',
                fontSize: 12.5,
                fontWeight: 600,
                marginBottom: 18,
              }}
            >
              <MapPin size={14} />
              Mysuru District, Karnataka
            </div>

            <h1
              style={{
                fontSize: 'clamp(2.05rem, 3.85vw, 3.2rem)',
                lineHeight: 1.12,
                fontWeight: 800,
                color: '#102019',
                letterSpacing: '-0.03em',
                margin: '0 0 14px',
              }}
            >
              Smart Land Valuation &amp;
              <br />
              Geospatial Analysis System
            </h1>

            <p
              style={{
                fontSize: 'clamp(1rem, 1.3vw, 1.18rem)',
                fontWeight: 600,
                color: '#1E3328',
                margin: '0 0 10px',
              }}
            >
              AI-Powered Property Intelligence for a Smarter Mysuru
            </p>

            <p
              style={{
                fontSize: 15,
                lineHeight: 1.6,
                color: '#465A4F',
                maxWidth: 480,
                margin: '0 0 28px',
              }}
            >
              Analyze property value, verify land documents and explore geospatial insights with
              confidence.
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center' }}>
              <Link
                to="/student/evaluate"
                style={{
                  padding: '13px 24px',
                  borderRadius: 9999,
                  background: '#134D2C',
                  color: '#FFFFFF',
                  fontSize: 14.5,
                  fontWeight: 600,
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 9,
                  boxShadow: '0 10px 24px rgba(19, 77, 44, 0.24)',
                }}
              >
                <Search size={16} />
                Evaluate Property
                <ArrowRight size={16} />
              </Link>

              <Link
                to="/student"
                style={{
                  padding: '12.5px 22px',
                  borderRadius: 9999,
                  background: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid #C8D6CD',
                  color: '#183827',
                  fontSize: 14.5,
                  fontWeight: 600,
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <FileText size={16} />
                Explore Platform
              </Link>
            </div>
          </div>
        </div>

        {/* Smooth curved bottom transition */}
        <svg
          viewBox="0 0 1440 72"
          preserveAspectRatio="none"
          style={{
            position: 'absolute',
            bottom: -1,
            left: 0,
            width: '100%',
            height: 54,
            zIndex: 3,
          }}
          aria-hidden="true"
        >
          <path
            d="M0,48 C360,4 1080,4 1440,48 L1440,72 L0,72 Z"
            fill={softContrast ? '#F3F7F4' : '#FAFDFB'}
          />
        </svg>
      </section>

      {/* ── FLOATING QUICK PROPERTY SEARCH BAR ───────────────────────────────── */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          width: '100%',
          maxWidth: 1120,
          margin: '-46px auto 0',
          padding: '0 24px',
        }}
      >
        <form
          onSubmit={handleQuickSearch}
          style={{
            background: '#FFFFFF',
            borderRadius: 20,
            border: '1px solid #E4EDE7',
            boxShadow: '0 18px 42px rgba(15, 42, 26, 0.08)',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingRight: 16 }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: 12,
                background: '#E7F0EA',
                color: '#154F2E',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <MapPin size={19} />
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#11251B' }}>
                Quick Property Search
              </div>
              <div style={{ fontSize: 12, color: '#617469' }}>
                Find and analyze any property in Mysuru District
              </div>
            </div>
          </div>

          <div
            className="slv-desktop-nav"
            style={{ width: 1, height: 34, background: '#E5EDE7' }}
          />

          <div
            style={{
              flex: '1 1 280px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: '#FBFDFC',
              border: '1px solid #DEE9E2',
              borderRadius: 12,
              padding: '0 14px',
              height: 46,
            }}
          >
            <Search size={17} style={{ color: '#586D61', flexShrink: 0 }} />
            <input
              type="text"
              value={quickQuery}
              onChange={(e) => setQuickQuery(e.target.value)}
              placeholder="Search by village, locality or survey number..."
              aria-label="Search by village, locality or survey number"
              style={{
                border: 'none',
                outline: 'none',
                background: 'transparent',
                width: '100%',
                fontSize: 14,
                color: '#102019',
              }}
            />
          </div>

          <button
            type="submit"
            style={{
              height: 46,
              padding: '0 26px',
              borderRadius: 12,
              border: 'none',
              background: '#134D2C',
              color: '#FFFFFF',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: '0 6px 16px rgba(19, 77, 44, 0.2)',
            }}
          >
            Search <ArrowRight size={15} />
          </button>
        </form>
      </div>

      {/* ── OUR PLATFORM: COMPREHENSIVE LAND INTELLIGENCE ────────────────────── */}
      <main
        id="platform-overview"
        style={{
          position: 'relative',
          flex: 1,
          maxWidth: 1280,
          width: '100%',
          margin: '0 auto',
          padding: '44px 24px 36px',
        }}
      >
        {/* Subtle Mysuru District Silhouette Badge on Right Margin */}
        <div
          className="slv-desktop-nav"
          style={{
            position: 'absolute',
            right: 28,
            top: 46,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            pointerEvents: 'none',
            opacity: 0.78,
          }}
        >
          <div style={{ position: 'relative' }}>
            <MysuruDistrictShape />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#174E31',
                fontSize: 11.5,
                fontWeight: 700,
                textAlign: 'center',
                lineHeight: 1.2,
              }}
            >
              <MapPin size={14} style={{ marginBottom: 2 }} />
              Mysuru
              <br />
              District
            </div>
          </div>
        </div>

        {/* Section Heading */}
        <div style={{ textAlign: 'center', marginBottom: 30 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 12,
              fontSize: 11.5,
              fontWeight: 700,
              letterSpacing: '0.14em',
              color: '#2B5B40',
              textTransform: 'uppercase',
              marginBottom: 8,
            }}
          >
            <span style={{ width: 28, height: 1, background: '#C7D8CD' }} />
            OUR PLATFORM
            <span style={{ width: 28, height: 1, background: '#C7D8CD' }} />
          </div>
          <h2
            style={{
              fontSize: 'clamp(1.45rem, 2.3vw, 2rem)',
              fontWeight: 800,
              color: '#102019',
              letterSpacing: '-0.02em',
              margin: 0,
            }}
          >
            Comprehensive Land Intelligence
          </h2>
        </div>

        {/* 7 Feature Highlight Cards */}
        <div className="slv-cards-grid" style={{ marginBottom: 56 }}>
          {PLATFORM_CARDS.map((card) => {
            const Icon = card.icon;
            return (
              <Link
                key={card.title}
                to={card.to}
                className="slv-feature-card"
                style={{
                  background: '#FFFFFF',
                  borderRadius: 14,
                  border: '1px solid #E3ECE6',
                  padding: '20px 18px 16px',
                  textDecoration: 'none',
                  color: '#102019',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  minHeight: 178,
                  boxShadow: '0 4px 16px rgba(15, 42, 26, 0.04)',
                  transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
                }}
              >
                <div>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 10,
                      background: '#E7F2EA',
                      color: '#175231',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginBottom: 14,
                    }}
                  >
                    <Icon size={19} />
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#102019', marginBottom: 6, lineHeight: 1.3 }}>
                    {card.title}
                  </div>
                  <p style={{ fontSize: 12.8, lineHeight: 1.5, color: '#5A6E63', margin: 0 }}>
                    {card.desc}
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                  <span
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#EEF5F0',
                      color: '#175231',
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <ArrowRight size={14} />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        {/* HOW IT WORKS SECTION */}
        <section style={{ marginBottom: 56 }}>
          <div style={{ textAlign: 'center', marginBottom: 26 }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.14em', color: '#2B5B40', textTransform: 'uppercase', marginBottom: 6 }}>
              WORKFLOW
            </div>
            <h2 style={{ fontSize: 'clamp(1.35rem, 2.1vw, 1.85rem)', fontWeight: 800, color: '#102019', letterSpacing: '-0.02em', margin: 0 }}>
              How SLV-GIS Evaluates a Mysuru Property
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 16 }}>
            {HOW_IT_WORKS.map((item) => (
              <div
                key={item.step}
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #E3ECE6',
                  borderRadius: 14,
                  padding: '20px',
                  boxShadow: '0 4px 14px rgba(15,42,26,0.03)',
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 800, color: '#144D29', background: '#E7F2EA', display: 'inline-block', padding: '3px 9px', borderRadius: 999, marginBottom: 10 }}>
                  STEP {item.step}
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#102019', marginBottom: 6 }}>{item.title}</div>
                <p style={{ fontSize: 13, lineHeight: 1.55, color: '#4A5750', margin: 0 }}>{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ABOUT & GEOGRAPHIC COVERAGE EDITORIAL SECTION */}
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 20,
            marginBottom: 20,
          }}
        >
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #E3ECE6',
              borderRadius: 14,
              padding: '26px 24px',
              boxShadow: '0 4px 14px rgba(15,42,26,0.03)',
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.12em', color: '#1B6336', textTransform: 'uppercase', marginBottom: 8 }}>
              ABOUT THE SYSTEM
            </div>
            <h3 style={{ fontSize: 20, fontWeight: 800, color: '#102019', marginBottom: 10 }}>
              Built for Transparent Property Due Diligence in Mysuru
            </h3>
            <p style={{ fontSize: 13.5, lineHeight: 1.65, color: '#4A5750', marginBottom: 14 }}>
              SLV-GIS unites machine learning price benchmarking, authoritative Karnataka GIS boundary verification,
              4-factor essential infrastructure scoring, 14-category facility discovery, and OCR-based legal document review
              for citizens, buyers, surveyors, and analysts.
            </p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Link to="/about" style={{ padding: '8px 16px', borderRadius: 9999, border: '1px solid #C8D6CD', color: '#144D29', fontSize: 13, fontWeight: 600, textDecoration: 'none' }}>
                Learn More
              </Link>
              <Link to="/disclaimers" style={{ padding: '8px 16px', borderRadius: 9999, color: '#4A5750', fontSize: 13, fontWeight: 500, textDecoration: 'none' }}>
                Valuation &amp; Legal Disclaimers
              </Link>
            </div>
          </div>

          <div
            style={{
              background: '#ECF5EE',
              border: '1px solid #CBE3D1',
              borderRadius: 14,
              padding: '26px 24px',
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.12em', color: '#144D29', textTransform: 'uppercase', marginBottom: 8 }}>
              GEOGRAPHIC COVERAGE (LIVE KGIS LAYERS)
            </div>
            <h3 style={{ fontSize: 20, fontWeight: 800, color: '#102019', marginBottom: 12 }}>
              Mysuru District Administrative Boundary Stack
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, marginBottom: 14 }}>
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #D2E5D7' }}>
                <div style={{ fontSize: 11, color: '#6E7B73' }}>KGIS Taluks / Hoblis</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#144D29' }}>
                  {gisCov ? `${gisCov.unique_kgis_taluks?.length || 8} Taluks · ${gisCov.hobli_polygons} Hoblis` : 'District Taluks & Hoblis'}
                </div>
              </div>
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #D2E5D7' }}>
                <div style={{ fontSize: 11, color: '#6E7B73' }}>Revenue Villages</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#144D29' }}>
                  {gisCov ? `${gisCov.revenue_village_polygons?.toLocaleString()} Villages` : 'KGIS Revenue Villages'}
                </div>
              </div>
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #D2E5D7' }}>
                <div style={{ fontSize: 11, color: '#6E7B73' }}>ULBs &amp; Municipal Wards</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#144D29' }}>
                  {gisCov ? `${gisCov.urban_local_body_polygons} ULBs · ${gisCov.municipal_ward_polygons} Wards` : 'Urban ULBs & Wards'}
                </div>
              </div>
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #D2E5D7' }}>
                <div style={{ fontSize: 11, color: '#6E7B73' }}>Rural GP Codes (LGD)</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#144D29' }}>
                  {gisCov ? `${gisCov.villages_with_lgd_gp_code?.toLocaleString()} Mapped` : 'KGIS GP Codes'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12, color: '#395244' }}>
              <CheckCircle2 size={15} style={{ color: '#144D29', flexShrink: 0, marginTop: 2 }} />
              <span>
                Covers urban Mysuru wards alongside Nanjangud, Hunsur, H.D. Kote, Saraguru, K.R. Nagar, Periyapatna, and T. Narasipura. Assembly constituency boundaries are not yet loaded and are clearly disclosed during verification.
              </span>
            </div>
          </div>
        </section>
      </main>

      {/* ── SUBTLE HERITAGE SKYLINE & FOOTER ──────────────────────────────────── */}
      <footer style={{ marginTop: 'auto' }}>
        <PalaceSkylineSilhouette />
        <div
          style={{
            borderTop: '1px solid #E3ECE6',
            background: '#F4F9F5',
            padding: '14px 24px',
          }}
        >
          <div
            style={{
              maxWidth: 1280,
              margin: '0 auto',
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              fontSize: 12.5,
              color: '#52685C',
            }}
          >
            <div>
              SLV-GIS Mysuru — Smart Land Valuation &amp; Geospatial Analysis System (All 7 Taluks)
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 18 }}>
              <Link to="/about" style={{ color: '#2F4A3B', textDecoration: 'none' }}>About</Link>
              <Link to="/help" style={{ color: '#2F4A3B', textDecoration: 'none' }}>Help</Link>
              <Link to="/privacy" style={{ color: '#2F4A3B', textDecoration: 'none' }}>Privacy</Link>
              <Link to="/terms" style={{ color: '#2F4A3B', textDecoration: 'none' }}>Terms</Link>
              <Link to="/disclaimers" style={{ color: '#2F4A3B', textDecoration: 'none' }}>Disclaimers</Link>
              <Link to="/admin/login" style={{ color: '#134D2C', fontWeight: 600, textDecoration: 'none' }}>
                Admin Portal
              </Link>
            </div>
          </div>
        </div>
      </footer>

      <style>{`
        .slv-cards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 18px;
          position: relative;
          z-index: 2;
        }
        .slv-feature-card:hover {
          transform: translateY(-3px);
          border-color: #B9D4C2 !important;
          box-shadow: 0 14px 30px rgba(15, 42, 26, 0.09) !important;
        }
        .slv-mobile-toggle {
          display: none;
        }
        @media (max-width: 1120px) {
          .slv-cards-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
        @media (max-width: 900px) {
          .slv-desktop-nav {
            display: none !important;
          }
          .slv-mobile-toggle {
            display: inline-flex !important;
          }
          .slv-cards-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
        @media (max-width: 560px) {
          .slv-cards-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
