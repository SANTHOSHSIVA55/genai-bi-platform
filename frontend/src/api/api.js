import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// Auth
export const registerUser = (data) => api.post('/api/auth/register', data);
export const loginUser = (data) => api.post('/api/auth/login', data);
export const getProfile = () => api.get('/api/auth/me');

// Data
export const uploadDataset = (formData) =>
  api.post('/api/data/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
export const getDatasets = () => api.get('/api/data/datasets');
export const deleteDataset = (id) => api.delete(`/api/data/datasets/${id}`);

// Query
export const executeQuery = (data) => api.post('/api/query', data);
export const getQueryHistory = () => api.get('/api/query/history');

export default api;
