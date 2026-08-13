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

/* ───── Simple Response Cache for UI Caching ───── */
const apiCache = new Map();
const CACHE_TTL = 30000; // 30 seconds cache TTL

export const cacheStore = {
  get: (key) => {
    const item = apiCache.get(key);
    if (!item) return null;
    if (Date.now() - item.timestamp > CACHE_TTL) {
      apiCache.delete(key);
      return null;
    }
    return item.data;
  },
  set: (key, data) => {
    apiCache.set(key, { data, timestamp: Date.now() });
  },
  clear: () => {
    apiCache.clear();
  }
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
let unauthorizedDispatched = false;

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
        // Refresh failed; handle token clearing and logout.
      }
    }
    if (error.response?.status === 401) {
      tokenStore.clear();
      cacheStore.clear();
      if (!unauthorizedDispatched) {
        unauthorizedDispatched = true;
        window.dispatchEvent(new CustomEvent('genai:unauthorized'));
        setTimeout(() => { unauthorizedDispatched = false; }, 1000);
      }
    }
    return Promise.reject(error);
  }
);

// Auth
export const registerUser = (data) => api.post('/api/auth/register', data);
export const loginUser = (data) => api.post('/api/auth/login', data);
export const refreshToken = (refresh_token) => api.post('/api/auth/refresh', { refresh_token });
export const logout = (refresh_token) => api.post('/api/auth/logout', { refresh_token }).finally(() => {
  cacheStore.clear();
});
export const getProfile = () => api.get('/api/auth/me');
export const verifyEmail = (token) => api.post('/api/auth/verify-email', { token });
export const resendVerification = (email) => api.post('/api/auth/resend-verification', { email });
export const forgotPassword = (email) => api.post('/api/auth/forgot-password', { email });
export const resetPassword = (token, password) => api.post('/api/auth/reset-password', { token, password });

// Data
export const uploadDataset = (formData) => {
  cacheStore.clear(); // Clear cache on new uploads
  return api.post('/api/data/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const getDatasets = async (params) => {
  const cacheKey = `datasets_${JSON.stringify(params || {})}`;
  const cached = cacheStore.get(cacheKey);
  if (cached) return { data: cached };
  
  const resp = await api.get('/api/data/datasets', { params });
  cacheStore.set(cacheKey, resp.data);
  return resp;
};

export const getDataset = async (id) => {
  const cacheKey = `dataset_${id}`;
  const cached = cacheStore.get(cacheKey);
  if (cached) return { data: cached };

  const resp = await api.get(`/api/data/datasets/${id}`);
  cacheStore.set(cacheKey, resp.data);
  return resp;
};

export const getDatasetPreview = (id) => api.get(`/api/data/datasets/${id}/preview`);

export const getDatasetRows = (id, params = {}) =>
  api.get(`/api/data/datasets/${id}/rows`, { params });

export const getDatasetProfile = async (id) => {
  const cacheKey = `profile_${id}`;
  const cached = cacheStore.get(cacheKey);
  if (cached) return { data: cached };

  const resp = await api.get(`/api/data/datasets/${id}/profile`);
  cacheStore.set(cacheKey, resp.data);
  return resp;
};

export const getDatasetQuestions = async (id) => {
  const cacheKey = `questions_${id}`;
  const cached = cacheStore.get(cacheKey);
  if (cached) return { data: cached };

  const resp = await api.get(`/api/data/datasets/${id}/questions`);
  cacheStore.set(cacheKey, resp.data);
  return resp;
};

export const deleteDataset = (id) => {
  cacheStore.clear(); // Clear cache on deletes
  return api.delete(`/api/data/datasets/${id}`);
};

// Query
export const executeQuery = (data, config = {}) => api.post('/api/query', data, config);
export const getQueryHistory = (params) => api.get('/api/query/history', { params });
export const deleteHistoryEntry = (queryId) => api.delete(`/api/query/history/${queryId}`);
export const clearQueryHistory = () => api.delete('/api/query/history');

// Admin
export const getAdminUsers = () => api.get('/api/admin/users');
export const updateAdminUser = (id, data) => api.patch(`/api/admin/users/${id}`, data);

export default api;
