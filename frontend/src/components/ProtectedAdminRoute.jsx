import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext';

export default function ProtectedAdminRoute({ children, requiredPermission = null }) {
  const { isAuthenticated, loading, admin, hasPermission } = useAdminAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F6F8F6] text-[#4A5750] text-sm font-mono">
        Verifying signed administrator session...
      </div>
    );
  }

  if (!isAuthenticated || !admin) {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  }

  const allowed = !requiredPermission
    ? true
    : Array.isArray(requiredPermission)
      ? requiredPermission.some((p) => hasPermission(p))
      : hasPermission(requiredPermission);

  if (!allowed) {
    return (
      <div className="p-8 max-w-xl mx-auto mt-12 rounded-xl border border-amber-500/30 bg-white shadow-sm text-[#141C17] space-y-3">
        <div className="flex items-center gap-2 text-[#85520E] font-semibold text-sm">
          <ShieldAlert className="w-5 h-5" /> Insufficient Role Permission ({admin.role})
        </div>
        <p className="text-xs text-[#4A5750] leading-relaxed">
          Your administrator role (<span className="font-mono text-[#85520E]">{admin.role}</span>) does not include
          permission <span className="font-mono text-[#141C17]">{requiredPermission}</span>. Access attempts are
          logged to the immutable audit trail.
        </p>
      </div>
    );
  }

  return children;
}
