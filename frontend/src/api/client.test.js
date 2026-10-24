import { describe, expect, it } from 'vitest'
import { describeError, isNetworkError } from './client.js'

describe('describeError', () => {
  it('returns a string detail verbatim', () => {
    expect(describeError({ response: { data: { detail: 'Nope' } } })).toBe('Nope')
  })

  it('joins FastAPI validation errors', () => {
    const error = {
      response: {
        data: { detail: [{ msg: 'field required' }, { msg: 'bad type' }] },
      },
    }
    expect(describeError(error)).toBe('field required; bad type')
  })

  it('renders the app-specific errors array', () => {
    const error = {
      response: {
        data: {
          detail: 'The request payload was invalid.',
          errors: [{ loc: ['body', 'count'], msg: 'must be <= 20' }],
        },
      },
    }
    expect(describeError(error)).toBe('The request payload was invalid.')
  })

  it('reports a timeout distinctly', () => {
    expect(describeError({ code: 'ECONNABORTED' })).toContain('timed out')
  })

  it('reports an unreachable backend distinctly', () => {
    expect(describeError({ message: 'Network Error' })).toContain('Cannot reach the backend')
  })

  it('never returns undefined', () => {
    expect(describeError({})).toBe('Unexpected error')
    expect(describeError(null)).toBe('Unexpected error')
  })

  it('does not leak an internal error_type into the message', () => {
    const error = {
      response: {
        data: { detail: 'An internal error occurred.', error_type: 'InternalServerError' },
      },
    }
    expect(describeError(error)).toBe('An internal error occurred.')
  })
})

describe('isNetworkError', () => {
  it('is true when there is no response', () => {
    expect(isNetworkError({ message: 'Network Error' })).toBe(true)
  })

  it('is false for a server verdict', () => {
    expect(isNetworkError({ response: { status: 500 } })).toBe(false)
  })
})
