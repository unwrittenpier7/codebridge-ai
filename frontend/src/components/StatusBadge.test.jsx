import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatusBadge from './StatusBadge.jsx'

describe('StatusBadge', () => {
  it('renders the status in upper case', () => {
    render(<StatusBadge status="partial" />)
    expect(screen.getByTestId('status-badge')).toHaveTextContent('PARTIAL')
  })

  it('falls back to UNKNOWN when no status is given', () => {
    render(<StatusBadge />)
    expect(screen.getByTestId('status-badge')).toHaveTextContent('UNKNOWN')
  })
})
