import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity, Search, BarChart2, FlaskConical,
  GitCompare, Terminal, Bot, ShieldAlert, Radio,
  TrendingUp, TrendingDown, Minus, Wallet, ArrowRight,
  Zap,
} from 'lucide-react'
import { adminService, terminalService, patternService, paperService, marketService } from '@/services/api'
import type { QuoteItem } from '@/services/api'

/* ─── palette ─── */
const BG    = '#06060b'
const BG1   = '#0c0c14'
const BG2   = '#12121c'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED   = '#ef4444'
const BLUE  = '#3b82f6'
const PURPLE = '#a78bfa'
const CYAN  = '#22d3ee'
const AMBER = '#f59e0b'
const TEXT  = '#f0f0f5'
const SEC   = '#8b8b9e'
const DIM   = '#55556a'
const FAINT = '#33334a'
const BORDER = 'rgba(255,255,255,0.06)'

const CARDS = [
  {
    to: '/scalper',
    icon: Activity,
    label: 'Scalper',
    sub: 'Live L2 imbalance scalping. Real-time order book signals and execution.',
    accent: GREEN,
    tag: 'LIVE',
  },
  {
    to: '/pattern',
    icon: BarChart2,
    label: 'Pattern',
    sub: 'Chart-pattern breakout strategy. Confirmed breakouts on 1-min bars.',
    accent: PURPLE,
    tag: 'LIVE',
  },
  {
    to: '/signals',
    icon: Radio,
    label: 'Signal Advisor',
    sub: 'Telegram signal feed with Claude risk cards and position sizing.',
    accent: CYAN,
    tag: 'LIVE',
  },
  {
    to: '/comparison',
    icon: GitCompare,
    label: 'Comparison',
    sub: 'Side-by-side live vs paper performance metrics.',
    accent: SEC,
    tag: null,
  },
  {
    to: '/grok',
    icon: Terminal,
    label: 'Grok Monitor',
    sub: 'Real-time stream logs, L2 events, and alert feed.',
    accent: AMBER,
    tag: null,
  },
  {
    to: '/backtest',
    icon: Search,
    label: 'Scalper Backtest',
    sub: 'Historical scalping simulations and past performance review.',
    accent: BLUE,
    tag: 'SIM',
  },
  {
    to: '/patterns',
    icon: FlaskConical,
    label: 'Pattern Lab',
    sub: 'Paper simulation of the pattern strategy without real capital.',
    accent: BLUE,
    tag: 'SIM',
  },
  {
    to: '/agents',
    icon: Bot,
    label: 'AI Agents',
    sub: 'Post-market analysis reports and automated insight agents.',
    accent: '#f472b6',
    tag: null,
  },
  {
    to: '/admin',
    icon: ShieldAlert,
    label: 'Admin',
    sub: 'System controls, symbol config, position sizing, Kelly parameters.',
    accent: RED,
    tag: 'AUTH',
  },
]

/* ─── background candlestick chart ─── */
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
const VOLUMES = [320,280,410,350,520,380,290,460,400,310,490,360,300,440,500,420,270,480,390,340,510,430,280,460,370,290,540,400,350,470]

