import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api/client'
import { ErrorBanner } from '../src/components/ErrorBanner'
import { QueryBox } from '../src/components/QueryBox'
import { ResultsTable } from '../src/components/ResultsTable'
import { SafetyBadge } from '../src/components/SafetyBadge'
import { toCsv } from '../src/lib/csv'

describe('QueryBox', () => {
  it('submits on click and on Ctrl+Enter, not when too short', async () => {
    const onSubmit = vi.fn()
    const { rerender } = render(<QueryBox value="hi" onChange={() => {}} onSubmit={onSubmit} loading={false} />)
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()

    rerender(<QueryBox value="How many students?" onChange={() => {}} onSubmit={onSubmit} loading={false} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await userEvent.type(screen.getByLabelText('Your question'), '{Control>}{Enter}{/Control}')
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })
})

describe('SafetyBadge', () => {
  it('shows passed, blocked with reason, and nothing on error', () => {
    const { rerender, container } = render(<SafetyBadge status="ok" reason={null} />)
    expect(screen.getByText('Passed security sandbox')).toBeInTheDocument()
    rerender(<SafetyBadge status="blocked" reason="forbidden operation: DELETE" />)
    expect(screen.getByText('Blocked: forbidden operation: DELETE')).toBeInTheDocument()
    rerender(<SafetyBadge status="error" reason={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ResultsTable', () => {
  it('renders headers, NULLs, row count and the truncated notice', () => {
    render(<ResultsTable columns={['name', 'year']} rows={[['Alice', 2023], ['Bob', null]]} truncated />)
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['name', 'year'])
    expect(screen.getByText('NULL')).toBeInTheDocument()
    expect(screen.getByText(/2 rows/)).toHaveTextContent('truncated')
  })
})

describe('ErrorBanner', () => {
  it('explains a 429 in plain words', () => {
    render(<ErrorBanner error={new ApiError('rate_limit', 'Too many requests', 429)} />)
    expect(screen.getByRole('alert')).toHaveTextContent('wait a minute')
  })
})

describe('toCsv', () => {
  it('quotes commas, quotes and newlines; NULL is empty', () => {
    expect(toCsv(['a', 'b'], [['x,y', 'say "hi"'], [null, 'line\nbreak']])).toBe(
      'a,b\r\n"x,y","say ""hi"""\r\n,"line\nbreak"',
    )
  })
})
