import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Activity, BarChart2, Radio, Search, FlaskConical, GitCompare,
  Terminal, Bot, ShieldAlert, TrendingUp, TrendingDown,
  ArrowUpRight, LineChart,
} from 'lucide-react'
import {
  adminService, terminalService, patternService, paperService, marketService,
} from '@/services/api'
import type { QuoteItem } from '@/services/api'

const BG = '#06060b'
const CARD = '#0c0c14'
const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const BLUE = '#3b82f6'
const PURPLE = '#a78bfa'
const CYAN = '#22d3ee'
const AMBER = '#f59e0b'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '0.56rem',
      color: DIM,
      letterSpacing: '0.16em',
      textTransform: 'uppercase',
      fontWeight: 700,
      marginBottom: 10,
    }}>
      {children}
    </div>
  )
}

function KpiBox({ label, value, color = TEXT }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      background: CARD,
      border: `1px solid ${BORDER}`,
      borderRadius: 8,
      padding: '12px 18px',
    }}>
      <div style={{ fontSize: '0.54rem', color: DIM, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.05rem', fontWeight: 700, color }}>
        {value}
      </div>
    </div>
  )
}

function StrategyCard({
  label, accent, pnl, kv1, kv2, to, tag, running,
}: {
  label: string
  accent: string
  pnl?: number
  kv1?: [string, string]
  kv2?: [string, string]
  to: string
  tag: string
  running: boolean
}) {
  const navigate = useNavigate()
  const pnlColor = pnl == null ? DIM : pnl >= 0 ? GREEN : RED
  return (
    <button
      onClick={() => navigate(to)}
      style={{
        background: CARD,
        border: `1px solid ${BORDER}`,
        borderRadius: 10,
        padding: '16px 18px',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        flex: 1,
        minWidth: 0,
        position: 'relative',
        overflow: 'hidden',
        transition: 'border-color 0.15s, background 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = `${accent}35`
        e.currentTarget.style.background = '#101018'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = BORDER
        e.currentTarget.style.background = CARD
      }}
    >
      <div style={{
        position: 'absolute',
        top: 0, left: 0, right: 0,
        height: 1,
        background: `linear-gradient(90deg, ${accent}70, transparent 60%)`,
      }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '0.58rem', fontWeight: 700, letterSpacing: '0.14em', color: accent }}>
          {label}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: running ? GREEN : DIM,
            boxShadow: running ? `0 0 5px ${GREEN}` : 'none',
            display: 'inline-block',
          }} />
          <span style={{
            fontSize: '0.5rem',
            fontWeight: 700,
            letterSpacing: '0.08em',
            fontFamily: 'JetBrains Mono',
            padding: '2px 6px',
            borderRadius: 3,
            background: `${accent}0c`,
            border: `1px solid ${accent}22`,
            color: accent,
          }}>
            {tag}
          </span>
        </div>
      </div>

      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '1.5rem',
        fontWeight: 700,
        color: pnlColor,
        letterSpacing: '-0.5px',
      }}>
        {pnl == null ? '—' : `${pnl >= 0 ? '+' : ''}$${Math.abs(pnl).toFixed(2)}`}
      </div>

      <div style={{ display: 'flex', gap: 20, paddingTop: 8, borderTop: `1px solid ${BORDER}` }}>
        {kv1 && (
          <div>
            <div style={{ fontSize: '0.54rem', color: DIM, marginBottom: 2 }}>{kv1[0]}</div>
            <div style={{ fontSize: '0.72rem', fontFamily: 'JetBrains Mono', color: SEC }}>{kv1[1]}</div>
          </div>
        )}
        {kv2 && (
          <div>
            <div style={{ fontSize: '0.54rem', color: DIM, marginBottom: 2 }}>{kv2[0]}</div>
            <div style={{ fontSize: '0.72rem', fontFamily: 'JetBrains Mono', color: SEC }}>{kv2[1]}</div>
          </div>
        )}
      </div>
    </button>
  )
}

