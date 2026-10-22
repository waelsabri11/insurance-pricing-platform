import type { ReactNode } from 'react'
import { BRANDS, REGIONS } from '../types'
import type { QuoteForm } from '../types'
import { LIMITS } from '../validation'
import type { FormErrors } from '../validation'

interface Props {
  form: QuoteForm
  errors: FormErrors
  loading: boolean
  onChange: (patch: Partial<QuoteForm>) => void
  onSubmit: () => void
}

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && <small>{hint}</small>}
      {error && (
        <small role="alert" className="error" id={`${id}-error`}>
          {error}
        </small>
      )}
    </div>
  )
}

export function QuoteFormView({ form, errors, loading, onChange, onSubmit }: Props) {
  const num = (name: keyof typeof LIMITS, hint: string) => (
    <Field id={name} label={LIMITS[name].label} hint={hint} error={errors[name]}>
      <input
        id={name}
        inputMode="numeric"
        value={form[name]}
        aria-invalid={Boolean(errors[name])}
        aria-describedby={errors[name] ? `${name}-error` : undefined}
        onChange={(e) => onChange({ [name]: e.target.value })}
      />
    </Field>
  )
  return (
    <form
      className="card form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <h2>Policy</h2>
      <div className="grid">
        {num('driver_age', '18–100 years')}
        {num('vehicle_age', '0–100 years')}
        {num('vehicle_power', 'Fiscal power class, 4–15')}
        {num('bonus_malus', '50 = max bonus, 100 = no history')}
        {num('population_density', 'Inhabitants/km² of the town')}
        <Field id="fuel_type" label="Fuel">
          <select id="fuel_type" value={form.fuel_type} onChange={(e) => onChange({ fuel_type: e.target.value as QuoteForm['fuel_type'] })}>
            <option>Regular</option>
            <option>Diesel</option>
          </select>
        </Field>
        <Field id="vehicle_brand" label="Vehicle brand" error={errors.vehicle_brand}>
          <select id="vehicle_brand" value={form.vehicle_brand} onChange={(e) => onChange({ vehicle_brand: e.target.value })}>
            {BRANDS.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </Field>
        <Field id="region_name" label="Region" error={errors.region_name}>
          <select id="region_name" value={form.region_name} onChange={(e) => onChange({ region_name: e.target.value })}>
            {REGIONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </Field>
      </div>
      <p className="note">No gender or other protected characteristic is collected: gender-based pricing is banned in the EU.</p>
      <button type="submit" className="primary" disabled={loading}>
        {loading ? 'Pricing…' : 'Get quote'}
      </button>
    </form>
  )
}
