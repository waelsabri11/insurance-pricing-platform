import type { QuoteRequest, QuoteResponse } from './types'

export async function fetchQuote(req: QuoteRequest, signal?: AbortSignal): Promise<QuoteResponse> {
  const res = await fetch('/api/quote', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.at(-1)}: ${d.msg}`).join('; ')
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail)
  }
  return res.json()
}
