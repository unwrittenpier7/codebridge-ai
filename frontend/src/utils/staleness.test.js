import { describe, expect, it } from 'vitest'
import {
  codeFingerprint,
  describeStaleness,
  isResultStale,
  verificationSnapshot,
} from './staleness.js'

const base = {
  sourceCode: 'print(1)\n',
  migratedCode: 'console.log(1)\n',
  sourceLanguage: 'python',
  targetLanguage: 'javascript',
}

describe('codeFingerprint', () => {
  it('is stable for identical text', () => {
    expect(codeFingerprint('abc')).toBe(codeFingerprint('abc'))
  })

  it('changes when the text changes', () => {
    expect(codeFingerprint('abc')).not.toBe(codeFingerprint('abd'))
  })

  it('distinguishes whitespace-only edits', () => {
    expect(codeFingerprint('a b')).not.toBe(codeFingerprint('a  b'))
  })

  it('handles empty input', () => {
    expect(codeFingerprint('')).toBe(codeFingerprint(undefined))
  })
})

describe('describeStaleness', () => {
  it('is fresh when nothing changed', () => {
    const snapshot = verificationSnapshot(base)
    expect(describeStaleness(base, snapshot).stale).toBe(false)
  })

  it('is stale after a source edit', () => {
    const snapshot = verificationSnapshot(base)
    const result = describeStaleness({ ...base, sourceCode: 'print(2)\n' }, snapshot)
    expect(result.stale).toBe(true)
    expect(result.reasons).toContain('the source code changed')
  })

  it('is stale after a migrated-code edit', () => {
    const snapshot = verificationSnapshot(base)
    const result = describeStaleness({ ...base, migratedCode: 'console.log(2)\n' }, snapshot)
    expect(result.stale).toBe(true)
    expect(result.reasons).toContain('the migrated code changed')
  })

  it('is stale after a source language change', () => {
    const snapshot = verificationSnapshot(base)
    const result = describeStaleness({ ...base, sourceLanguage: 'java' }, snapshot)
    expect(result.stale).toBe(true)
    expect(result.reasons).toContain('the source language changed')
  })

  it('is stale after a target language change', () => {
    const snapshot = verificationSnapshot(base)
    const result = describeStaleness({ ...base, targetLanguage: 'go' }, snapshot)
    expect(result.stale).toBe(true)
    expect(result.reasons).toContain('the target language changed')
  })

  it('reports no staleness when there is no baseline', () => {
    expect(describeStaleness(base, null).stale).toBe(false)
  })

  it('collects every reason at once', () => {
    const snapshot = verificationSnapshot(base)
    const result = describeStaleness(
      { sourceCode: 'x', migratedCode: 'y', sourceLanguage: 'java', targetLanguage: 'go' },
      snapshot,
    )
    expect(result.reasons).toHaveLength(4)
  })
})

describe('isResultStale', () => {
  it('trusts the server verdict', () => {
    const snapshot = verificationSnapshot(base)
    expect(isResultStale({ stale: true }, base, snapshot)).toBe(true)
  })

  it('detects an unsaved edit the server has not seen', () => {
    const snapshot = verificationSnapshot(base)
    const edited = { ...base, migratedCode: 'changed' }
    expect(isResultStale({ stale: false }, edited, snapshot)).toBe(true)
  })

  it('is false with no result', () => {
    expect(isResultStale(null, base, verificationSnapshot(base))).toBe(false)
  })
})
