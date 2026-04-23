import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Bell, TrendingDown, Circle } from 'lucide-react'
import { screenerService } from '@/services/api'

const BG      = '#06060b'
const CARD    = '#0c0c14'
const BORDER  = 'rgba(255,255,255,0.06)'
const TEXT    = '#f0f0f5'
const SEC     = '#8b8b9e'
const DIM     = '#55556a'
const ACCENT  = '#c8ff00'
const GREEN   = '#22c55e'
const RED     = '#ef4444'
const ORANGE  = '#f59e0b'

interface WatchRow {
  symbol: string
  price: number
  score: number
  distance: number
  ts: string
}

interface AlertRow {
  id: number
  symbol: string
  alert_type: 'APPROACHING' | 'BREAK'
  price: number
  score: number | null
  ts: string
}

interface HistoryPoint { ts: string; price: number }

function formatTime(iso: string) {
  try {
    return new Date(iso + 'Z').toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch { return iso }
}

function trendArrow(distance: number): string {
  if (distance <= 0.01) return '↓↓↓'
  if (distance <= 0.03) return '↓↓'
  if (distance <= 0.06) return '↓'
  return '→'
}

// ── Mini SVG sparkline ────────────────────────────────────────────────────────
function Sparkline({ points, width = 120, height = 32 }: {
  points: HistoryPoint[]
  width?: number
  height?: number
}) {
  if (points.length < 2) return <span style={{ color: DIM, fontSize: '0.65rem' }}>no data</span>

  const prices = points.map(p => p.price)
  const mn = Math.min(...prices)
  const mx = Math.max(...prices)
  const range = mx - mn || 0.001
  const pad = 2

  const xs = points.map((_, i) => pad + (i / (points.length - 1)) * (width - pad * 2))
  const ys = prices.map(p => pad + (1 - (p - mn) / range) * (height - pad * 2))

  const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')

  // dollar line y position
  const dollarY = pad + (1 - (1.00 - mn) / range) * (height - pad * 2)
  const showDollar = dollarY >= pad && dollarY <= height - pad

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {showDollar && (
        <line x1={pad} y1={dollarY} x2={width - pad} y2={dollarY}
          stroke={RED} strokeWidth={0.8} strokeDasharray="3,2" opacity={0.5} />
      )}
      <path d={d} fill="none" stroke={ACCENT} strokeWidth={1.5} />
    </svg>
  )
}

