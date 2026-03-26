import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity, Search, BarChart2, FlaskConical,
  GitCompare, Terminal, Bot, ShieldAlert, Cpu,
  TrendingUp, TrendingDown, Minus,
} from 'lucide-react'
import { adminService, terminalService, patternService } from '@/services/api'

const CARDS = [
  {
    to: '/scalper',
    icon: Activity,
    label: 'Scalper',
    description: 'Live L2 imbalance scalping strategy. Real-time order book signals and execution.',
    color: '#00FF99',
    badge: 'LIVE',
  },
  {
    to: '/pattern',
    icon: BarChart2,
    label: 'Pattern',
    description: 'Live chart-pattern breakout strategy. Confirmed breakouts on 1-minute bars.',
    color: '#A855F7',
    badge: 'LIVE',
  },
  {
    to: '/patterns',
    icon: FlaskConical,
    label: 'Pattern Lab',
    description: 'Paper simulation of the pattern strategy. Track performance without real capital.',
    color: '#3B82F6',
    badge: 'PAPER',
  },
  {
    to: '/backtest',
    icon: Search,
    label: 'Backtest',
    description: 'Run historical strategy simulations and review past performance.',
    color: '#F59E0B',
    badge: null,
  },
  {
    to: '/comparison',
    icon: GitCompare,
    label: 'Comparison',
    description: 'Side-by-side live vs paper performance metrics.',
    color: '#64748B',
    badge: null,
  },
  {
    to: '/grok',
    icon: Terminal,
    label: 'Grok Monitor',
    description: 'Real-time stream logs, L2 events, and alert feed.',
    color: '#94A3B8',
    badge: null,
  },
  {
    to: '/agents',
    icon: Bot,
    label: 'AI Agents',
    description: 'Post-market analysis reports and automated insight agents.',
    color: '#EC4899',
    badge: null,
  },
  {
    to: '/admin',
    icon: ShieldAlert,
    label: 'Admin',
    description: 'System controls, symbol config, position sizing, and Kelly parameters.',
    color: '#EF4444',
    badge: 'AUTH',
  },
]

function PnLPill({ value }: { value: number | undefined }) {
  if (value === undefined) return <span style={{ color: '#64748B', fontSize: '0.72rem' }}>—</span>
  const pos = value >= 0
  const Icon = value > 0.005 ? TrendingUp : value < -0.005 ? TrendingDown : Minus
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      color: pos ? '#00FF99' : '#EF4444',
      fontSize: '0.75rem', fontFamily: 'Roboto Mono', fontWeight: 600,
    }}>
      <Icon size={11} />
      {pos ? '+' : ''}${Math.abs(value).toFixed(2)}
    </span>
  )
}

export function HomePage() {
  const navigate = useNavigate()

  const { data: status } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const { data: scalperState } = useQuery({
    queryKey: ['terminal-state'],
    queryFn: () => terminalService.getState().then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const { data: patternState } = useQuery({
    queryKey: ['pattern-state-live'],
    queryFn: () => patternService.getState('live').then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const { data: paperState } = useQuery({
    queryKey: ['pattern-state-paper'],
    queryFn: () => patternService.getState('paper').then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const backendOnline = status?.loop_running || status?.trader_running || status?.grok_running

  const pnlByRoute: Record<string, number | undefined> = {
    '/scalper': scalperState?.daily_pnl,
    '/pattern': patternState?.daily_pnl,
    '/patterns': paperState?.daily_pnl,
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0B0E14',
      padding: '40px 32px',
      boxSizing: 'border-box',
    }}>
      {/* Header */}
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 48 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <Cpu size={28} color="#00FF99" />
              <span style={{
                fontFamily: 'Roboto Mono', fontSize: '1.8rem', fontWeight: 700,
                color: '#00FF99', letterSpacing: 2,
              }}>
                QUANT_OS
              </span>
            </div>
            <p style={{
              margin: 0, color: '#94A3B8', fontSize: '0.9rem', maxWidth: 520, lineHeight: 1.6,
            }}>
              Algorithmic trading system running two independent intraday strategies.
              The <span style={{ color: '#00FF99' }}>Scalper</span> trades L2 order-book imbalances in real time.
              The <span style={{ color: '#A855F7' }}>Pattern</span> strategy enters confirmed chart-pattern breakouts on 1-minute bar closes.
              Both run live with full Kelly position sizing.
            </p>
          </div>

          {/* System status */}
          <div style={{
            background: '#111827', border: '1px solid #1F2937', borderRadius: 10,
            padding: '14px 20px', display: 'flex', flexDirection: 'column', gap: 8,
            flexShrink: 0, minWidth: 160,
          }}>
            <div style={{ fontSize: '0.62rem', color: '#64748B', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 2 }}>
              System
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: backendOnline ? '#00FF99' : '#EF4444',
                boxShadow: backendOnline ? '0 0 8px #00FF99' : '0 0 8px #EF4444',
                display: 'inline-block', flexShrink: 0,
              }} />
              <span style={{ fontSize: '0.78rem', color: '#E2E8F0', fontFamily: 'Roboto Mono' }}>
                {backendOnline ? 'Bot Online' : 'Bot Offline'}
              </span>
            </div>
            <div style={{ borderTop: '1px solid #1F2937', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.68rem', color: '#64748B' }}>Scalper</span>
                <PnLPill value={scalperState?.daily_pnl} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.68rem', color: '#64748B' }}>Pattern</span>
                <PnLPill value={patternState?.daily_pnl} />
              </div>
            </div>
          </div>
        </div>

        {/* Nav cards grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: 14,
        }}>
          {CARDS.map(({ to, icon: Icon, label, description, color, badge }) => (
            <button
              key={to}
              onClick={() => navigate(to)}
              style={{
                background: '#111827',
                border: '1px solid #1F2937',
                borderRadius: 10,
                padding: '18px 20px',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                position: 'relative',
                overflow: 'hidden',
                transition: 'border-color 0.15s, background 0.15s',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = color
                ;(e.currentTarget as HTMLButtonElement).style.background = '#141C2B'
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#1F2937'
                ;(e.currentTarget as HTMLButtonElement).style.background = '#111827'
              }}
            >
              {/* Top accent line */}
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                background: color, opacity: 0.6, borderRadius: '10px 10px 0 0',
              }} />

              {/* Icon row */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{
                  width: 34, height: 34, borderRadius: 8,
                  background: `${color}18`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={16} color={color} />
                </div>
                {badge && (
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.08em',
                    color: color, background: `${color}18`,
                    border: `1px solid ${color}40`,
                    borderRadius: 4, padding: '2px 6px',
                  }}>
                    {badge}
                  </span>
                )}
                {to in pnlByRoute && pnlByRoute[to] !== undefined && (
                  <PnLPill value={pnlByRoute[to]} />
                )}
              </div>

              {/* Label */}
              <div>
                <div style={{
                  fontSize: '0.88rem', fontWeight: 700, color: '#F8FAFC',
                  fontFamily: 'Roboto Mono', letterSpacing: '0.02em', marginBottom: 5,
                }}>
                  {label}
                </div>
                <div style={{ fontSize: '0.73rem', color: '#64748B', lineHeight: 1.5 }}>
                  {description}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
