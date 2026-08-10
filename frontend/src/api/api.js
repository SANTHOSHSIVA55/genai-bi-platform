import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'genai_access_token';
const REFRESH_KEY = 'genai_refresh_token';
const USER_KEY = 'genai_user';

export const tokenStore = {
  getAccess: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  getUser: () => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY));
    } catch {
      return null;
    }
  },
  set: (tokens, user) => {
    if (tokens?.access_token) localStorage.setItem(TOKEN_KEY, tokens.access_token);
    if (tokens?.refresh_token) localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  setUser: (user) => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshPromise = null;

const doRefresh = async () => {
  const refresh = tokenStore.getRefresh();
  if (!refresh) {
    return null;
  }
  const resp = await axios.post(`${API_BASE}/api/auth/refresh`, {
    refresh_token: refresh,
  });
  const tokens = resp.data;
  tokenStore.set(tokens, tokens.user || tokenStore.getUser());
  return tokens.access_token;
};

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original?._retry && tokenStore.getRefresh()) {
      original._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = doRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const newToken = await refreshPromise;
        if (newToken) {
          original.headers.Authorization = `Bearer ${newToken}`;
          return api(original);
        }
      } catch (e) {
        // Refresh failed; fall through to logout handling below.
      }
    }
    if (error.response?.status === 401) {
      tokenStore.clear();
      window.dispatchEvent(new CustomEvent('genai:unauthorized'));
    }
    return Promise.reject(error);
  }
);

// Auth
export const registerUser = (data) => api.post('/api/auth/register', data);
export const loginUser = (data) => api.post('/api/auth/login', data);
export const refreshToken = (refresh_token) => api.post('/api/auth/refresh', { refresh_token });
export const logout = (refresh_token) => api.post('/api/auth/logout', { refresh_token });
export const getProfile = () => api.get('/api/auth/me');
export const verifyEmail = (token) => api.post('/api/auth/verify-email', { token });
export const resendVerification = (email) => api.post('/api/auth/resend-verification', { email });
export const forgotPassword = (email) => api.post('/api/auth/forgot-password', { email });
export const resetPassword = (token, password) => api.post('/api/auth/reset-password', { token, password });

// Data
export const uploadDataset = (formData) =>
  api.post('/api/data/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
export const getDatasets = (params) => api.get('/api/data/datasets', { params });
export const getDataset = (id) => api.get(`/api/data/datasets/${id}`);
export const getDatasetPreview = (id) => api.get(`/api/data/datasets/${id}/preview`);
export const getDatasetProfile = (id) => api.get(`/api/data/datasets/${id}/profile`);
export const getDatasetQuestions = (id) => api.get(`/api/data/datasets/${id}/questions`);
export const deleteDataset = (id) => api.delete(`/api/data/datasets/${id}`);

// Query
export const executeQuery = (data) => api.post('/api/query', data);
export const getQueryHistory = (params) => api.get('/api/query/history', { params });

// Admin
export const getAdminUsers = () => api.get('/api/admin/users');
export const updateAdminUser = (id, data) => api.patch(`/api/admin/users/${id}`, data);

export default api;
