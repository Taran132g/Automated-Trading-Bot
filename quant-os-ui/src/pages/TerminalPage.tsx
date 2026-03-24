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

function isMarketOpen(): boolean {
  const now = new Date()
  // EST offset (no DST handling for simplicity)
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

  // WebSocket for live updates
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

  // Equity curve
  const { data: equityData } = useQuery({
    queryKey: ['equity-curve', equityRange],
    queryFn: () => terminalService.getEquityCurve(equityRange).then((r) => r.data.points),
    refetchInterval: 15000,
    staleTime: 10000,
  })

  // Initial trades load
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
  const pnlColor = daily_pnl >= 0 ? '#00FF99' : '#EF4444'

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
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
          EXECUTION TERMINAL
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <LiveIndicator isLive={isMarketOpen()} />
          <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: '#64748B' }}>
            {new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false })} ET
          </span>
        </div>
      </div>

      {/* Cooldown banners */}
      {lossActive && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #EF4444', borderRadius: 8, padding: '10px 16px', fontSize: '0.82rem', color: '#EF4444' }}>
          ⚠️ <strong>LOSS COOLDOWN ACTIVE{cooldowns.loss_cooldown_syms.length ? ` [${cooldowns.loss_cooldown_syms.join(', ')}]` : ''}</strong> — Trading paused for {Math.round(lossCooldown - now)}s
        </div>
      )}
      {piActive && !lossActive && (
        <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid #F59E0B', borderRadius: 8, padding: '10px 16px', fontSize: '0.82rem', color: '#F59E0B' }}>
          🕒 <strong>PI COOLDOWN ACTIVE</strong> — Skipping entries for {Math.round(piCooldown - now)}s
        </div>
      )}

      {/* KPI row */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Daily PnL (Schwab)" value={fmt$(daily_pnl)} color={pnlColor} sub="REALIZED + UNREALIZED" />
        <MetricCard label="PnL Per Share" value={`${pnlPerShare >= 0 ? '+' : ''}$${Math.abs(pnlPerShare).toFixed(3)}`} color={pnlPerShare >= 0 ? '#00FF99' : '#EF4444'} sub="EXIT TRADES" />
        <MetricCard label="Account Value" value={`$${liveVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
        <MetricCard label="Max Drawdown" value={`-${max_drawdown.toFixed(2)}%`} color={max_drawdown > 2 ? '#EF4444' : '#F8FAFC'} sub="PEAK TO TROUGH" />
        <MetricCard label="Win Rate" value={`${win_rate.toFixed(1)}%`} color={win_rate > 50 ? '#00FF99' : '#F8FAFC'} sub="TODAY" />
        <MetricCard label="PI Per Share" value={`$${rolling_pi_per_share.toFixed(3)}`} color={rolling_pi_per_share >= 0 ? '#00FF99' : '#F8FAFC'} sub="ROLLING" />
      </div>

      {/* Equity chart + tape */}
      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        {/* Left: equity curve */}
        <div style={{ flex: 7, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <SectionHeader>Account Value Trajectory</SectionHeader>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['today', 'alltime'] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setEquityRange(r)}
                  style={{
                    padding: '3px 10px',
                    borderRadius: 20,
                    border: '1px solid #1F2937',
                    background: equityRange === r ? '#1F2937' : 'transparent',
                    color: equityRange === r ? '#F8FAFC' : '#64748B',
                    fontSize: '0.7rem',
                    cursor: 'pointer',
                    fontFamily: 'Inter',
                  }}
                >
                  {r === 'today' ? 'Today' : 'All Time'}
                </button>
              ))}
            </div>
          </div>
          <PnLCurve data={equityData ?? []} color="#00FF99" height={220} />
        </div>

        {/* Right: tape */}
        <div style={{ flex: 3, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px', overflowY: 'auto', minWidth: 0 }}>
          <SectionHeader>Live Execution Tape</SectionHeader>
          {trades.length === 0 ? (
            <div style={{ color: '#64748B', fontSize: '0.78rem', textAlign: 'center', marginTop: 20 }}>No trades today</div>
          ) : (
            trades.map((t, i) => {
              const side = t.side?.toUpperCase() ?? ''
              const isExit = ['SELL', 'COVER'].includes(side)
              const isShortEntry = ['SHORT', 'SELL SHORT'].includes(side)
              const accentColor = isExit
                ? (t.pnl >= 0 ? '#00FF99' : '#EF4444')
                : isShortEntry ? '#EF4444' : '#60A5FA'
              return (
                <div
                  key={t.id ?? i}
                  className="animate-fade-in-down"
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '6px 0',
                    borderBottom: '1px solid #1F2937',
                    fontFamily: 'Roboto Mono',
                    fontSize: '0.75rem',
                  }}
                >
                  <span style={{ color: '#64748B', width: 64 }}>{t.datetime_est}</span>
                  <span style={{ color: '#E2E8F0', fontWeight: 700, width: 48 }}>{t.symbol}</span>
                  <span style={{ color: accentColor, width: 52 }}>{t.side}</span>
                  <span style={{ color: '#F8FAFC', textAlign: 'right' }}>${t.price?.toFixed(2)}</span>
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
              <div
                key={sym}
                style={{
                  background: '#111827',
                  border: `1px solid ${qty > 0 ? '#00FF9933' : '#EF444433'}`,
                  borderLeft: `3px solid ${qty > 0 ? '#00FF99' : '#EF4444'}`,
                  borderRadius: 6,
                  padding: '10px 16px',
                  fontFamily: 'Roboto Mono',
                  fontSize: '0.82rem',
                }}
              >
                <span style={{ color: '#E2E8F0', fontWeight: 700 }}>{sym}</span>
                <span style={{ color: '#94A3B8', margin: '0 8px' }}>{Math.abs(qty).toLocaleString()} shares</span>
                <span style={{ color: qty > 0 ? '#00FF99' : '#EF4444', fontWeight: 600 }}>
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
