export const REGIONS = [
  'Alsace', 'Aquitaine', 'Auvergne', 'Basse-Normandie', 'Bourgogne', 'Bretagne', 'Centre',
  'Champagne-Ardenne', 'Corse', 'Franche-Comte', 'Haute-Normandie', 'Ile-de-France',
  'Languedoc-Roussillon', 'Limousin', 'Lorraine', 'Midi-Pyrenees', 'Nord-Pas-de-Calais',
  'Pays-de-la-Loire', 'Picardie', 'Poitou-Charentes', "Provence-Alpes-Cotes-D'Azur", 'Rhone-Alpes',
] as const

export const BRANDS = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B10', 'B11', 'B12', 'B13', 'B14'] as const

export interface QuoteForm {
  driver_age: string
  vehicle_age: string
  vehicle_power: string
  bonus_malus: string
  population_density: string
  fuel_type: 'Diesel' | 'Regular'
  vehicle_brand: string
  region_name: string
}

export interface QuoteRequest {
  driver_age: number
  vehicle_age: number
  vehicle_power: number
  bonus_malus: number
  population_density: number
  fuel_type: 'Diesel' | 'Regular'
  vehicle_brand: string
  region_name: string
}

export interface FactorLine {
  factor: string
  rated_value: string | number
  frequency_relativity: number
  severity_relativity: number
  combined_relativity: number
}

export interface CurvePoint {
  multiplier: number
  price: number
  conversion: number
  expected_profit: number
}

export interface DemandScenario {
  label: string
  price_sensitivity: number
  base_conversion: number
  points: CurvePoint[]
}

export interface Offer {
  simulated: boolean
  disclaimer: string
  segment: string
  technical_premium: number
  annual_technical_premium: number
  multiplier: number
  price: number
  annual_price: number
  market_price_proxy: number
  expected_conversion: number
  expected_profit_per_quote: number
  baseline_flat_loading_price: number
  sensitivity: DemandScenario[]
}

export interface QuoteResponse {
  pure_premium: number
  annual_pure_premium: number
  expected_claim_frequency: number
  expected_claim_severity: number
  base_premium: number
  large_loss_load: number
  breakdown: FactorLine[]
  model: string
  offer: Offer
}
