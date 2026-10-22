import type { QuoteForm, QuoteRequest } from './types'

type Field = Exclude<keyof QuoteForm, 'fuel_type' | 'vehicle_brand' | 'region_name'>

// Same bounds as the API's Pydantic model (src/pricing/api.py).
export const LIMITS: Record<Field, { min: number; max: number; label: string }> = {
  driver_age: { min: 18, max: 100, label: 'Driver age' },
  vehicle_age: { min: 0, max: 100, label: 'Vehicle age' },
  vehicle_power: { min: 4, max: 15, label: 'Vehicle power' },
  bonus_malus: { min: 50, max: 230, label: 'Bonus-malus' },
  population_density: { min: 1, max: 27000, label: 'Population density' },
}

export type FormErrors = Partial<Record<keyof QuoteForm, string>>

export function validate(form: QuoteForm): { errors: FormErrors; request: QuoteRequest | null } {
  const errors: FormErrors = {}
  const numbers: Record<string, number> = {}
  for (const [field, { min, max, label }] of Object.entries(LIMITS) as [Field, (typeof LIMITS)[Field]][]) {
    const raw = form[field].trim()
    const n = Number(raw)
    if (raw === '') errors[field] = `${label} is required`
    else if (!Number.isInteger(n)) errors[field] = `${label} must be a whole number`
    else if (n < min || n > max) errors[field] = `${label} must be between ${min} and ${max}`
    else numbers[field] = n
  }
  if (!form.vehicle_brand) errors.vehicle_brand = 'Brand is required'
  if (!form.region_name) errors.region_name = 'Region is required'
  if (Object.keys(errors).length > 0) return { errors, request: null }
  return {
    errors,
    request: {
      driver_age: numbers.driver_age,
      vehicle_age: numbers.vehicle_age,
      vehicle_power: numbers.vehicle_power,
      bonus_malus: numbers.bonus_malus,
      population_density: numbers.population_density,
      fuel_type: form.fuel_type,
      vehicle_brand: form.vehicle_brand,
      region_name: form.region_name,
    },
  }
}
