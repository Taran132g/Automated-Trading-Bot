import { useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { LiveIndicator } from '@/components/ui/LiveIndicator'
import { PnLCurve } from '@/components/charts/PnLCurve'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useTerminalStore } from '@/store/terminalStore'
import { terminalService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED = '#ef4444'
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

export function TerminalPage() {
  const { setState, appendTrades, positions, account_details, daily_pnl, win_rate, rolling_pi_per_share, max_drawdown, cooldowns, trades } = useTerminalStore()
  const [equityRange, setEquityRange] = useState<'today' | 'alltime'>('today')
  const now = Date.now() / 1000

  const onWsMessage = useCallback((data: unknown) => {
    const msg = data as { type: string; data: Record<string, unknown>; _cursor?: unknown }
    if (msg.type === 'state_update') {
      setState(msg.data as Parameters<typeof setState>[0])
      if (Array.isArray((msg.data as { new_trades?: unknown[] }).new_trades)) {
        appendTrades((msg.data as { new_trades: Parameters<typeof appendTrades>[0] }).new_trades)
      }
    }
  }, [setState, appendTrades])

  useWebSocket({ url: '/api/terminal/ws', onMessage: onWsMessage })

  const { data: equityData } = useQuery({
    queryKey: ['equity-curve', equityRange],
    queryFn: () => terminalService.getEquityCurve(equityRange).then((r) => r.data.points),
    refetchInterval: 15000, staleTime: 10000,
  })

  const { data: tradesData } = useQuery({
    queryKey: ['terminal-trades'],
    queryFn: () => terminalService.getTrades('today').then((r) => r.data.trades),
    staleTime: 5000, refetchInterval: 10000,
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
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          SCALPER
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <LiveIndicator isLive={isMarketOpen()} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>
            {new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false })} ET
          </span>
        </div>
      </div>

      {/* Cooldown banners */}
      {lossActive && (
        <div style={{ background: 'rgba(239,68,68,0.06)', border: `1px solid rgba(239,68,68,0.2)`, borderRadius: 10, padding: '12px 18px', fontSize: '0.82rem', color: RED }}>
          <strong>LOSS COOLDOWN ACTIVE{cooldowns.loss_cooldown_syms.length ? ` [${cooldowns.loss_cooldown_syms.join(', ')}]` : ''}</strong> — Trading paused for {Math.round(lossCooldown - now)}s
        </div>
      )}
      {piActive && !lossActive && (
        <div style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 10, padding: '12px 18px', fontSize: '0.82rem', color: '#f59e0b' }}>
          <strong>PI COOLDOWN ACTIVE</strong> — Skipping entries for {Math.round(piCooldown - now)}s
        </div>
      )}

      {/* KPI row */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Daily PnL (Schwab)" value={fmt$(daily_pnl)} color={pnlColor} sub="REALIZED + UNREALIZED" />
        <MetricCard label="PnL Per Share" value={`${pnlPerShare >= 0 ? '+' : ''}$${Math.abs(pnlPerShare).toFixed(3)}`} color={pnlPerShare >= 0 ? GREEN : RED} sub="EXIT TRADES" />
        <MetricCard label="Account Value" value={`$${liveVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
        <MetricCard label="Max Drawdown" value={`-${max_drawdown.toFixed(2)}%`} color={max_drawdown > 2 ? RED : TEXT} sub="PEAK TO TROUGH" />
        <MetricCard label="Win Rate" value={`${win_rate.toFixed(1)}%`} color={win_rate > 50 ? GREEN : TEXT} sub="TODAY" />
        <MetricCard label="PI Per Share" value={`$${rolling_pi_per_share.toFixed(3)}`} color={rolling_pi_per_share >= 0 ? GREEN : TEXT} sub="ROLLING" />
      </div>

      {/* Equity chart + tape */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 7, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <SectionHeader>Trade PnL</SectionHeader>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['today', 'alltime'] as const).map((r) => (
                <button key={r} onClick={() => setEquityRange(r)} style={{
                  padding: '4px 12px', borderRadius: 20, border: `1px solid ${BORDER}`,
                  background: equityRange === r ? '#191925' : 'transparent',
                  color: equityRange === r ? TEXT : DIM,
                  fontSize: '0.7rem', cursor: 'pointer', fontFamily: 'Inter',
                  transition: 'all 0.15s',
                }}>
                  {r === 'today' ? 'Today' : 'All Time'}
                </button>
              ))}
            </div>
          </div>
          <PnLCurve data={equityData ?? []} color={GREEN} height={220} />
        </div>

        <div style={{ flex: 3, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px', overflowY: 'auto', minWidth: 0 }}>
          <SectionHeader>Live Execution Tape</SectionHeader>
          {trades.length === 0 ? (
            <div style={{ color: DIM, fontSize: '0.78rem', textAlign: 'center', marginTop: 20 }}>No trades today</div>
          ) : (
            trades.map((t, i) => {
              const side = t.side?.toUpperCase() ?? ''
              const isExit = ['SELL', 'COVER'].includes(side)
              const isShortEntry = ['SHORT', 'SELL SHORT'].includes(side)
              const accentColor = isExit
                ? (t.pnl >= 0 ? GREEN : RED)
                : isShortEntry ? RED : '#3b82f6'
              return (
                <div key={t.id ?? i} className="animate-fade-in-down" style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '7px 0', borderBottom: `1px solid ${BORDER}`,
                  fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem',
                }}>
                  <span style={{ color: DIM, width: 64 }}>{t.datetime_est}</span>
                  <span style={{ color: TEXT, fontWeight: 700, width: 48 }}>{t.symbol}</span>
                  <span style={{ color: accentColor, width: 52 }}>{t.side}</span>
                  <span style={{ color: TEXT, textAlign: 'right' }}>${t.price?.toFixed(2)}</span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Open positions */}
      {openPositions.length > 0 && (
        <div>
          <SectionHeader>Open Positions</SectionHeader>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {openPositions.map(([sym, qty]) => (
              <div key={sym} style={{
                background: CARD,
                border: `1px solid ${qty > 0 ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'}`,
                borderLeft: `3px solid ${qty > 0 ? GREEN : RED}`,
                borderRadius: 8, padding: '12px 18px',
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem',
              }}>
                <span style={{ color: TEXT, fontWeight: 700 }}>{sym}</span>
                <span style={{ color: SEC, margin: '0 10px' }}>{Math.abs(qty).toLocaleString()} shares</span>
                <span style={{ color: qty > 0 ? GREEN : RED, fontWeight: 600 }}>
                  {qty > 0 ? 'LONG' : 'SHORT'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
