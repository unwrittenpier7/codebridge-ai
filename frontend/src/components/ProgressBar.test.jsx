import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ProgressBar from './ProgressBar.jsx'

describe('ProgressBar', () => {
  it('clamps values into the 0-100 range', () => {
    render(<ProgressBar value={150} label="Behavioral match" />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
})
