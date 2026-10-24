import axios from 'axios'

const TOKEN_KEY = 'codebridge.token'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 180000,
})

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

let unauthorizedHandler = null

/** Registers the callback invoked when the server rejects the session. */
export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

apiClient.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    // An expired or revoked token must drop the session rather than leave the
    // UI stuck showing a signed-in shell that cannot load anything.
    if (status === 401 && getStoredToken()) {
      setStoredToken(null)
      if (unauthorizedHandler) unauthorizedHandler()
    }
    return Promise.reject(error)
  },
)

/** Normalizes FastAPI error payloads into a readable message. */
export function describeError(error) {
  const data = error?.response?.data
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  if (data?.errors?.length) {
    return data.errors.map((e) => `${(e.loc || []).join('.')}: ${e.msg}`).join('; ')
  }
  if (error?.code === 'ECONNABORTED') return 'The request timed out. The operation may still be running.'
  if (!error?.response && error?.message) {
    return `Cannot reach the backend: ${error.message}`
  }
  if (error?.message) return error.message
  return 'Unexpected error'
}

/** True when the failure is a connectivity problem rather than a server verdict. */
export function isNetworkError(error) {
  return !error?.response
}

