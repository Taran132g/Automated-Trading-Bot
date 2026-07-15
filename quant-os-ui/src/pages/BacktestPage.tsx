import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { PnLCurve } from '@/components/charts/PnLCurve'
import { Badge } from '@/components/ui/Badge'
import { paperService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const BLUE = '#3b82f6'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const GREEN = '#22c55e'

type Range = 'today' | '2days' | 'all'

const RANGE_LABELS: Record<Range, string> = {
  today: 'Today',
  '2days': '48h',
  all: 'All Time',
}

function formatTradeTime(timestamp: number): string {
  const d = new Date(timestamp * 1000)
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/New_York',
  })
}

function formatTradeDate(timestamp: number): string {
  const d = new Date(timestamp * 1000)
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'America/New_York',
  })
}

function tradeDateKey(timestamp: number): string {
  const d = new Date(timestamp * 1000)
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'America/New_York',
  })
}

type SideBadgeProps = { side: string }
function SideBadge({ side }: SideBadgeProps) {
  const isEntry = side === 'BUY' || side === 'SHORT'
  const isLong = side === 'BUY' || side === 'SELL'
  const color = isLong ? BLUE : '#a855f7'
  const label = side === 'BUY' ? 'BUY' : side === 'SHORT' ? 'SHORT' : side === 'SELL' ? 'SELL' : 'COVER'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: 4,
      fontSize: '0.65rem',
      fontWeight: 700,
      fontFamily: 'JetBrains Mono, monospace',
      letterSpacing: '0.05em',
      background: `${color}22`,
      color,
      border: `1px solid ${color}44`,
      opacity: isEntry ? 0.7 : 1,
    }}>
      {label}
    </span>
  )
}

