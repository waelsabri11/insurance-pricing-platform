export const eur = (x: number, digits = 0) =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(x)

export const pct = (x: number, digits = 1) => `${(x * 100).toFixed(digits)}%`

export const FACTOR_LABELS: Record<string, string> = {
  driver_age_band: 'Driver age',
  vehicle_age_band: 'Vehicle age',
  vehicle_power: 'Vehicle power',
  bonus_malus: 'Bonus-malus',
  log_density: 'Population density',
  fuel_type: 'Fuel',
  vehicle_brand: 'Vehicle brand',
  region_name: 'Region',
}

export const factorLabel = (name: string) => FACTOR_LABELS[name] ?? name
