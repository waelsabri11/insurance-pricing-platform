import { useState } from 'react'
import { eur, pct } from '../format'
import type { Offer } from '../types'

type Metric = 'conversion' | 'expected_profit'

const COLORS = ['#1f6feb', '#8250df', '#bf8700', '#cf222e']
const W = 520
const H = 240
const PAD = { l: 52, r: 22, t: 12, b: 34 }

export function SensitivityChart({ offer }: { offer: Offer }) {
  const [metric, setMetric] = useState<Metric>('conversion')
  const scenarios = offer.sensitivity
  const values = scenarios.flatMap((s) => s.points.map((p) => p[metric]))
  const lo = Math.min(0, ...values)
  const hi = Math.max(...values) || 1
  const mults = scenarios[0].points.map((p) => p.multiplier)
  const x = (m: number) => PAD.l + ((m - mults[0]) / (mults[mults.length - 1] - mults[0])) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b)
  const fmt = (v: number) => (metric === 'conversion' ? pct(v, 0) : eur(v))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo))

  return (
    <div>
      <div className="toggle" role="group" aria-label="Sensitivity metric">
        <button type="button" aria-pressed={metric === 'conversion'} onClick={() => setMetric('conversion')}>
          Conversion
        </button>
        <button type="button" aria-pressed={metric === 'expected_profit'} onClick={() => setMetric('expected_profit')}>
          Expected profit
        </button>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`Simulated ${metric} versus price multiplier`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="grid" />
            <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="tick">
              {fmt(t)}
            </text>
          </g>
        ))}
        {mults.filter((_, i) => i % 2 === 0).map((m) => (
          <text key={m} x={x(m)} y={H - 12} textAnchor="middle" className="tick">
            ×{m.toFixed(2)}
          </text>
        ))}
        {scenarios.map((s, i) => (
          <polyline
            key={s.label}
            fill="none"
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={i === 0 ? 3 : 1.75}
            strokeDasharray={i === 0 ? undefined : '5 3'}
            points={s.points.map((p) => `${x(p.multiplier)},${y(p[metric])}`).join(' ')}
          />
        ))}
        <line x1={x(offer.multiplier)} x2={x(offer.multiplier)} y1={PAD.t} y2={H - PAD.b} className="marker" />
      </svg>
      <ul className="legend">
        {scenarios.map((s, i) => (
          <li key={s.label}>
            <span className="swatch" style={{ background: COLORS[i % COLORS.length] }} />
            {s.label} (b = {s.price_sensitivity})
          </li>
        ))}
        <li>
          <span className="swatch marker-swatch" />
          optimized multiplier ×{offer.multiplier.toFixed(2)}
        </li>
      </ul>
    </div>
  )
}