// ── Price chart for selected symbol ──────────────────────────────────────────
function PriceChart({ symbol, breakTimes }: { symbol: string; breakTimes: string[] }) {
  const { data } = useQuery({
    queryKey: ['screener-history', symbol],
    queryFn: () => screenerService.getHistory(symbol, 30).then(r => r.data),
    refetchInterval: 10000,
  })

  const points: HistoryPoint[] = data?.points ?? []
  if (points.length < 2) {
    return (
      <div style={{ color: DIM, fontSize: '0.78rem', padding: '24px 0' }}>
        Waiting for history data for {symbol}…
      </div>
    )
  }

  const W = 640
  const H = 140
  const PAD = { top: 16, right: 24, bottom: 28, left: 56 }
  const iW = W - PAD.left - PAD.right
  const iH = H - PAD.top - PAD.bottom

  const prices = points.map(p => p.price)
  const mn = Math.min(...prices, 1.00) - 0.005
  const mx = Math.max(...prices, 1.00) + 0.005
  const range = mx - mn

  const px = (i: number) => PAD.left + (i / (points.length - 1)) * iW
  const py = (price: number) => PAD.top + (1 - (price - mn) / range) * iH

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${px(i).toFixed(1)},${py(p.price).toFixed(1)}`).join(' ')

  const dollarY = py(1.00)

  // Y axis ticks
  const ticks = 4
  const tickPrices = Array.from({ length: ticks + 1 }, (_, i) => mn + (i / ticks) * range)

  // X axis: first and last time labels
  const firstTime = formatTime(points[0].ts)
  const lastTime = formatTime(points[points.length - 1].ts)

  // Break dots
  const breakDots = breakTimes.flatMap(bt => {
    const btMs = new Date(bt + 'Z').getTime()
    let closest = 0
    let closestDiff = Infinity
    points.forEach((p, i) => {
      const diff = Math.abs(new Date(p.ts + 'Z').getTime() - btMs)
      if (diff < closestDiff) { closestDiff = diff; closest = i }
    })
    return closestDiff < 120000 ? [closest] : []
  })

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: W, display: 'block' }}>
      {/* Y axis ticks */}
      {tickPrices.map((p, i) => (
        <g key={i}>
          <line x1={PAD.left - 4} y1={py(p)} x2={PAD.left} y2={py(p)} stroke={BORDER} strokeWidth={1} />
          <text x={PAD.left - 8} y={py(p) + 4} textAnchor="end"
            style={{ fontSize: 9, fill: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
            ${p.toFixed(3)}
          </text>
        </g>
      ))}

      {/* Grid lines */}
      {tickPrices.map((p, i) => (
        <line key={i} x1={PAD.left} y1={py(p)} x2={W - PAD.right} y2={py(p)}
          stroke={BORDER} strokeWidth={0.5} />
      ))}

      {/* $1.00 reference line */}
      <line x1={PAD.left} y1={dollarY} x2={W - PAD.right} y2={dollarY}
        stroke={RED} strokeWidth={1} strokeDasharray="5,3" opacity={0.7} />
      <text x={W - PAD.right + 4} y={dollarY + 4}
        style={{ fontSize: 9, fill: RED, fontFamily: 'JetBrains Mono, monospace' }}>
        $1.00
      </text>

      {/* Price line */}
      <path d={linePath} fill="none" stroke={ACCENT} strokeWidth={1.8} />

      {/* BREAK dots */}
      {breakDots.map((idx, i) => (
        <circle key={i} cx={px(idx)} cy={py(points[idx].price)} r={4}
          fill={RED} stroke="#06060b" strokeWidth={1.5} />
      ))}

      {/* X axis labels */}
      <text x={PAD.left} y={H - 6} style={{ fontSize: 9, fill: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
        {firstTime}
      </text>
      <text x={W - PAD.right} y={H - 6} textAnchor="end"
        style={{ fontSize: 9, fill: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
        {lastTime}
      </text>
    </svg>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function ScreenerPage() {
  const [minScore, setMinScore] = useState(50)
  const [priceRange, setPriceRange] = useState<[number, number]>([0.90, 1.15])
  const [alertFilter, setAlertFilter] = useState<'all' | 'APPROACHING' | 'BREAK'>('all')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: statusData } = useQuery({
    queryKey: ['screener-status'],
    queryFn: () => screenerService.getStatus().then(r => r.data),
    refetchInterval: 15000,
  })

  const { data: watchlistData } = useQuery({
    queryKey: ['screener-watchlist', minScore, priceRange],
    queryFn: () => screenerService.getWatchlist(minScore, priceRange[0], priceRange[1]).then(r => r.data),
    refetchInterval: 10000,
  })

  const { data: alertsData } = useQuery({
    queryKey: ['screener-alerts', alertFilter],
    queryFn: () => screenerService.getAlerts(alertFilter, 30).then(r => r.data),
    refetchInterval: 10000,
  })

  const watchlist: WatchRow[] = watchlistData?.rows ?? []
  const alerts: AlertRow[] = alertsData?.alerts ?? []
  const running: boolean = statusData?.running ?? false
  const universeSize: number = statusData?.universe_size ?? 0

  const breakTimesForSymbol = alerts
    .filter(a => a.symbol === selectedSymbol && a.alert_type === 'BREAK')
    .map(a => a.ts)

  return (
    <div style={{ background: BG, minHeight: '100%', padding: '24px 28px', color: TEXT }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
            Dollar Break Screener
          </h1>
          <p style={{ margin: '2px 0 0', fontSize: '0.72rem', color: SEC }}>
            Stocks approaching $1.00 from above
          </p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: running ? GREEN : DIM,
              display: 'inline-block',
              boxShadow: running ? `0 0 6px ${GREEN}` : 'none',
            }} />
            <span style={{ fontSize: '0.7rem', color: SEC, fontFamily: 'JetBrains Mono, monospace' }}>
              {running ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
          {universeSize > 0 && (
            <span style={{ fontSize: '0.7rem', color: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
              {universeSize} symbols
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 20 }}>

        {/* ── Sidebar filters ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: '0.65rem', color: DIM, letterSpacing: '0.12em', marginBottom: 12, textTransform: 'uppercase' }}>
              Filters
            </div>

            <label style={{ fontSize: '0.72rem', color: SEC, display: 'block', marginBottom: 4 }}>
              Min score: <span style={{ color: ACCENT }}>{minScore}</span>
            </label>
            <input type="range" min={0} max={100} step={5} value={minScore}
              onChange={e => setMinScore(Number(e.target.value))}
              style={{ width: '100%', accentColor: ACCENT, marginBottom: 14 }} />

            <label style={{ fontSize: '0.72rem', color: SEC, display: 'block', marginBottom: 4 }}>
              Price min: <span style={{ color: ACCENT }}>${priceRange[0].toFixed(2)}</span>
            </label>
            <input type="range" min={0.80} max={1.15} step={0.01} value={priceRange[0]}
              onChange={e => setPriceRange([Number(e.target.value), priceRange[1]])}
              style={{ width: '100%', accentColor: ACCENT, marginBottom: 14 }} />

            <label style={{ fontSize: '0.72rem', color: SEC, display: 'block', marginBottom: 4 }}>
              Price max: <span style={{ color: ACCENT }}>${priceRange[1].toFixed(2)}</span>
            </label>
            <input type="range" min={0.90} max={1.50} step={0.01} value={priceRange[1]}
              onChange={e => setPriceRange([priceRange[0], Number(e.target.value)])}
              style={{ width: '100%', accentColor: ACCENT, marginBottom: 14 }} />

            <div style={{ fontSize: '0.65rem', color: DIM, letterSpacing: '0.1em', marginBottom: 8, textTransform: 'uppercase' }}>
              Alert type
            </div>
            {(['all', 'APPROACHING', 'BREAK'] as const).map(t => (
              <button key={t}
                onClick={() => setAlertFilter(t)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  background: alertFilter === t ? 'rgba(200,255,0,0.06)' : 'none',
                  border: `1px solid ${alertFilter === t ? 'rgba(200,255,0,0.2)' : 'transparent'}`,
                  borderRadius: 6, padding: '6px 10px', marginBottom: 4,
                  color: alertFilter === t ? ACCENT : SEC,
                  fontSize: '0.72rem', cursor: 'pointer',
                }}>
                {t === 'all' ? 'All' : t === 'APPROACHING' ? '🟡 Approaching' : '🔴 Break'}
              </button>
            ))}
          </div>

          {/* Active alerts panel */}
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
              <Bell size={12} style={{ color: ORANGE }} />
              <span style={{ fontSize: '0.65rem', color: DIM, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                Recent Alerts
              </span>
            </div>
            {alerts.length === 0 ? (
              <div style={{ fontSize: '0.72rem', color: DIM }}>No alerts yet</div>
            ) : (
              alerts.slice(0, 10).map(a => (
                <div key={a.id}
                  onClick={() => setSelectedSymbol(a.symbol)}
                  style={{
                    padding: '7px 0', borderBottom: `1px solid ${BORDER}`,
                    cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'flex-start',
                  }}>
                  <span style={{ fontSize: '0.8rem', marginTop: -1 }}>
                    {a.alert_type === 'BREAK' ? '🔴' : '🟡'}
                  </span>
                  <div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 700, color: TEXT }}>{a.symbol}</span>
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: a.alert_type === 'BREAK' ? RED : ORANGE }}>
                        ${a.price.toFixed(4)}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.62rem', color: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
                      {formatTime(a.ts)} · score {a.score?.toFixed(0) ?? '—'}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Main content ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Watchlist table */}
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{
              padding: '12px 16px', borderBottom: `1px solid ${BORDER}`,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <TrendingDown size={13} style={{ color: ACCENT }} />
              <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Watchlist</span>
              <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
                {watchlist.length} matches
              </span>
            </div>

            {watchlist.length === 0 ? (
              <div style={{ padding: '32px 16px', textAlign: 'center', color: DIM, fontSize: '0.78rem' }}>
                {running ? 'No stocks match current filters.' : 'Pipeline offline — start the ingestion process.'}
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,0.02)' }}>
                    {['Symbol', 'Price', 'Distance', 'Score', 'Trend', 'Sparkline', 'Updated'].map(h => (
                      <th key={h} style={{
                        padding: '8px 12px', textAlign: 'left',
                        fontSize: '0.62rem', color: DIM, fontWeight: 600,
                        letterSpacing: '0.08em', textTransform: 'uppercase',
                        borderBottom: `1px solid ${BORDER}`,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {watchlist.map((row, i) => {
                    const isSelected = selectedSymbol === row.symbol
                    const scoreColor = row.score >= 75 ? RED : row.score >= 60 ? ORANGE : ACCENT
                    return (
                      <tr key={row.symbol}
                        onClick={() => setSelectedSymbol(row.symbol)}
                        style={{
                          background: isSelected ? 'rgba(200,255,0,0.04)' : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                          borderLeft: isSelected ? `2px solid ${ACCENT}` : '2px solid transparent',
                          cursor: 'pointer',
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)' }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = isSelected ? 'rgba(200,255,0,0.04)' : 'transparent' }}
                      >
                        <td style={{ padding: '9px 12px', fontWeight: 700, color: TEXT }}>{row.symbol}</td>
                        <td style={{ padding: '9px 12px', fontFamily: 'JetBrains Mono, monospace', color: TEXT }}>
                          ${row.price.toFixed(4)}
                        </td>
                        <td style={{ padding: '9px 12px', fontFamily: 'JetBrains Mono, monospace', color: row.distance <= 0.03 ? RED : ORANGE }}>
                          ${row.distance.toFixed(4)}
                        </td>
                        <td style={{ padding: '9px 12px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: scoreColor }}>
                          {row.score.toFixed(1)}
                        </td>
                        <td style={{ padding: '9px 12px', color: row.distance <= 0.03 ? RED : SEC }}>
                          {trendArrow(row.distance)}
                        </td>
                        <td style={{ padding: '6px 12px' }}>
                          <SparklineCell symbol={row.symbol} />
                        </td>
                        <td style={{ padding: '9px 12px', fontSize: '0.65rem', color: DIM, fontFamily: 'JetBrains Mono, monospace' }}>
                          {formatTime(row.ts)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Price chart */}
          {selectedSymbol && (
            <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <Activity size={13} style={{ color: ACCENT }} />
                <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>
                  {selectedSymbol} — last 30 min
                </span>
                <span style={{ marginLeft: 'auto', fontSize: '0.62rem', color: DIM }}>
                  red dashed = $1.00  ·  red dot = BREAK alert
                </span>
                <button onClick={() => setSelectedSymbol(null)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: DIM, fontSize: '0.72rem' }}>
                  ✕
                </button>
              </div>
              <PriceChart symbol={selectedSymbol} breakTimes={breakTimesForSymbol} />
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

// Lazy sparkline — fetches its own 30-min history
function SparklineCell({ symbol }: { symbol: string }) {
  const { data } = useQuery({
    queryKey: ['screener-sparkline', symbol],
    queryFn: () => screenerService.getHistory(symbol, 30).then(r => r.data),
    refetchInterval: 30000,
    staleTime: 20000,
  })
  return <Sparkline points={data?.points ?? []} />
}