export function HomePage() {
  const navigate = useNavigate()

  const { data: status } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then(r => r.data),
    refetchInterval: 10000,
    retry: false,
  })
  const { data: scalperState } = useQuery({
    queryKey: ['terminal-state'],
    queryFn: () => terminalService.getState().then(r => r.data),
    refetchInterval: 10000,
    retry: false,
  })
  const { data: recentTrades } = useQuery({
    queryKey: ['terminal-trades-home'],
    queryFn: () => terminalService.getTrades('today').then(r => r.data.trades),
    refetchInterval: 15000,
    retry: false,
  })
  const { data: patternState } = useQuery({
    queryKey: ['pattern-state-live'],
    queryFn: () => patternService.getState('live').then(r => r.data),
    refetchInterval: 10000,
    retry: false,
  })
  const { data: paperState } = useQuery({
    queryKey: ['pattern-state-paper'],
    queryFn: () => patternService.getState('paper').then(r => r.data),
    refetchInterval: 10000,
    retry: false,
  })
  const { data: marketData } = useQuery({
    queryKey: ['market-quotes'],
    queryFn: () => marketService.getQuotes().then(r => r.data),
    refetchInterval: 60000,
    staleTime: 55000,
    retry: false,
  })

  const backendOnline = status?.loop_running || status?.trader_running || status?.grok_running
  const acctVal = scalperState?.account_details?.liquidation_value
  const scalperPnl = scalperState?.daily_pnl
  const patternPnl = patternState?.daily_pnl
  const totalPnl = (scalperPnl ?? 0) + (patternPnl ?? 0)
  const movers: QuoteItem[] = [
    ...(marketData?.top ?? []),
    ...(marketData?.bottom ?? []),
  ].slice(0, 8)
  const trades = (recentTrades ?? []).slice(0, 10)
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  })

  return (
    <div style={{
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
      background: BG,
      minHeight: '100%',
    }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: '0.56rem', color: DIM, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 3 }}>
            Command Center
          </div>
          <h1 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.03em' }}>
            Dashboard
          </h1>
        </div>
        <span style={{ fontSize: '0.68rem', color: DIM }}>{today}</span>
      </div>

      {/* KPI strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        <KpiBox
          label="Account Value"
          value={acctVal
            ? `$${acctVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '—'}
        />
        <KpiBox
          label="Total Day P&L"
          value={`${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}`}
          color={totalPnl >= 0 ? GREEN : RED}
        />
        <KpiBox
          label="Scalper Win Rate"
          value={scalperState?.win_rate != null ? `${scalperState.win_rate.toFixed(1)}%` : '—'}
          color={(scalperState?.win_rate ?? 0) > 50 ? GREEN : TEXT}
        />
        <KpiBox
          label="System"
          value={backendOnline ? 'Online' : 'Offline'}
          color={backendOnline ? GREEN : RED}
        />
      </div>

      {/* Strategy cards */}
      <div>
        <SectionLabel>Strategies</SectionLabel>
        <div style={{ display: 'flex', gap: 12 }}>
          <StrategyCard
            label="SCALPER"
            accent={GREEN}
            pnl={scalperPnl}
            kv1={['Win Rate', scalperState?.win_rate != null ? `${scalperState.win_rate.toFixed(1)}%` : '—']}
            kv2={['P/Share', scalperState?.rolling_pi_per_share != null ? `$${scalperState.rolling_pi_per_share.toFixed(3)}` : '—']}
            to="/scalper"
            tag="LIVE"
            running={!!status?.trader_running}
          />
          <StrategyCard
            label="PATTERN"
            accent={PURPLE}
            pnl={patternPnl}
            kv1={['Win Rate', patternState?.win_rate != null ? `${patternState.win_rate.toFixed(1)}%` : '—']}
            kv2={['Trades', patternState?.daily_trades != null ? String(patternState.daily_trades) : '—']}
            to="/pattern"
            tag="LIVE"
            running={!!status?.loop_running}
          />
          <StrategyCard
            label="PATTERN LAB"
            accent={BLUE}
            pnl={paperState?.daily_pnl}
            kv1={['Win Rate', paperState?.win_rate != null ? `${paperState.win_rate.toFixed(1)}%` : '—']}
            kv2={['Trades', paperState?.daily_trades != null ? String(paperState.daily_trades) : '—']}
            to="/patterns"
            tag="SIM"
            running={!!status?.loop_running}
          />
        </div>
      </div>

      {/* Activity + Market */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 14 }}>

        {/* Recent trades */}
        <div style={{
          background: CARD,
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
          overflow: 'hidden',
        }}>
          <div style={{
            padding: '11px 18px',
            borderBottom: `1px solid ${BORDER}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 600, color: TEXT }}>Recent Trades</span>
            <button
              onClick={() => navigate('/scalper')}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                color: '#c8ff00',
                fontSize: '0.62rem',
                padding: 0,
              }}
            >
              Scalper <ArrowUpRight size={11} />
            </button>
          </div>

          {/* Table header */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '62px 50px 68px 1fr 70px',
            padding: '6px 18px',
            borderBottom: `1px solid rgba(255,255,255,0.04)`,
          }}>
            {['Time', 'Sym', 'Side', 'Price × Qty', 'P&L'].map(h => (
              <span key={h} style={{
                fontSize: '0.54rem',
                color: DIM,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}>
                {h}
              </span>
            ))}
          </div>

          {trades.length === 0 ? (
            <div style={{ padding: '28px 18px', textAlign: 'center', color: DIM, fontSize: '0.75rem' }}>
              No trades today
            </div>
          ) : (
            trades.map((t: Record<string, unknown>, i: number) => {
              const side = String(t.side ?? '').toUpperCase()
              const isExit = ['SELL', 'COVER'].includes(side)
              const isShort = ['SHORT', 'SELL SHORT'].includes(side)
              const sideColor = isExit ? ((t.pnl as number) >= 0 ? GREEN : RED) : isShort ? RED : BLUE
              const pnl = t.pnl as number | undefined
              const price = t.price as number | undefined
              const qty = t.qty as number | undefined
              const timeStr = String(t.datetime_est ?? '').split(' ')[1] ?? ''
              return (
                <div
                  key={(t.id as number) ?? i}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '62px 50px 68px 1fr 70px',
                    padding: '7px 18px',
                    borderBottom: `1px solid ${BORDER}`,
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.7rem',
                    alignItems: 'center',
                  }}
                >
                  <span style={{ color: DIM }}>{timeStr}</span>
                  <span style={{ color: TEXT, fontWeight: 600 }}>{String(t.symbol ?? '')}</span>
                  <span style={{ color: sideColor }}>{String(t.side ?? '')}</span>
                  <span style={{ color: SEC }}>
                    {price != null ? `$${price.toFixed(2)}` : '—'} × {Math.abs(qty ?? 0)}
                  </span>
                  <span style={{ color: isExit && pnl != null ? (pnl >= 0 ? GREEN : RED) : DIM, textAlign: 'right' }}>
                    {isExit && pnl != null ? `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}` : '—'}
                  </span>
                </div>
              )
            })
          )}
        </div>

        {/* Market movers */}
        <div style={{
          background: CARD,
          border: `1px solid ${BORDER}`,
          borderRadius: 10,
          overflow: 'hidden',
        }}>
          <div style={{ padding: '11px 18px', borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 600, color: TEXT }}>Market Movers</span>
          </div>
          {movers.length === 0 ? (
            <div style={{ padding: '28px 18px', textAlign: 'center', color: DIM, fontSize: '0.75rem' }}>
              Loading market data...
            </div>
          ) : (
            movers.map((q: QuoteItem) => {
              const pos = q.change_pct >= 0
              const Icon = pos ? TrendingUp : TrendingDown
              return (
                <div key={q.symbol} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '9px 18px',
                  borderBottom: `1px solid ${BORDER}`,
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.75rem',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Icon size={11} color={pos ? GREEN : RED} />
                    <span style={{ color: TEXT, fontWeight: 600, minWidth: 50 }}>{q.symbol}</span>
                    <span style={{ color: SEC }}>${q.price?.toFixed(2)}</span>
                  </div>
                  <span style={{
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    color: pos ? GREEN : RED,
                    background: pos ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)',
                    padding: '2px 8px',
                    borderRadius: 4,
                  }}>
                    {pos ? '+' : ''}{q.change_pct.toFixed(2)}%
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* All modules */}
      <div>
        <SectionLabel>All Modules</SectionLabel>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))', gap: 8 }}>
          {(
            [
              { to: '/scalper', label: 'Scalper', icon: Activity, accent: GREEN },
              { to: '/pattern', label: 'Pattern', icon: BarChart2, accent: PURPLE },
              { to: '/signals', label: 'Signals', icon: Radio, accent: CYAN },
              { to: '/comparison', label: 'Comparison', icon: GitCompare, accent: SEC },
              { to: '/analytics', label: 'Analytics', icon: LineChart, accent: AMBER },
              { to: '/grok', label: 'Grok', icon: Terminal, accent: AMBER },
              { to: '/backtest', label: 'Backtest', icon: Search, accent: BLUE },
              { to: '/patterns', label: 'Pattern Lab', icon: FlaskConical, accent: BLUE },
              { to: '/agents', label: 'AI Agents', icon: Bot, accent: '#f472b6' },
              { to: '/admin', label: 'Admin', icon: ShieldAlert, accent: RED },
            ] as const
          ).map(({ to, label, icon: Icon, accent }) => (
            <button
              key={to}
              onClick={() => navigate(to)}
              style={{
                background: 'rgba(12,12,20,0.5)',
                border: `1px solid ${BORDER}`,
                borderRadius: 8,
                padding: '10px 14px',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                transition: 'all 0.12s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = `${accent}30`
                e.currentTarget.style.background = 'rgba(16,16,24,0.9)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = BORDER
                e.currentTarget.style.background = 'rgba(12,12,20,0.5)'
              }}
            >
              <Icon size={13} color={accent} style={{ flexShrink: 0 }} />
              <span style={{ fontSize: '0.76rem', color: SEC }}>{label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
