import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  ADMIN_PROFILE_KEY,
  ADMIN_TOKEN_KEY,
  adminLogin as apiAdminLogin,
  adminLogout as apiAdminLogout,
  fetchAdminSession,
} from '../api/adminClient';

const AdminAuthContext = createContext(null);

export function AdminAuthProvider({ children }) {
  const [admin, setAdmin] = useState(() => {
    try {
      const saved = localStorage.getItem(ADMIN_PROFILE_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [permissions, setPermissions] = useState(() => admin?.permissions || []);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    localStorage.removeItem(ADMIN_PROFILE_KEY);
    setAdmin(null);
    setPermissions([]);
  }, []);

  const verifySession = useCallback(async () => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (!token) {
      setAdmin(null);
      setPermissions([]);
      setLoading(false);
      return null;
    }
    try {
      const { data } = await fetchAdminSession();
      const perms = data.permissions || data.admin?.permissions || [];
      const profile = { ...(data.admin || {}), permissions: perms };
      localStorage.setItem(ADMIN_PROFILE_KEY, JSON.stringify(profile));
      setAdmin(profile);
      setPermissions(perms);
      return profile;
    } catch {
      clearSession();
      return null;
    } finally {
      setLoading(false);
    }
  }, [clearSession]);

  useEffect(() => {
    verifySession();
  }, [verifySession]);

  const login = async (username, password) => {
    const { data } = await apiAdminLogin(username, password);
    const token = data.token || data.access_token;
    if (!token) {
      throw new Error('Signed administrator token missing from server response.');
    }
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
    const perms = data.permissions || data.admin?.permissions || [];
    const profile = { ...(data.admin || {}), permissions: perms };
    localStorage.setItem(ADMIN_PROFILE_KEY, JSON.stringify(profile));
    setAdmin(profile);
    setPermissions(perms);
    return profile;
  };

  const logout = async () => {
    try {
      await apiAdminLogout();
    } catch {
      // Clear local session regardless of server revocation response
    }
    clearSession();
  };

  const hasPermission = (perm) => {
    if (!admin) return false;
    if (admin.role === 'SUPER_ADMIN') return true;
    return permissions.includes(perm);
  };

  return (
    <AdminAuthContext.Provider
      value={{
        admin,
        permissions,
        loading,
        isAuthenticated: Boolean(admin && localStorage.getItem(ADMIN_TOKEN_KEY)),
        login,
        logout,
        verifySession,
        hasPermission,
      }}
    >
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error('useAdminAuth must be used inside AdminAuthProvider');
  return ctx;
}
