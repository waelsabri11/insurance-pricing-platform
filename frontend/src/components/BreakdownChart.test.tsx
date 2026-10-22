import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { QUOTE } from '../fixtures'
import { BreakdownChart } from './BreakdownChart'

describe('BreakdownChart', () => {
  it('labels each factor and colours up/down bars', () => {
    const { container } = render(<BreakdownChart lines={QUOTE.breakdown} />)
    expect(screen.getByText('Bonus-malus')).toBeInTheDocument()
    expect(screen.getByText('×2.000')).toBeInTheDocument()
    expect(screen.getByText('×0.700')).toBeInTheDocument()
    expect(container.querySelectorAll('.bar.up')).toHaveLength(1)
    expect(container.querySelectorAll('.bar.down')).toHaveLength(1)
  })
})
