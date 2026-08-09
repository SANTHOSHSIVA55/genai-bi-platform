import React, { createContext, useContext, useEffect, useCallback, useState } from 'react';
import {
  getProfile,
  loginUser,
  registerUser,
  logout as logoutApi,
  tokenStore,
} from '../api/api';

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const clearAuth = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener('genai:unauthorized', onUnauthorized);
    return () => window.removeEventListener('genai:unauthorized', onUnauthorized);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      const hasAccess = !!tokenStore.getAccess();
      const hasRefresh = !!tokenStore.getRefresh();
      if (!hasAccess && !hasRefresh) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const resp = await getProfile();
        if (!cancelled) {
          setUser(resp.data);
          tokenStore.setUser(resp.data);
        }
      } catch {
        if (!cancelled) clearAuth();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [clearAuth]);

  const login = useCallback(async (email, password) => {
    const resp = await loginUser({ email, password });
    tokenStore.set(resp.data, resp.data.user);
    setUser(resp.data.user);
    return resp.data.user;
  }, []);

  const register = useCallback(async ({ email, username, password }) => {
    const resp = await registerUser({ email, username, password });
    tokenStore.set(resp.data, resp.data.user);
    setUser(resp.data.user);
    return resp.data.user;
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh();
    if (refresh) {
      try {
        await logoutApi(refresh);
      } catch {
        // Ignore network/server errors on logout; always clear locally.
      }
    }
    clearAuth();
  }, [clearAuth]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