function BackgroundChart() {
  const SW = 1440, SH = 540, cw = 28, gap = 18, step = cw + gap
  const padL = 50, padT = 30, cH = 360, volH = 70, volPad = 16
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
    <svg viewBox={`0 0 ${SW} ${SH}`} preserveAspectRatio="xMaxYMax meet"
      style={{
        position: 'fixed', right: '-2%', bottom: '8%',
        width: '68%', height: '65%', zIndex: 0, pointerEvents: 'none', opacity: 0.04,
      }}>
      <defs>
        <linearGradient id="fadeLeft" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={BG} stopOpacity="1" />
          <stop offset="35%" stopColor={BG} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="volGreenGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={GREEN} stopOpacity="0.7" />
          <stop offset="100%" stopColor={GREEN} stopOpacity="0.2" />
        </linearGradient>
        <linearGradient id="volRedGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={RED} stopOpacity="0.7" />
          <stop offset="100%" stopColor={RED} stopOpacity="0.2" />
        </linearGradient>
      </defs>
      {[0,1,2,3,4,5].map(i => (
        <line key={i} x1={padL} y1={padT + (i/5)*cH} x2={SW-10} y2={padT + (i/5)*cH}
          stroke="#fff" strokeWidth="0.4" opacity="0.15" strokeDasharray="6 10" />
      ))}
      {CANDLE_DATA.map((c, i) => {
        const x = padL + i * step
        const isGreen = c.c >= c.o
        const color = isGreen ? GREEN : RED
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
      <polyline points={maPoints.join(' ')} fill="none" stroke={AMBER} strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" opacity="0.6" />
      {VOLUMES.map((vol, i) => {
        const x = padL + i * step
        const bh = (vol / maxVol) * volH
        const y = padT + cH + volPad + volH - bh
        const isGreen = CANDLE_DATA[i].c >= CANDLE_DATA[i].o
        return <rect key={i} x={x} y={y} width={cw} height={bh}
          fill={isGreen ? 'url(#volGreenGrad)' : 'url(#volRedGrad)'} rx="1" />
      })}
      <rect x="0" y="0" width={SW * 0.38} height={SH} fill="url(#fadeLeft)" />
    </svg>
  )
}

/* ─── helpers ─── */
function fmtQuote(q: QuoteItem): string {
  const sign = q.change_pct >= 0 ? '+' : ''
  return `${q.symbol} ${sign}${q.change_pct.toFixed(2)}%`
}

function Ticker({ items, speed, direction, opacity = 1 }: {
  items: string[]; speed: number; direction: 'forward' | 'reverse'; opacity?: number
}) {
  const doubled = [...items, ...items]
  return (
    <div style={{ overflow: 'hidden', opacity }}>
      <div style={{
        display: 'inline-flex', gap: 48, whiteSpace: 'nowrap',
        animation: `${direction === 'forward' ? 'tickerFwd' : 'tickerRev'} ${speed}s linear infinite`,
        fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', letterSpacing: '0.04em',
      }}>
        {doubled.map((item, i) => {
          const isNeg = item.includes('-')
          return <span key={i} style={{ color: isNeg ? RED : GREEN, flexShrink: 0 }}>{item}</span>
        })}
      </div>
    </div>
  )
}

function PnLPill({ value }: { value: number | undefined }) {
  if (value === undefined) return <span style={{ color: DIM, fontSize: '0.85rem' }}>&mdash;</span>
  const pos = value >= 0
  const Icon = value > 0.005 ? TrendingUp : value < -0.005 ? TrendingDown : Minus
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      color: pos ? GREEN : RED,
      fontSize: '0.85rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
    }}>
      <Icon size={13} />
      {pos ? '+' : ''}${Math.abs(value).toFixed(2)}
    </span>
  )
}

