/** Device health 0-100. Red below the alert threshold, amber within 20 points above it, green otherwise. */
export function healthTone(health: number, threshold = 50): 'red' | 'amber' | 'green' {
  return health < threshold ? 'red' : health < threshold + 20 ? 'amber' : 'green'
}

const FILL = { red: 'bg-red-500', amber: 'bg-amber-500', green: 'bg-emerald-500' }
const TEXT = { red: 'text-red-600', amber: 'text-amber-600', green: 'text-emerald-600' }

export function HealthBar({ health, threshold = 50, reasons = [], label = true, dark = false, className = '' }: { health: number; threshold?: number; reasons?: string[]; label?: boolean; dark?: boolean; className?: string }) {
  const tone = healthTone(health, threshold)
  return (
    <div className={`flex items-center gap-2 ${className}`} title={reasons.length ? reasons.join(', ') : 'Healthy'} role="meter" aria-label="Device health" aria-valuemin={0} aria-valuemax={100} aria-valuenow={health}>
      <div className={`relative h-2 min-w-14 flex-1 overflow-hidden rounded-full ${dark ? 'bg-white/15' : 'bg-ink-900/8'}`}>
        <div className={`h-full origin-left rounded-full transition-[transform,background-color] duration-700 ${FILL[tone]}`} style={{ width: '100%', transform: `scaleX(${health / 100})` }} />
        <span className={`absolute inset-y-0 w-px ${dark ? 'bg-white/40' : 'bg-ink-900/25'}`} style={{ left: `${threshold}%` }} aria-hidden="true" />
      </div>
      {label && <span className={`w-9 text-right text-xs font-bold tabular-nums ${TEXT[tone]}`}>{health}%</span>}
    </div>
  )
}
