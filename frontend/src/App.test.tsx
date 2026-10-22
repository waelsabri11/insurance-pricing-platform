import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { QUOTE } from './fixtures'

afterEach(() => vi.restoreAllMocks())

describe('App', () => {
  it('shows validation errors and does not call the API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    render(<App />)
    const age = screen.getByLabelText('Driver age')
    await userEvent.clear(age)
    await userEvent.type(age, '12')
    await userEvent.click(screen.getByRole('button', { name: 'Get quote' }))
    expect(await screen.findByText('Driver age must be between 18 and 100')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('posts the policy and renders premium, offer, breakdown, sensitivity and the simulated warning', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(QUOTE), { status: 200 }))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Get quote' }))
    await waitFor(() => expect(screen.getByTestId('offer-price')).toHaveTextContent('€224.00'))
    expect(screen.getByTestId('technical-premium')).toHaveTextContent('€186.67')
    expect(screen.getByTestId('conversion')).toHaveTextContent('11.0%')
    expect(screen.getByRole('note')).toHaveTextContent('Simulated')
    expect(screen.getByRole('list', { name: 'Factor-by-factor breakdown' }).children).toHaveLength(2)
    expect(screen.getByRole('img', { name: /versus price multiplier/ })).toBeInTheDocument()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/quote')
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({ driver_age: 35, region_name: 'Centre' })
  })

  it('switches the sensitivity chart metric', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(QUOTE), { status: 200 }))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Get quote' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Expected profit' }))
    expect(screen.getByRole('button', { name: 'Expected profit' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('surfaces API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ['body', 'driver_age'], msg: 'bad' }] }), { status: 422 }),
    )
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Get quote' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('driver_age: bad')
  })
})