/* ─── page ─── */
export function HomePage() {
  const navigate = useNavigate()

  const { data: status } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const { data: scalperState } = useQuery({
    queryKey: ['terminal-state'],
    queryFn: () => terminalService.getState().then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const { data: patternState } = useQuery({
    queryKey: ['pattern-state-live'],
    queryFn: () => patternService.getState('live').then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const { data: paperState } = useQuery({
    queryKey: ['pattern-state-paper'],
    queryFn: () => patternService.getState('paper').then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const { data: scalperPaperState } = useQuery({
    queryKey: ['paper-state'],
    queryFn: () => paperService.getState().then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const { data: marketData } = useQuery({
    queryKey: ['market-quotes'],
    queryFn: () => marketService.getQuotes().then((r) => r.data),
    refetchInterval: 60000, staleTime: 55000, retry: false,
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
      background: `radial-gradient(ellipse at 50% 0%, #14141f 0%, ${BG} 55%)`,
      position: 'relative', overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Subtle dot grid */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
      }} />

      <BackgroundChart />

      {/* Top vignette */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: 200,
        zIndex: 0, pointerEvents: 'none',
        background: `linear-gradient(to bottom, ${BG} 0%, transparent 100%)`,
      }} />

      {/* Content */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', flex: 1 }}>

        {/* Top ticker */}
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          borderBottom: `1px solid ${BORDER}`,
          padding: '7px 0', flexShrink: 0,
        }}>
          {topItems.length > 0
            ? <Ticker items={topItems} speed={32} direction="forward" />
            : <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: FAINT, padding: '0 20px' }}>Loading market data...</div>
          }
        </div>

        {/* Main content */}
        <div style={{ flex: 1, padding: '72px 6vw 48px', display: 'flex', flexDirection: 'column', gap: 64 }}>

          {/* ─── Hero ─── */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 48, flexWrap: 'wrap' }}>
            {/* Left: hero text */}
            <div style={{ flex: 1, minWidth: 340 }}>
              <div style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: 'min(7.5vw, 5rem)',
                fontWeight: 900,
                color: ACCENT,
                letterSpacing: '-0.05em',
                lineHeight: 0.92,
                marginBottom: 28,
                textShadow: `0 0 120px rgba(200,255,0,0.12)`,
              }}>
                QUANT<span style={{ color: FAINT }}>_</span><span style={{ color: TEXT }}>OS</span>
              </div>
              <p style={{
                margin: 0, color: SEC, fontSize: '1.05rem', maxWidth: 520, lineHeight: 1.8,
                letterSpacing: '-0.01em',
              }}>
                Algorithmic trading system running two independent intraday strategies.
                The <span style={{ color: GREEN, fontWeight: 600 }}>Scalper</span> trades
                L2 order-book imbalances in real time.
                The <span style={{ color: PURPLE, fontWeight: 600 }}>Pattern</span> strategy
                enters confirmed chart-pattern breakouts on 1-minute bar closes.
              </p>
            </div>

            {/* Right: status cards */}
            <div style={{ display: 'flex', gap: 14, flexShrink: 0, flexWrap: 'wrap' }}>
              {/* Account value */}
              <div style={{
                background: 'rgba(12,12,20,0.8)',
                border: `1px solid ${BORDER}`,
                borderRadius: 14, padding: '22px 26px',
                backdropFilter: 'blur(20px)',
                display: 'flex', flexDirection: 'column', gap: 8, minWidth: 190,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <Wallet size={13} color={DIM} />
                  <span style={{ fontSize: '0.6rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                    Account Value
                  </span>
                </div>
                <div style={{
                  fontFamily: 'JetBrains Mono, monospace', fontSize: '1.5rem', fontWeight: 700,
                  color: TEXT, letterSpacing: '-0.5px',
                }}>
                  {scalperState?.account_details?.liquidation_value != null
                    ? `$${scalperState.account_details.liquidation_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : <span style={{ color: DIM, fontSize: '1.1rem' }}>&mdash;</span>
                  }
                </div>
                <div style={{ fontSize: '0.6rem', color: FAINT, letterSpacing: '0.04em' }}>
                  LIQUIDATION VALUE
                </div>
              </div>

              {/* System status */}
              <div style={{
                background: 'rgba(12,12,20,0.8)',
                border: `1px solid ${backendOnline ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'}`,
                borderRadius: 14, padding: '22px 26px',
                backdropFilter: 'blur(20px)',
                display: 'flex', flexDirection: 'column', gap: 12, minWidth: 210,
                boxShadow: backendOnline ? '0 0 60px rgba(34,197,94,0.04)' : 'none',
              }}>
                <div style={{ fontSize: '0.6rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                  System Status
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: backendOnline ? GREEN : RED,
                    boxShadow: backendOnline ? `0 0 12px ${GREEN}` : `0 0 12px ${RED}`,
                    display: 'inline-block',
                  }} />
                  <span style={{
                    fontSize: '0.9rem', color: TEXT,
                    fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                  }}>
                    {backendOnline ? 'Online' : 'Offline'}
                  </span>
                </div>
                <div style={{ borderTop: `1px solid ${BORDER}`, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24 }}>
                    <span style={{ fontSize: '0.75rem', color: DIM }}>Scalper</span>
                    <PnLPill value={scalperState?.daily_pnl} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24 }}>
                    <span style={{ fontSize: '0.75rem', color: DIM }}>Pattern</span>
                    <PnLPill value={patternState?.daily_pnl} />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ─── Navigation grid ─── */}
          <div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24,
            }}>
              <Zap size={14} color={ACCENT} style={{ opacity: 0.6 }} />
              <span style={{
                fontSize: '0.66rem', color: DIM, letterSpacing: '0.16em',
                textTransform: 'uppercase', fontWeight: 600,
              }}>
                Modules
              </span>
              <div style={{ flex: 1, height: 1, background: BORDER }} />
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(290px, 1fr))',
              gap: 14,
            }}>
              {CARDS.map(({ to, icon: Icon, label, sub, accent, tag }) => (
                <button
                  key={to}
                  onClick={() => navigate(to)}
                  style={{
                    background: 'rgba(12,12,20,0.6)',
                    border: `1px solid ${BORDER}`,
                    borderRadius: 12,
                    padding: '24px 26px',
                    cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex', flexDirection: 'column', gap: 14,
                    position: 'relative', overflow: 'hidden',
                    transition: 'all 0.35s cubic-bezier(.16,1,.3,1)',
                    backdropFilter: 'blur(8px)',
                  }}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = `${accent}40`
                    el.style.background = 'rgba(18,18,28,0.9)'
                    el.style.boxShadow = `0 0 40px ${accent}08, 0 8px 32px rgba(0,0,0,0.4)`
                    el.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = 'rgba(255,255,255,0.06)'
                    el.style.background = 'rgba(12,12,20,0.6)'
                    el.style.boxShadow = 'none'
                    el.style.transform = 'translateY(0)'
                  }}
                >
                  {/* Top accent line */}
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, height: 1,
                    background: `linear-gradient(90deg, ${accent}60, transparent 70%)`,
                  }} />

                  {/* Icon + badges row */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: `${accent}0a`,
                      border: `1px solid ${accent}18`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Icon size={18} color={accent} />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {tag && (
                        <span style={{
                          fontSize: '0.56rem', fontWeight: 700, letterSpacing: '0.1em',
                          color: accent, background: `${accent}0c`,
                          border: `1px solid ${accent}22`,
                          borderRadius: 4, padding: '3px 8px',
                          fontFamily: 'JetBrains Mono, monospace',
                        }}>
                          {tag}
                        </span>
                      )}
                      {to in pnlByRoute && pnlByRoute[to] !== undefined && (
                        <PnLPill value={pnlByRoute[to]} />
                      )}
                    </div>
                  </div>

                  {/* Label */}
                  <div>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
                    }}>
                      <span style={{
                        fontSize: '1rem', fontWeight: 700, color: TEXT,
                        fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em',
                      }}>
                        {label}
                      </span>
                      <ArrowRight size={13} color={FAINT} style={{ opacity: 0.5 }} />
                    </div>
                    <div style={{ fontSize: '0.78rem', color: SEC, lineHeight: 1.6 }}>
                      {sub}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom ticker */}
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          borderTop: `1px solid ${BORDER}`,
          padding: '7px 0', flexShrink: 0,
        }}>
          {bottomItems.length > 0
            ? <Ticker items={bottomItems} speed={32} direction="reverse" />
            : <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: FAINT, padding: '0 20px' }}>&mdash;</div>
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
