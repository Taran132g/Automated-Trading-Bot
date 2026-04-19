import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity, Search, BarChart2, FlaskConical,
  GitCompare, Terminal, Bot, ShieldAlert, Cpu,
  TrendingUp, TrendingDown, Minus, Wallet, Radio,
} from 'lucide-react'
import { adminService, terminalService, patternService, paperService, marketService } from '@/services/api'
import type { QuoteItem } from '@/services/api'

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
    to: '/backtest',
    icon: Search,
    label: 'Scalper Backtest',
    description: 'Run historical scalping strategy simulations and review past performance.',
    color: '#F59E0B',
    badge: 'PAPER',
  },
  {
    to: '/patterns',
    icon: FlaskConical,
    label: 'Pattern Backtest',
    description: 'Paper simulation of the pattern strategy. Track performance without real capital.',
    color: '#3B82F6',
    badge: 'PAPER',
  },
  {
    to: '/signals',
    icon: Radio,
    label: 'Signal Advisor',
    description: 'Live Telegram signal feed. Claude parses trades, calculates your position size and risk, and shows you exactly what to enter on Yubit.',
    color: '#06B6D4',
    badge: 'LIVE',
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

// Deterministic candlestick data — general uptrend with natural pullbacks
const CANDLE_DATA = [
  { o: 142, c: 148, h: 151, l: 139 }, { o: 148, c: 145, h: 152, l: 143 },
  { o: 145, c: 153, h: 157, l: 142 }, { o: 153, c: 150, h: 158, l: 148 },
  { o: 150, c: 159, h: 162, l: 147 }, { o: 159, c: 163, h: 166, l: 156 },
  { o: 163, c: 158, h: 167, l: 155 }, { o: 158, c: 166, h: 169, l: 155 },
  { o: 166, c: 172, h: 175, l: 163 }, { o: 172, c: 169, h: 177, l: 166 },
  { o: 169, c: 177, h: 180, l: 166 }, { o: 177, c: 174, h: 181, l: 171 },
  { o: 174, c: 182, h: 185, l: 171 }, { o: 182, c: 179, h: 187, l: 176 },
  { o: 179, c: 188, h: 191, l: 176 }, { o: 188, c: 193, h: 196, l: 185 },
  { o: 193, c: 188, h: 197, l: 185 }, { o: 188, c: 196, h: 199, l: 185 },
  { o: 196, c: 201, h: 204, l: 193 }, { o: 201, c: 198, h: 206, l: 195 },
  { o: 198, c: 207, h: 210, l: 195 }, { o: 207, c: 213, h: 216, l: 204 },
  { o: 213, c: 209, h: 218, l: 206 }, { o: 209, c: 218, h: 221, l: 206 },
  { o: 218, c: 224, h: 227, l: 215 }, { o: 224, c: 221, h: 229, l: 218 },
  { o: 221, c: 231, h: 234, l: 218 }, { o: 231, c: 227, h: 236, l: 224 },
  { o: 227, c: 236, h: 239, l: 224 }, { o: 236, c: 242, h: 246, l: 233 },
]

const VOLUMES = [320, 280, 410, 350, 520, 380, 290, 460, 400, 310, 490, 360, 300, 440, 500, 420, 270, 480, 390, 340, 510, 430, 280, 460, 370, 290, 540, 400, 350, 470]

function BackgroundChart() {
  const SW = 1440
  const SH = 540
  const cw = 28
  const gap = 18
  const step = cw + gap
  const padL = 50
  const padT = 30
  const cH = 360
  const volH = 70
  const volPad = 16

  const allPrices = CANDLE_DATA.flatMap(c => [c.h, c.l])
  const pMin = Math.min(...allPrices) - 8
  const pMax = Math.max(...allPrices) + 8
  const pRange = pMax - pMin
  const toY = (p: number) => padT + cH - ((p - pMin) / pRange) * cH

  const maxVol = Math.max(...VOLUMES)

  const maPoints: string[] = []
  for (let i = 4; i < CANDLE_DATA.length; i++) {
    const avg = CANDLE_DATA.slice(i - 4, i + 1).reduce((s, c) => s + c.c, 0) / 5
    maPoints.push(`${padL + i * step + cw / 2},${toY(avg)}`)
  }

  return (
    <svg
      viewBox={`0 0 ${SW} ${SH}`}
      preserveAspectRatio="xMaxYMax meet"
      style={{
        position: 'fixed', right: '-2%', bottom: '8%',
        width: '68%', height: '65%',
        zIndex: 0, pointerEvents: 'none', opacity: 0.1,
      }}
    >
      <defs>
        <linearGradient id="fadeLeft" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#060810" stopOpacity="1" />
          <stop offset="35%" stopColor="#060810" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="volGreenGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00FF99" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#00FF99" stopOpacity="0.2" />
        </linearGradient>
        <linearGradient id="volRedGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#EF4444" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#EF4444" stopOpacity="0.2" />
        </linearGradient>
      </defs>

      {/* Horizontal grid lines */}
      {[0, 1, 2, 3, 4, 5].map(i => (
        <line key={i}
          x1={padL} y1={padT + (i / 5) * cH}
          x2={SW - 10} y2={padT + (i / 5) * cH}
          stroke="#00FF99" strokeWidth="0.4" opacity="0.35" strokeDasharray="6 10"
        />
      ))}

      {/* Candles */}
      {CANDLE_DATA.map((c, i) => {
        const x = padL + i * step
        const isGreen = c.c >= c.o
        const color = isGreen ? '#00FF99' : '#EF4444'
        const bodyTop = toY(Math.max(c.o, c.c))
        const bodyBot = toY(Math.min(c.o, c.c))
        const bh = Math.max(1.5, bodyBot - bodyTop)
        const wx = x + cw / 2
        return (
          <g key={i}>
            <line x1={wx} y1={toY(c.h)} x2={wx} y2={toY(c.l)} stroke={color} strokeWidth="1.5" />
            <rect x={x} y={bodyTop} width={cw} height={bh} fill={color} opacity="0.85" rx="1" />
          </g>
        )
      })}

      {/* MA line */}
      <polyline
        points={maPoints.join(' ')}
        fill="none" stroke="#F59E0B" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" opacity="0.8"
      />

      {/* Volume bars */}
      {VOLUMES.map((vol, i) => {
        const x = padL + i * step
        const bh = (vol / maxVol) * volH
        const y = padT + cH + volPad + volH - bh
        const isGreen = CANDLE_DATA[i].c >= CANDLE_DATA[i].o
        return (
          <rect key={i} x={x} y={y} width={cw} height={bh}
            fill={isGreen ? 'url(#volGreenGrad)' : 'url(#volRedGrad)'} rx="1" />
        )
      })}

      {/* Left fade mask */}
      <rect x="0" y="0" width={SW * 0.38} height={SH} fill="url(#fadeLeft)" />
    </svg>
  )
}

function fmtQuote(q: QuoteItem): string {
  const sign = q.change_pct >= 0 ? '+' : ''
  return `${q.symbol} ${sign}${q.change_pct.toFixed(2)}%`
}

function Ticker({ items, speed, direction, opacity = 1 }: {
  items: string[]
  speed: number
  direction: 'forward' | 'reverse'
  opacity?: number
}) {
  const doubled = [...items, ...items]
  return (
    <div style={{ overflow: 'hidden', opacity }}>
      <div style={{
        display: 'inline-flex', gap: 48, whiteSpace: 'nowrap',
        animation: `${direction === 'forward' ? 'tickerFwd' : 'tickerRev'} ${speed}s linear infinite`,
        fontFamily: 'Roboto Mono', fontSize: '0.72rem', letterSpacing: '0.04em',
      }}>
        {doubled.map((item, i) => {
          const isNeg = item.includes('-')
          return (
            <span key={i} style={{ color: isNeg ? '#EF4444' : '#00FF99', flexShrink: 0 }}>
              {item}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function PnLPill({ value }: { value: number | undefined }) {
  if (value === undefined) return <span style={{ color: '#475569', fontSize: '0.85rem' }}>—</span>
  const pos = value >= 0
  const Icon = value > 0.005 ? TrendingUp : value < -0.005 ? TrendingDown : Minus
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      color: pos ? '#00FF99' : '#EF4444',
      fontSize: '0.88rem', fontFamily: 'Roboto Mono', fontWeight: 600,
    }}>
      <Icon size={13} />
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

  const { data: scalperPaperState } = useQuery({
    queryKey: ['paper-state'],
    queryFn: () => paperService.getState().then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const { data: marketData } = useQuery({
    queryKey: ['market-quotes'],
    queryFn: () => marketService.getQuotes().then((r) => r.data),
    refetchInterval: 60000,
    staleTime: 55000,
    retry: false,
  })

  const topItems = marketData?.top?.map(fmtQuote) ?? []
  const bottomItems = marketData?.bottom?.map(fmtQuote) ?? []

  const backendOnline = status?.loop_running || status?.trader_running || status?.grok_running

  const pnlByRoute: Record<string, number | undefined> = {
    '/scalper': scalperState?.daily_pnl,
    '/pattern': patternState?.daily_pnl,
    '/patterns': paperState?.daily_pnl,
    '/backtest': scalperPaperState?.daily_pnl,
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'radial-gradient(ellipse at 65% 35%, #0D1825 0%, #080C12 55%, #050810 100%)',
      boxSizing: 'border-box',
      position: 'relative',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Grid overlay */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
        backgroundImage:
          'linear-gradient(#00FF9905 1px, transparent 1px), linear-gradient(90deg, #00FF9905 1px, transparent 1px)',
        backgroundSize: '64px 64px',
      }} />

      {/* Background candlestick chart */}
      <BackgroundChart />

      {/* Top vignette */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: 160, zIndex: 0, pointerEvents: 'none',
        background: 'linear-gradient(to bottom, #050810 0%, transparent 100%)',
      }} />

      {/* Content layer */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', flex: 1 }}>

        {/* Top ticker */}
        <div style={{
          background: 'rgba(0,255,153,0.03)',
          borderBottom: '1px solid rgba(0,255,153,0.12)',
          padding: '7px 0',
          flexShrink: 0,
        }}>
          {topItems.length > 0
            ? <Ticker items={topItems} speed={32} direction="forward" />
            : <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: '#1F2937', padding: '0 20px' }}>Loading market data…</div>
          }
        </div>

        {/* Main */}
        <div style={{ flex: 1, padding: '52px 5vw 44px', display: 'flex', flexDirection: 'column', gap: 48 }}>

          {/* Header row */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 40, flexWrap: 'wrap' }}>

            {/* Left: logo + description */}
            <div style={{ flex: 1, minWidth: 300 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
                <Cpu size={42} color="#00FF99" style={{ filter: 'drop-shadow(0 0 14px #00FF9970)' } as React.CSSProperties} />
                <span style={{
                  fontFamily: 'Roboto Mono', fontSize: '2.6rem', fontWeight: 700,
                  color: '#00FF99', letterSpacing: 4,
                  textShadow: '0 0 40px #00FF9930',
                }}>
                  QUANT_OS
                </span>
              </div>
              <p style={{
                margin: 0, color: '#94A3B8', fontSize: '1.05rem', maxWidth: 600, lineHeight: 1.75,
              }}>
                Algorithmic trading system running two independent intraday strategies.
                The{' '}
                <span style={{ color: '#00FF99', fontWeight: 600 }}>Scalper</span>
                {' '}trades L2 order-book imbalances in real time.
                The{' '}
                <span style={{ color: '#A855F7', fontWeight: 600 }}>Pattern</span>
                {' '}strategy enters confirmed chart-pattern breakouts on 1-minute bar closes.
                Both run live with full Kelly position sizing.
              </p>
            </div>

            {/* Account value card */}
            <div style={{
              background: 'rgba(13, 18, 30, 0.85)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 16,
              padding: '22px 28px',
              display: 'flex', flexDirection: 'column', gap: 10,
              flexShrink: 0, minWidth: 180,
              backdropFilter: 'blur(12px)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Wallet size={14} color="#64748B" />
                <span style={{ fontSize: '0.66rem', color: '#475569', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                  Account Value
                </span>
              </div>
              <div style={{ fontFamily: 'Roboto Mono', fontSize: '1.45rem', fontWeight: 700, color: '#F1F5F9', letterSpacing: '-0.5px' }}>
                {scalperState?.account_details?.liquidation_value != null
                  ? `$${scalperState.account_details.liquidation_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : <span style={{ color: '#334155', fontSize: '1.1rem' }}>—</span>
                }
              </div>
              <div style={{ fontSize: '0.68rem', color: '#334155', letterSpacing: '0.04em' }}>
                LIQUIDATION VALUE
              </div>
            </div>

            {/* Right: system status */}
            <div style={{
              background: 'rgba(13, 18, 30, 0.85)',
              border: `1px solid ${backendOnline ? 'rgba(0,255,153,0.25)' : 'rgba(239,68,68,0.25)'}`,
              borderRadius: 16,
              padding: '22px 28px',
              display: 'flex', flexDirection: 'column', gap: 14,
              flexShrink: 0, minWidth: 220,
              backdropFilter: 'blur(12px)',
              boxShadow: backendOnline
                ? '0 0 40px rgba(0,255,153,0.08), inset 0 1px 0 rgba(0,255,153,0.1)'
                : '0 0 40px rgba(239,68,68,0.06)',
            }}>
              <div style={{ fontSize: '0.66rem', color: '#475569', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                System Status
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{
                  width: 11, height: 11, borderRadius: '50%', flexShrink: 0,
                  background: backendOnline ? '#00FF99' : '#EF4444',
                  boxShadow: backendOnline ? '0 0 14px #00FF99, 0 0 6px #00FF99' : '0 0 14px #EF4444',
                  display: 'inline-block',
                }} />
                <span style={{ fontSize: '0.95rem', color: '#E2E8F0', fontFamily: 'Roboto Mono', fontWeight: 700 }}>
                  {backendOnline ? 'Bot Online' : 'Bot Offline'}
                </span>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24 }}>
                  <span style={{ fontSize: '0.78rem', color: '#64748B' }}>Scalper PnL</span>
                  <PnLPill value={scalperState?.daily_pnl} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24 }}>
                  <span style={{ fontSize: '0.78rem', color: '#64748B' }}>Pattern PnL</span>
                  <PnLPill value={patternState?.daily_pnl} />
                </div>
              </div>
            </div>
          </div>

          {/* Nav cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(290px, 1fr))',
            gap: 20,
          }}>
            {CARDS.map(({ to, icon: Icon, label, description, color, badge }) => (
              <button
                key={to}
                onClick={() => navigate(to)}
                style={{
                  background: 'rgba(13, 18, 28, 0.82)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 16,
                  padding: '28px 30px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 16,
                  position: 'relative',
                  overflow: 'hidden',
                  transition: 'border-color 0.2s, background 0.2s, box-shadow 0.2s, transform 0.15s',
                  backdropFilter: 'blur(10px)',
                }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLButtonElement
                  el.style.borderColor = color
                  el.style.background = 'rgba(18, 26, 42, 0.95)'
                  el.style.boxShadow = `0 0 36px ${color}22, 0 8px 32px rgba(0,0,0,0.5)`
                  el.style.transform = 'translateY(-3px)'
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLButtonElement
                  el.style.borderColor = 'rgba(255,255,255,0.07)'
                  el.style.background = 'rgba(13, 18, 28, 0.82)'
                  el.style.boxShadow = 'none'
                  el.style.transform = 'translateY(0)'
                }}
              >
                {/* Top accent bar */}
                <div style={{
                  position: 'absolute', top: 0, left: 0, right: 0, height: 3,
                  background: `linear-gradient(90deg, ${color}, ${color}50)`,
                  borderRadius: '16px 16px 0 0',
                }} />

                {/* Ambient corner glow */}
                <div style={{
                  position: 'absolute', top: -60, right: -60,
                  width: 160, height: 160, borderRadius: '50%',
                  background: `${color}07`,
                  pointerEvents: 'none',
                }} />

                {/* Icon + badge row */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{
                    width: 50, height: 50, borderRadius: 13,
                    background: `${color}15`,
                    border: `1px solid ${color}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon size={24} color={color} />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {badge && (
                      <span style={{
                        fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.1em',
                        color: color, background: `${color}12`,
                        border: `1px solid ${color}40`,
                        borderRadius: 6, padding: '4px 9px',
                        fontFamily: 'Roboto Mono',
                      }}>
                        {badge}
                      </span>
                    )}
                    {to in pnlByRoute && pnlByRoute[to] !== undefined && (
                      <PnLPill value={pnlByRoute[to]} />
                    )}
                  </div>
                </div>

                {/* Label + description */}
                <div>
                  <div style={{
                    fontSize: '1.1rem', fontWeight: 700, color: '#F1F5F9',
                    fontFamily: 'Roboto Mono', letterSpacing: '0.03em', marginBottom: 8,
                  }}>
                    {label}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#64748B', lineHeight: 1.65 }}>
                    {description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Bottom ticker */}
        <div style={{
          background: 'rgba(0,255,153,0.03)',
          borderTop: '1px solid rgba(0,255,153,0.12)',
          padding: '7px 0',
          flexShrink: 0,
        }}>
          {bottomItems.length > 0
            ? <Ticker items={bottomItems} speed={32} direction="reverse" />
            : <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.7rem', color: '#1F2937', padding: '0 20px' }}>—</div>
          }
        </div>
      </div>

      <style>{`
        @keyframes tickerFwd {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes tickerRev {
          0%   { transform: translateX(-50%); }
          100% { transform: translateX(0); }
        }
      `}</style>
    </div>
  )
}
