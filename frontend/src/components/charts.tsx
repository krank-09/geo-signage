import { useEffect, useRef, useState } from 'react'

/** Eases a number up to its target (re-runs when the target changes). */
export function useCountUp(target: number, ms = 900): number {
  const [v, setV] = useState(0)
  const from = useRef(0)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setV(target); return }
    const start = performance.now(), a = from.current
    let raf = 0
    const tick = (t: number) => {
      const p = Math.min((t - start) / ms, 1)
      const e = 1 - Math.pow(1 - p, 4)
      setV(a + (target - a) * e)
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

export const CountUp = ({ value, decimals = 0 }: { value: number; decimals?: number }) => <>{useCountUp(value).toFixed(decimals)}</>

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(300)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(120, e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

/** Smooth line with soft area fill and glowing dots; the line draws itself on mount. */
export function LineChart({ values, labels, height = 110, color = '#5b49eb', max: maxProp }: { values: number[]; labels?: string[]; height?: number; color?: string; max?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const pad = 10, h = height
  const max = Math.max(maxProp ?? 0, ...values, 1)
  const pts = values.map((v, i) => [pad + (i * (w - pad * 2)) / Math.max(values.length - 1, 1), h - pad - (v / max) * (h - pad * 2 - 6)] as const)
  const path = pts.reduce((d, [x, y], i, a) => {
    if (i === 0) return `M${x},${y}`
    const [px, py] = a[i - 1], cx = (px + x) / 2
    return `${d} C${cx},${py} ${cx},${y} ${x},${y}`
  }, '')
  const area = pts.length ? `${path} L${pts[pts.length - 1][0]},${h} L${pts[0][0]},${h} Z` : ''
  const gid = useRef(`g${Math.random().toString(36).slice(2, 8)}`).current
  return (
    <div ref={ref} className="relative w-full" style={{ height }} onMouseLeave={() => setHover(null)}>
      <svg width={w} height={h} className="overflow-visible">
        <defs>
          <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.28" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient>
        </defs>
        {[0.33, 0.66].map((f) => <line key={f} x1={pad} x2={w - pad} y1={h * f} y2={h * f} stroke="#5b49eb" strokeOpacity="0.07" strokeDasharray="3 5" />)}
        {area && <path d={area} fill={`url(#${gid})`} style={{ animation: 'area-in 1s ease-out 0.5s both' }} />}
        {path && <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1} style={{ animation: 'draw 1.2s var(--ease-out-expo) 0.15s forwards' }} />}
        {pts.map(([x, y], i) => (
          <g key={i} style={{ animation: `fade 0.4s ease-out ${0.5 + i * 0.03}s both` }} onMouseEnter={() => setHover(i)}>
            <circle cx={x} cy={y} r="14" fill="transparent" />
            {(i === pts.length - 1 || hover === i) && <circle cx={x} cy={y} r="9" fill={color} opacity="0.18" />}
            <circle cx={x} cy={y} r={i === pts.length - 1 || hover === i ? 4.5 : 3} fill="#fff" stroke={color} strokeWidth="2" />
          </g>
        ))}
      </svg>
      {hover !== null && pts[hover] && (
        <div className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg bg-ink-900 px-2 py-1 text-xs font-semibold text-white" style={{ left: pts[hover][0], top: pts[hover][1] - 12 }}>
          {values[hover]}{labels?.[hover] ? ` · ${labels[hover]}` : ''}
        </div>
      )}
    </div>
  )
}

/** Rounded bars that grow from the baseline; the tallest is highlighted like the reference. */
export function BarChart({ values, labels, height = 96 }: { values: number[]; labels?: string[]; height?: number }) {
  const max = Math.max(...values, 1)
  const peak = values.indexOf(Math.max(...values))
  return (
    <div className="flex items-end gap-1.5" style={{ height: height + (labels ? 18 : 0) }}>
      {values.map((v, i) => (
        <div key={i} className="group relative flex h-full flex-1 flex-col justify-end">
          <div className="w-full origin-bottom rounded-t-[10px] transition-colors duration-300" title={`${v}`}
            style={{ height: `${Math.max((v / max) * height, v ? 6 : 4)}px`, background: i === peak && v > 0 ? 'linear-gradient(180deg,#7160f3,#5b49eb)' : '#dcd7ff', animation: `grow 0.8s var(--ease-out-expo) ${0.1 + i * 0.045}s both` }} />
          {labels && <span className="mt-1 text-center text-[10px] text-ink-400">{labels[i]}</span>}
          <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 rounded-md bg-ink-900 px-1.5 py-0.5 text-[10px] font-semibold text-white opacity-0 transition group-hover:opacity-100">{v}</span>
        </div>
      ))}
    </div>
  )
}
