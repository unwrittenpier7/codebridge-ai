import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi } from '../api/endpoints.js'
import { getStoredToken, onUnauthorized, setStoredToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getStoredToken()))

  useEffect(() => {
    // Any 401 from anywhere in the app ends the session immediately.
    onUnauthorized(() => setUser(null))
  }, [])

  useEffect(() => {
    if (!getStoredToken()) {
      setLoading(false)
      return
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => setStoredToken(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (credentials) => {
    const data = await authApi.login(credentials)
    setStoredToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback(async (payload) => {
    const data = await authApi.register(payload)
    setStoredToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    // Tell the server first (best effort), then always clear local state so a
    // failed call can never leave the user appearing signed in.
    try {
      await authApi.logout()
    } catch {
      // The token is stateless; local cleanup below is what matters.
    }
    setStoredToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, isAuthenticated: Boolean(user) }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}
