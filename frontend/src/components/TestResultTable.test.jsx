import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TestResultTable from './TestResultTable.jsx'

const results = [
  {
    id: 1,
    test_number: 1,
    description: 'normal case',
    input: '5\n10\n',
    original_output: '15',
    migrated_output: '16',
    status: 'FAIL',
    difference: 'Line 1: expected \'15\' but received \'16\'.',
    migrated_exit_code: 0,
  },
]

describe('TestResultTable', () => {
  it('shows outputs and the behavioral difference for a failing test', () => {
    render(<TestResultTable results={results} />)
    expect(screen.getByText('Test #1')).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText('16')).toBeInTheDocument()
    expect(screen.getByText(/expected/)).toBeInTheDocument()
  })

  it('renders an empty state without results', () => {
    render(<TestResultTable results={[]} />)
    expect(screen.getByText('No test results yet.')).toBeInTheDocument()
  })
})
