import { useEffect, useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { LiveIndicator } from '@/components/ui/LiveIndicator'
import { PnLCurve } from '@/components/charts/PnLCurve'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useTerminalStore } from '@/store/terminalStore'
import { terminalService } from '@/services/api'

const CARD = '#0c0c14'
const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const BLUE = '#3b82f6'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

function isMarketOpen(): boolean {
  const now = new Date()
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const day = et.getDay()
  const h = et.getHours()
  const m = et.getMinutes()
  if (day === 0 || day === 6) return false
  const totalMin = h * 60 + m
  return totalMin >= 9 * 60 + 30 && totalMin < 16 * 60
}

function fmt$(v: number) {
  const prefix = v >= 0 ? '+' : ''
  return `${prefix}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function StatRow({ label, value, color = TEXT }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '8px 0',
      borderBottom: `1px solid ${BORDER}`,
    }}>
      <span style={{ fontSize: '0.72rem', color: DIM }}>{label}</span>
      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem', fontWeight: 600, color }}>
        {value}
      </span>
    </div>
  )
}

export function TerminalPage() {
  const {
    setState, appendTrades, setPositions,
    positions, account_details, daily_pnl, win_rate,
    rolling_pi_per_share, max_drawdown, cooldowns, trades,
  } = useTerminalStore()
  const [equityRange, setEquityRange] = useState<'today' | 'alltime'>('today')
  const queryClient = useQueryClient()
  const now = Date.now() / 1000

  const onWsMessage = useCallback((data: unknown) => {
    const msg = data as { type: string; data: Record<string, unknown>; _cursor?: unknown }
    if (msg.type === 'state_update') {
      setState(msg.data as Parameters<typeof setState>[0])
      const newTrades = (msg.data as { new_trades?: unknown[] }).new_trades
      if (Array.isArray(newTrades)) {
        appendTrades(newTrades as Parameters<typeof appendTrades>[0])
        // Any closing fill → immediately refetch positions from the server
        const hasClose = (newTrades as { side?: string }[]).some(
          t => ['SELL', 'COVER'].includes((t.side ?? '').toUpperCase())
        )
        if (hasClose) {
          queryClient.invalidateQueries({ queryKey: ['terminal-positions'] })
        }
      }
    }
  }, [setState, appendTrades, queryClient])

  useWebSocket({ url: '/api/terminal/ws', onMessage: onWsMessage })

  // Poll positions every 5s; also invalidated immediately on any SELL/COVER via WS
  const { data: positionsData } = useQuery({
    queryKey: ['terminal-positions'],
    queryFn: () => terminalService.getPositions().then((r) => r.data.positions as Record<string, number>),
    refetchInterval: 5000,
    staleTime: 2000,
  })

  useEffect(() => {
    if (positionsData) setPositions(positionsData)
  }, [positionsData, setPositions])

  const { data: equityData } = useQuery({
    queryKey: ['equity-curve', equityRange],
    queryFn: () => terminalService.getEquityCurve(equityRange).then((r) => r.data.points),
    refetchInterval: 15000,
    staleTime: 10000,
  })

  const { data: tradesData } = useQuery({
    queryKey: ['terminal-trades'],
    queryFn: () => terminalService.getTrades('today').then((r) => r.data.trades),
    staleTime: 5000,
    refetchInterval: 10000,
  })

  useEffect(() => {
    if (tradesData?.length) appendTrades(tradesData)
  }, [tradesData, appendTrades])

  const liveVal = account_details.liquidation_value ?? 0
  const pnlColor = daily_pnl >= 0 ? GREEN : RED

  const lossCooldown = cooldowns.loss_cooldown_until
  const piCooldown = cooldowns.pi_cooldown_until
  const lossActive = now < lossCooldown
  const piActive = now < piCooldown

  const openPositions = Object.entries(positions).filter(([, qty]) => qty !== 0)

  const exitTrades = trades.filter((t) => ['SELL', 'COVER'].includes(t.side?.toUpperCase() ?? ''))
  const exitPnl = exitTrades.reduce((s, t) => s + (t.pnl ?? 0), 0)
  const exitShares = exitTrades.reduce((s, t) => s + Math.abs(t.qty ?? 0), 0)
  const pnlPerShare = exitShares > 0 ? exitPnl / exitShares : 0

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '0.54rem', color: DIM, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 3 }}>
            Live Strategy
          </div>
          <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
            Scalper
          </h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <LiveIndicator isLive={isMarketOpen()} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM }}>
            {new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false })} ET
          </span>
        </div>
      </div>

      {/* Cooldown banners */}
      {lossActive && (
        <div style={{
          background: 'rgba(239,68,68,0.05)',
          border: `1px solid rgba(239,68,68,0.18)`,
          borderLeft: `3px solid ${RED}`,
          borderRadius: 8,
          padding: '10px 16px',
          fontSize: '0.78rem',
          color: RED,
        }}>
          <strong>LOSS COOLDOWN</strong>
          {cooldowns.loss_cooldown_syms.length ? ` [${cooldowns.loss_cooldown_syms.join(', ')}]` : ''} — Trading paused for {Math.round(lossCooldown - now)}s
        </div>
      )}
      {piActive && !lossActive && (
        <div style={{
          background: 'rgba(245,158,11,0.05)',
          border: '1px solid rgba(245,158,11,0.18)',
          borderLeft: '3px solid #f59e0b',
          borderRadius: 8,
          padding: '10px 16px',
          fontSize: '0.78rem',
          color: '#f59e0b',
        }}>
          <strong>PI COOLDOWN</strong> — Skipping entries for {Math.round(piCooldown - now)}s
        </div>
      )}

      {/* Main layout: chart + sidebar */}
      <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>

        {/* Left: chart + trade table */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>

          {/* Equity chart */}
          <div style={{
            background: CARD,
            border: `1px solid ${BORDER}`,
            borderRadius: 10,
            padding: '16px 18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <SectionHeader>Trade P&L Curve</SectionHeader>
              <div style={{ display: 'flex', gap: 4 }}>
                {(['today', 'alltime'] as const).map((r) => (
                  <button key={r} onClick={() => setEquityRange(r)} style={{
                    padding: '3px 10px',
                    borderRadius: 20,
                    border: `1px solid ${BORDER}`,
                    background: equityRange === r ? '#191925' : 'transparent',
                    color: equityRange === r ? TEXT : DIM,
                    fontSize: '0.66rem',
                    cursor: 'pointer',
                    fontFamily: 'Inter',
                    transition: 'all 0.15s',
                  }}>
                    {r === 'today' ? 'Today' : 'All Time'}
                  </button>
                ))}
              </div>
            </div>
            <PnLCurve data={equityData ?? []} color={GREEN} height={180} />
          </div>

          {/* Trade log */}
          <div style={{
            background: CARD,
            border: `1px solid ${BORDER}`,
            borderRadius: 10,
            overflow: 'hidden',
            flex: 1,
          }}>
            <div style={{ padding: '11px 18px', borderBottom: `1px solid ${BORDER}` }}>
              <SectionHeader>Execution Log</SectionHeader>
            </div>

            {/* Table header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '72px 52px 72px 80px 1fr 80px',
              padding: '6px 18px',
              borderBottom: `1px solid rgba(255,255,255,0.04)`,
            }}>
              {['Time', 'Symbol', 'Side', 'Price', 'Shares', 'P&L'].map(h => (
                <span key={h} style={{
                  fontSize: '0.52rem',
                  color: DIM,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                }}>
                  {h}
                </span>
              ))}
            </div>

            <div style={{ overflowY: 'auto', maxHeight: 260 }}>
              {trades.length === 0 ? (
                <div style={{ color: DIM, fontSize: '0.75rem', textAlign: 'center', padding: '28px 18px' }}>
                  No trades today
                </div>
              ) : (
                trades.map((t, i) => {
                  const side = t.side?.toUpperCase() ?? ''
                  const isExit = ['SELL', 'COVER'].includes(side)
                  const isShortEntry = ['SHORT', 'SELL SHORT'].includes(side)
                  const sideColor = isExit
                    ? (t.pnl >= 0 ? GREEN : RED)
                    : isShortEntry ? RED : BLUE
                  return (
                    <div
                      key={t.id ?? i}
                      className="animate-fade-in-down"
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '72px 52px 72px 80px 1fr 80px',
                        padding: '7px 18px',
                        borderBottom: `1px solid ${BORDER}`,
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: '0.72rem',
                        alignItems: 'center',
                      }}
                    >
                      <span style={{ color: DIM }}>{t.datetime_est}</span>
                      <span style={{ color: TEXT, fontWeight: 600 }}>{t.symbol}</span>
                      <span style={{ color: sideColor }}>{t.side}</span>
                      <span style={{ color: SEC }}>${t.price?.toFixed(2)}</span>
                      <span style={{ color: SEC }}>{Math.abs(t.qty ?? 0).toLocaleString()}</span>
                      <span style={{ color: isExit && t.pnl != null ? (t.pnl >= 0 ? GREEN : RED) : DIM, textAlign: 'right' }}>
                        {isExit && t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                      </span>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Right sidebar: metrics + positions */}
        <div style={{ width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Key metrics */}
          <div style={{
            background: CARD,
            border: `1px solid ${BORDER}`,
            borderRadius: 10,
            padding: '14px 16px',
          }}>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: '0.54rem', color: DIM, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 4 }}>
                Day P&L
              </div>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '1.6rem',
                fontWeight: 800,
                color: pnlColor,
                letterSpacing: '-0.5px',
              }}>
                {fmt$(daily_pnl)}
              </div>
            </div>
            <div style={{ borderTop: `1px solid ${BORDER}`, paddingTop: 10 }}>
              <StatRow label="Account Value" value={`$${liveVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
              <StatRow label="Win Rate" value={`${win_rate.toFixed(1)}%`} color={win_rate > 50 ? GREEN : TEXT} />
              <StatRow label="P&L / Share" value={`${pnlPerShare >= 0 ? '+' : ''}$${Math.abs(pnlPerShare).toFixed(3)}`} color={pnlPerShare >= 0 ? GREEN : RED} />
              <StatRow label="PI / Share" value={`$${rolling_pi_per_share.toFixed(3)}`} color={rolling_pi_per_share >= 0 ? GREEN : TEXT} />
              <StatRow label="Max Drawdown" value={`-${max_drawdown.toFixed(2)}%`} color={max_drawdown > 2 ? RED : TEXT} />
            </div>
          </div>

          {/* Open positions */}
          <div style={{
            background: CARD,
            border: `1px solid ${BORDER}`,
            borderRadius: 10,
            padding: '14px 16px',
            flex: 1,
          }}>
            <div style={{ marginBottom: 10 }}>
              <SectionHeader>Open Positions</SectionHeader>
            </div>
            {openPositions.length === 0 ? (
              <div style={{ color: DIM, fontSize: '0.72rem', textAlign: 'center', paddingTop: 20 }}>
                No open positions
              </div>
            ) : (
              openPositions.map(([sym, qty]) => (
                <div key={sym} style={{
                  padding: '10px 0',
                  borderBottom: `1px solid ${BORDER}`,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.88rem',
                      fontWeight: 700,
                      color: TEXT,
                    }}>
                      {sym}
                    </span>
                    <span style={{
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      color: qty > 0 ? GREEN : RED,
                      background: qty > 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                      border: `1px solid ${qty > 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
                      borderRadius: 4,
                      padding: '2px 7px',
                      fontFamily: 'JetBrains Mono',
                    }}>
                      {qty > 0 ? 'LONG' : 'SHORT'}
                    </span>
                  </div>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: SEC }}>
                    {Math.abs(qty).toLocaleString()} shares
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
