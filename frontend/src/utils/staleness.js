/**
 * Client-side staleness tracking.
 *
 * The backend decides authoritatively whether a stored result is stale (it hashes
 * the code it tested). These helpers cover the *unsaved* edit case: while the user
 * types, the editor holds code that the server has never seen, so the displayed
 * result must be marked stale immediately rather than after a save round-trip.
 */

/** Cheap, stable-enough fingerprint of a code string for comparison in the UI. */
export function codeFingerprint(text) {
  const value = text || ''
  let hash = 5381
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) + hash + value.charCodeAt(index)) | 0
  }
  return `${value.length}:${(hash >>> 0).toString(36)}`
}

/**
 * Describes whether the current editor state still matches what was verified.
 *
 * @param {{sourceCode: string, migratedCode: string, sourceLanguage: string, targetLanguage: string}} current
 * @param {null | {sourceCode: string, migratedCode: string, sourceLanguage: string, targetLanguage: string}} verified
 * @returns {{stale: boolean, reasons: string[]}}
 */
export function describeStaleness(current, verified) {
  if (!verified) return { stale: false, reasons: [] }
  const reasons = []
  if (codeFingerprint(current.sourceCode) !== verified.sourceCode) {
    reasons.push('the source code changed')
  }
  if (codeFingerprint(current.migratedCode) !== verified.migratedCode) {
    reasons.push('the migrated code changed')
  }
  if (current.sourceLanguage !== verified.sourceLanguage) {
    reasons.push('the source language changed')
  }
  if (current.targetLanguage !== verified.targetLanguage) {
    reasons.push('the target language changed')
  }
  return { stale: reasons.length > 0, reasons }
}

/** Snapshot of the editor state a verification run was performed against. */
export function verificationSnapshot({ sourceCode, migratedCode, sourceLanguage, targetLanguage }) {
  return {
    sourceCode: codeFingerprint(sourceCode),
    migratedCode: codeFingerprint(migratedCode),
    sourceLanguage,
    targetLanguage,
  }
}

/**
 * True when a result was produced by the server against code that no longer
 * matches the editor. `result.stale` is the server's verdict; the fingerprint
 * comparison catches unsaved edits on top of it.
 */
export function isResultStale(result, current, snapshot) {
  if (!result) return false
  if (result.stale) return true
  return describeStaleness(current, snapshot).stale
}