export function BacktestPage() {
  const [range, setRange] = useState<Range>('2days')

  const { data: state } = useQuery({
    queryKey: ['paper-state'],
    queryFn: () => paperService.getState().then((r) => r.data),
    refetchInterval: 5000,
  })

  const { data: equityCurve } = useQuery({
    queryKey: ['paper-equity', range],
    queryFn: () => paperService.getEquityCurve(range).then((r) => r.data.points),
    refetchInterval: 10000,
  })

  const { data: performance } = useQuery({
    queryKey: ['paper-performance'],
    queryFn: () => paperService.getPerformance().then((r) => r.data.rows),
    refetchInterval: 10000,
  })

  const { data: tradesData } = useQuery({
    queryKey: ['paper-trades', range],
    queryFn: () => paperService.getTrades(range).then((r) => r.data.trades),
    refetchInterval: 10000,
  })

  const openPositions = Object.entries(state?.positions ?? {}).filter(([, qty]) => qty !== 0)

  // Group trades by calendar date (ET)
  const tradesByDate: Array<{ dateKey: string; dateLabel: string; trades: unknown[] }> = []
  if (tradesData && tradesData.length > 0) {
    const groups = new Map<string, { label: string; trades: unknown[] }>()
    for (const t of tradesData as Array<{ timestamp: number }>) {
      const key = tradeDateKey(t.timestamp)
      if (!groups.has(key)) {
        groups.set(key, { label: formatTradeDate(t.timestamp), trades: [] })
      }
      groups.get(key)!.trades.push(t)
    }
    for (const [dateKey, { label, trades }] of groups) {
      tradesByDate.push({ dateKey, dateLabel: label, trades })
    }
  }

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header + range toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
            PAPER TRADING
          </h2>
          <Badge type="simulation" label="SIMULATION" />
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['today', '2days', 'all'] as Range[]).map((r) => (
            <button key={r} onClick={() => setRange(r)} style={{
              padding: '5px 14px', borderRadius: 20, border: `1px solid ${BORDER}`,
              background: range === r ? '#191925' : 'transparent',
              color: range === r ? TEXT : DIM,
              fontSize: '0.7rem', cursor: 'pointer', fontFamily: 'Inter',
              transition: 'all 0.15s',
              fontWeight: range === r ? 600 : 400,
            }}>
              {RANGE_LABELS[r]}
            </button>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Daily PnL" value={`${state?.daily_pnl >= 0 ? '+' : ''}$${Math.abs(state?.daily_pnl ?? 0).toFixed(2)}`} color={(state?.daily_pnl ?? 0) >= 0 ? BLUE : RED} />
        <MetricCard label="Total PnL" value={`${(state?.total_pnl ?? 0) >= 0 ? '+' : ''}$${Math.abs(state?.total_pnl ?? 0).toFixed(2)}`} color={(state?.total_pnl ?? 0) >= 0 ? BLUE : RED} />
        <MetricCard label="Win Rate" value={`${state?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(state?.win_rate ?? 0) > 50 ? BLUE : TEXT} sub="TODAY" />
        <MetricCard label="Trades Today" value={state?.trades_today?.toLocaleString() ?? '0'} />
      </div>

      {/* Equity curve + open positions */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 7, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Cumulative PnL — {RANGE_LABELS[range]}</SectionHeader>
          <PnLCurve data={equityCurve ?? []} color={BLUE} height={220} />
        </div>

        <div style={{ flex: 3, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px', overflowY: 'auto' }}>
          <SectionHeader>Paper Positions</SectionHeader>
          {openPositions.length === 0 ? (
            <div style={{ color: DIM, fontSize: '0.78rem' }}>No open positions</div>
          ) : (
            openPositions.map(([sym, qty]) => (
              <div key={sym} style={{
                borderLeft: `3px solid ${(qty as number) > 0 ? BLUE : RED}`,
                padding: '10px 14px', marginBottom: 8, background: '#0c0c14', borderRadius: '0 8px 8px 0',
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem',
              }}>
                <span style={{ color: TEXT, fontWeight: 700 }}>{sym}</span>
                <span style={{ color: SEC, margin: '0 10px' }}>{Math.abs(qty as number)} shares</span>
                <span style={{ color: (qty as number) > 0 ? BLUE : RED }}>{(qty as number) > 0 ? 'LONG' : 'SHORT'}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Symbol performance */}
      {performance && performance.length > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Symbol Performance</SectionHeader>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Today PnL/Share</th>
                <th>Today Win%</th>
                <th>All Time PnL/Share</th>
                <th>All Time Win%</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {performance.map((row: { symbol: string; total_pnl: number; win_rate: number; trades: number; today_pi: number; alltime_pi: number; today_win_rate: number }) => (
                <tr key={row.symbol}>
                  <td style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: BLUE }}>{row.symbol}</td>
                  <td style={{ color: (row.today_pi ?? 0) >= 0 ? BLUE : RED, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                    {(row.today_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.today_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#0c0c14', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.today_win_rate ?? 0}%`, background: BLUE, height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: SEC, minWidth: 40 }}>{(row.today_win_rate ?? 0).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: (row.alltime_pi ?? 0) >= 0 ? BLUE : RED, fontFamily: 'JetBrains Mono, monospace' }}>
                    {(row.alltime_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.alltime_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#0c0c14', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.win_rate}%`, background: DIM, height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: DIM, minWidth: 40 }}>{row.win_rate.toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: SEC }}>{row.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Trade log */}
      {tradesByDate.length > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Trade Log — {RANGE_LABELS[range]}</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginTop: 14 }}>
            {tradesByDate.map(({ dateKey, dateLabel, trades }) => (
              <div key={dateKey}>
                {/* Date separator */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
                }}>
                  <span style={{
                    fontSize: '0.68rem', fontWeight: 700, color: SEC,
                    textTransform: 'uppercase', letterSpacing: '0.1em',
                  }}>{dateLabel}</span>
                  <div style={{ flex: 1, height: 1, background: BORDER }} />
                  <span style={{ fontSize: '0.65rem', color: DIM }}>{trades.length} legs</span>
                </div>

                {/* Trade rows */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {(trades as Array<{
                    id: number
                    timestamp: number
                    symbol: string
                    side: string
                    qty: number
                    price: number
                    pnl: number
                    imbalance_ratio: number
                  }>).map((t) => {
                    const isExit = t.side === 'SELL' || t.side === 'COVER'
                    const pnlColor = t.pnl > 0 ? GREEN : t.pnl < 0 ? RED : DIM
                    return (
                      <div key={t.id} style={{
                        display: 'grid',
                        gridTemplateColumns: '52px 60px 72px 1fr 80px 80px 72px',
                        alignItems: 'center',
                        gap: 12,
                        padding: '7px 12px',
                        borderRadius: 6,
                        background: '#0c0c14',
                        borderLeft: `2px solid ${isExit ? (t.pnl >= 0 ? GREEN : RED) : '#334155'}`,
                        opacity: isExit ? 1 : 0.65,
                      }}>
                        <span style={{ color: DIM, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem' }}>
                          {formatTradeTime(t.timestamp)}
                        </span>
                        <span style={{ color: TEXT, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: '0.8rem' }}>
                          {t.symbol}
                        </span>
                        <SideBadge side={t.side} />
                        <span style={{ color: SEC, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem' }}>
                          {t.qty} @ ${t.price.toFixed(3)}
                        </span>
                        <span style={{ color: DIM, fontSize: '0.65rem', textAlign: 'right' }}>
                          {t.imbalance_ratio != null ? `${t.imbalance_ratio.toFixed(1)}x` : '—'}
                        </span>
                        {isExit ? (
                          <span style={{
                            color: pnlColor,
                            fontFamily: 'JetBrains Mono, monospace',
                            fontWeight: 700,
                            fontSize: '0.8rem',
                            textAlign: 'right',
                          }}>
                            {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}
                          </span>
                        ) : (
                          <span style={{ color: DIM, fontSize: '0.72rem', textAlign: 'right' }}>entry</span>
                        )}
                        <span style={{ color: isExit && t.pnl > 0 ? GREEN : isExit && t.pnl < 0 ? RED : DIM, fontSize: '0.65rem', textAlign: 'right' }}>
                          {isExit ? (t.pnl > 0 ? '▲ WIN' : t.pnl < 0 ? '▼ LOSS' : '— FLAT') : ''}
                        </span>
                      </div>
                    )
                  })}
                </div>

                {/* Day summary for exits */}
                {(() => {
                  const exits = (trades as Array<{ side: string; pnl: number }>).filter(t => t.side === 'SELL' || t.side === 'COVER')
                  if (exits.length === 0) return null
                  const dayPnl = exits.reduce((s, t) => s + t.pnl, 0)
                  const wins = exits.filter(t => t.pnl > 0).length
                  return (
                    <div style={{
                      display: 'flex', gap: 20, marginTop: 8, paddingTop: 8,
                      borderTop: `1px solid ${BORDER}`,
                    }}>
                      <span style={{ fontSize: '0.68rem', color: DIM }}>
                        {exits.length} exits ·{' '}
                        <span style={{ color: wins / exits.length >= 0.5 ? GREEN : RED }}>
                          {Math.round(wins / exits.length * 100)}% win
                        </span>
                      </span>
                      <span style={{
                        fontSize: '0.68rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                        color: dayPnl >= 0 ? GREEN : RED,
                      }}>
                        {dayPnl >= 0 ? '+' : ''}${dayPnl.toFixed(2)} day PnL
                      </span>
                    </div>
                  )
                })()}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
