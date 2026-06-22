import React, { createContext, useContext, useState, useEffect } from 'react';
import { getProfile } from '../api/api';

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const guestUser = {
    id: 'guest-user-id-123456',
    username: 'guest',
    email: 'guest@example.com',
    role: 'user'
  };

  const [user, setUser] = useState(guestUser);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setUser(guestUser);
    setLoading(false);
  }, []);

  const login = (token, userData) => {};
  const logout = () => {};

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
