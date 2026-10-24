import { useCallback, useRef, useState } from 'react'
import { describeError } from '../api/client.js'

/**
 * Runs an async operation with duplicate-submission protection.
 *
 * A double click or a second click while a request is in flight would otherwise
 * fire two identical expensive operations (a second AI migration, a second
 * verification run). `run` ignores any call made while one is already active, so
 * the guard cannot be raced by React's async state updates.
 */
export function useAsyncAction() {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const inFlight = useRef(false)

  const run = useCallback(async (label, action, { successMessage } = {}) => {
    if (inFlight.current) return undefined
    inFlight.current = true
    setBusy(label)
    setError('')
    setNotice('')
    try {
      const result = await action()
      if (successMessage) setNotice(successMessage)
      return result
    } catch (err) {
      setError(describeError(err))
      return undefined
    } finally {
      inFlight.current = false
      setBusy('')
    }
  }, [])

  const clearMessages = useCallback(() => {
    setError('')
    setNotice('')
  }, [])

  return { busy, error, notice, run, clearMessages, setError, setNotice, isBusy: Boolean(busy) }
}
