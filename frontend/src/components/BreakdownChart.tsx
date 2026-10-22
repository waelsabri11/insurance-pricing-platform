import { factorLabel } from '../format'
import type { FactorLine } from '../types'

function ratedValue(l: FactorLine): string {
  if (typeof l.rated_value === 'string') return l.rated_value
  return l.factor === 'log_density' ? `${Math.round(Math.exp(l.rated_value))}/km²` : String(Math.round(l.rated_value))
}

// Diverging bars on a log scale: 1.00 is the base profile, left is cheaper, right dearer.
export function BreakdownChart({ lines }: { lines: FactorLine[] }) {
  const logs = lines.map((l) => Math.log(l.combined_relativity))
  const span = Math.max(0.1, ...logs.map(Math.abs))
  return (
    <ul className="breakdown" aria-label="Factor-by-factor breakdown">
      {lines.map((l, i) => {
        const half = (Math.abs(logs[i]) / span) * 50
        const up = logs[i] >= 0
        return (
          <li key={l.factor}>
            <span className="factor-name">
              {factorLabel(l.factor)} <small>{ratedValue(l)}</small>
            </span>
            <span className="bar-track" role="img" aria-label={`${factorLabel(l.factor)} relativity ${l.combined_relativity.toFixed(3)}`}>
              <span className="bar-axis" />
              <span
                className={`bar ${up ? 'up' : 'down'}`}
                style={{ left: up ? '50%' : `${50 - half}%`, width: `${half}%` }}
              />
            </span>
            <span className="rel">×{l.combined_relativity.toFixed(3)}</span>
          </li>
        )
      })}
    </ul>
  )
}
