import { apiClient } from './client.js'

export const authApi = {
  register: (payload) => apiClient.post('/api/auth/register', payload).then((r) => r.data),
  login: (payload) => apiClient.post('/api/auth/login', payload).then((r) => r.data),
  me: () => apiClient.get('/api/auth/me').then((r) => r.data),
}

export const systemApi = {
  health: () => apiClient.get('/api/health').then((r) => r.data),
  languages: () => apiClient.get('/api/languages').then((r) => r.data),
}

export const migrationsApi = {
  list: () => apiClient.get('/api/migrations').then((r) => r.data),
  stats: () => apiClient.get('/api/migrations/stats').then((r) => r.data),
  get: (id) => apiClient.get(`/api/migrations/${id}`).then((r) => r.data),
  create: (payload) => apiClient.post('/api/migrations', payload).then((r) => r.data),
  update: (id, payload) => apiClient.patch(`/api/migrations/${id}`, payload).then((r) => r.data),
  remove: (id) => apiClient.delete(`/api/migrations/${id}`).then((r) => r.data),
  migrate: (id, payload = {}) =>
    apiClient.post(`/api/migrations/${id}/migrate`, payload).then((r) => r.data),
  validate: (id, payload = {}) =>
    apiClient.post(`/api/migrations/${id}/validate`, payload).then((r) => r.data),
  generateTests: (id, payload = {}) =>
    apiClient.post(`/api/migrations/${id}/generate-tests`, payload).then((r) => r.data),
  verify: (id, payload = {}) =>
    apiClient.post(`/api/migrations/${id}/verify`, payload).then((r) => r.data),
  fix: (id, payload = {}) => apiClient.post(`/api/migrations/${id}/fix`, payload).then((r) => r.data),
  results: (id) => apiClient.get(`/api/migrations/${id}/results`).then((r) => r.data),
}
