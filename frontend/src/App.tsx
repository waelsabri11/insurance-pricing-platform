import { useRef, useState } from 'react'
import { fetchQuote } from './api'
import { BreakdownChart } from './components/BreakdownChart'
import { QuoteFormView } from './components/QuoteFormView'
import { SensitivityChart } from './components/SensitivityChart'
import { eur, pct } from './format'
import type { QuoteForm, QuoteResponse } from './types'
import { validate } from './validation'
import type { FormErrors } from './validation'

export const DEFAULT_FORM: QuoteForm = {
  driver_age: '35',
  vehicle_age: '4',
  vehicle_power: '6',
  bonus_malus: '50',
  population_density: '600',
  fuel_type: 'Regular',
  vehicle_brand: 'B12',
  region_name: 'Centre',
}

export default function App() {
  const [form, setForm] = useState<QuoteForm>(DEFAULT_FORM)
  const [errors, setErrors] = useState<FormErrors>({})
  const [quote, setQuote] = useState<QuoteResponse | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)

  async function submit() {
    const { errors: found, request } = validate(form)
    setErrors(found)
    if (!request) return
    controller.current?.abort()
    controller.current = new AbortController()
    setLoading(true)
    setApiError(null)
    try {
      setQuote(await fetchQuote(request, controller.current.signal))
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setQuote(null)
        setApiError((e as Error).message)
      }
    } finally {
      setLoading(false)
    }
  }

  const offer = quote?.offer
  return (
    <main>
      <header>
        <h1>Motor liability quote</h1>
        <p>GLM technical premium on French motor data (freMTPL2) and a price optimized on simulated demand.</p>
      </header>
      <div className="layout">
        <QuoteFormView form={form} errors={errors} loading={loading} onChange={(p) => setForm({ ...form, ...p })} onSubmit={submit} />
        <section className="results" aria-live="polite">
          {apiError && (
            <div className="card error-card" role="alert">
              Could not get a quote: {apiError}
            </div>
          )}
          {!quote && !apiError && <div className="card placeholder">Fill in the policy and press “Get quote”.</div>}
          {quote && offer && (
            <>
              <div className="card kpis">
                <div>
                  <span className="kpi-label">Technical premium (break-even)</span>
                  <strong data-testid="technical-premium">{eur(offer.annual_technical_premium, 2)}</strong>
                  <small>per year · expected claims {eur(quote.annual_pure_premium, 2)}</small>
                </div>
                <div className="highlight">
                  <span className="kpi-label">Optimized offer</span>
                  <strong data-testid="offer-price">{eur(offer.annual_price, 2)}</strong>
                  <small>
                    ×{offer.multiplier.toFixed(3)} of technical · segment {offer.segment}
                  </small>
                </div>
                <div>
                  <span className="kpi-label">Expected conversion</span>
                  <strong data-testid="conversion">{pct(offer.expected_conversion)}</strong>
                  <small>market price proxy {eur(offer.market_price_proxy, 0)}</small>
                </div>
              </div>
              <p className="simulated" role="note">
                <b>Simulated.</b> {offer.disclaimer} freMTPL2 contains no quotes or renewals, so conversion and profit are
                illustrations of an assumed demand curve, not observed results.
              </p>
              <div className="card">
                <h2>Where the premium comes from</h2>
                <p className="note">
                  Combined frequency × severity relativity per factor, versus the base profile (×1.000). The product of all factors
                  times the base premium ({eur(quote.base_premium, 2)}) gives the expected claims.
                </p>
                <BreakdownChart lines={quote.breakdown} />
              </div>
              <div className="card">
                <h2>Price sensitivity (simulated)</h2>
                <p className="note">
                  Conversion and expected profit per quote as the price multiplier moves from ×0.80 to ×1.30 of the technical premium,
                  under three assumed price sensitivities.
                </p>
                <SensitivityChart offer={offer} />
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  )
}
