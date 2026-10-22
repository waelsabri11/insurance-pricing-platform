import type { QuoteResponse } from './types'

const points = (b: number) =>
  [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3].map((m) => {
    const conversion = 1 / (1 + Math.exp(-(Math.log(0.15 / 0.85) - b * Math.log(m * 1.0))))
    return { multiplier: m, price: 200 * m, conversion, expected_profit: conversion * (200 * m * 0.75 - 20 - 120) }
  })

export const QUOTE: QuoteResponse = {
  pure_premium: 120,
  annual_pure_premium: 120,
  expected_claim_frequency: 0.06,
  expected_claim_severity: 1500,
  base_premium: 110,
  large_loss_load: 1.3,
  model: 'GLM',
  breakdown: [
    { factor: 'bonus_malus', rated_value: 90, frequency_relativity: 2, severity_relativity: 1, combined_relativity: 2 },
    { factor: 'driver_age_band', rated_value: '26-30', frequency_relativity: 0.7, severity_relativity: 1, combined_relativity: 0.7 },
  ],
  offer: {
    simulated: true,
    disclaimer: 'Conversion and profit come from an assumed demand model, not from observed quotes.',
    segment: '26-30|76-100|200-2000',
    technical_premium: 186.67,
    annual_technical_premium: 186.67,
    multiplier: 1.2,
    price: 224,
    annual_price: 224,
    market_price_proxy: 200,
    expected_conversion: 0.11,
    expected_profit_per_quote: 5,
    baseline_flat_loading_price: 205,
    sensitivity: [
      { label: 'base assumption', price_sensitivity: 4, base_conversion: 0.15, points: points(4) },
      { label: 'sensitivity 2', price_sensitivity: 2, base_conversion: 0.15, points: points(2) },
      { label: 'sensitivity 6', price_sensitivity: 6, base_conversion: 0.15, points: points(6) },
    ],
  },
}
