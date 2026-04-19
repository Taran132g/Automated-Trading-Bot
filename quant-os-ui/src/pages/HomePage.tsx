import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Activity, Search, BarChart2, FlaskConical,
  GitCompare, Terminal, Bot, ShieldAlert, Radio,
  TrendingUp, TrendingDown, Minus, Wallet, ArrowRight,
} from 'lucide-react'
import { adminService, terminalService, patternService, paperService, marketService } from '@/services/api'
import type { QuoteItem } from '@/services/api'

/* ─── palette ─── */
const BG   = '#031818'
const CARD = '#052424'
const ELEV = '#0a2e2e'
const LIME = '#abff02'
const DIM  = '#4a6a5a'
const TEXT = '#e4f0e4'
const SEC  = '#7a9a8a'
const BORDER = 'rgba(171,255,2,0.08)'
const RED  = '#ff4466'
const GREEN = '#00ff88'

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
    accent: '#c084fc',
    tag: 'LIVE',
  },
  {
    to: '/signals',
    icon: Radio,
    label: 'Signal Advisor',
    sub: 'Telegram signal feed with Claude risk cards and position sizing.',
    accent: '#22d3ee',
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
    accent: SEC,
    tag: null,
  },
  {
    to: '/backtest',
    icon: Search,
    label: 'Scalper Backtest',
    sub: 'Historical scalping simulations and past performance review.',
    accent: '#fbbf24',
    tag: 'PAPER',
  },
  {
    to: '/patterns',
    icon: FlaskConical,
    label: 'Pattern Lab',
    sub: 'Paper simulation of the pattern strategy without real capital.',
    accent: '#60a5fa',
    tag: 'PAPER',
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
        width: '68%', height: '65%', zIndex: 0, pointerEvents: 'none', opacity: 0.06,
      }}>
      <defs>
        <linearGradient id="fadeLeft" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={BG} stopOpacity="1" />
          <stop offset="35%" stopColor={BG} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="volGreenGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={LIME} stopOpacity="0.7" />
          <stop offset="100%" stopColor={LIME} stopOpacity="0.2" />
        </linearGradient>
        <linearGradient id="volRedGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={RED} stopOpacity="0.7" />
          <stop offset="100%" stopColor={RED} stopOpacity="0.2" />
        </linearGradient>
      </defs>
      {[0,1,2,3,4,5].map(i => (
        <line key={i} x1={padL} y1={padT + (i/5)*cH} x2={SW-10} y2={padT + (i/5)*cH}
          stroke={LIME} strokeWidth="0.4" opacity="0.35" strokeDasharray="6 10" />
      ))}
      {CANDLE_DATA.map((c, i) => {
        const x = padL + i * step
        const isGreen = c.c >= c.o
        const color = isGreen ? LIME : RED
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
      <polyline points={maPoints.join(' ')} fill="none" stroke="#fbbf24" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" opacity="0.8" />
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
        fontFamily: 'JetBrains Mono, Roboto Mono, monospace', fontSize: '0.7rem', letterSpacing: '0.04em',
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
  if (value === undefined) return <span style={{ color: DIM, fontSize: '0.85rem' }}>—</span>
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
      background: `radial-gradient(ellipse at 50% 0%, #0a3030 0%, ${BG} 60%)`,
      position: 'relative', overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Grid texture */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
        backgroundImage:
          `linear-gradient(${LIME}04 1px, transparent 1px), linear-gradient(90deg, ${LIME}04 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
      }} />

      {/* Scanline effect */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none', overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', left: 0, right: 0, height: 200,
          background: `linear-gradient(180deg, transparent, ${LIME}03, transparent)`,
          animation: 'scanline 8s linear infinite',
        }} />
      </div>

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
          background: 'rgba(171,255,2,0.03)',
          borderBottom: `1px solid ${BORDER}`,
          padding: '7px 0', flexShrink: 0,
        }}>
          {topItems.length > 0
            ? <Ticker items={topItems} speed={32} direction="forward" />
            : <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM, padding: '0 20px' }}>Loading market data...</div>
          }
        </div>

        {/* Main content */}
        <div style={{ flex: 1, padding: '60px 5vw 48px', display: 'flex', flexDirection: 'column', gap: 56 }}>

          {/* ─── Hero ─── */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 40, flexWrap: 'wrap' }}>

            {/* Left: hero title */}
            <div style={{ flex: 1, minWidth: 320 }}>
              <div style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: 'min(8vw, 5.5rem)',
                fontWeight: 900,
                color: LIME,
                letterSpacing: '-0.04em',
                lineHeight: 0.95,
                marginBottom: 24,
                textShadow: `0 0 80px ${LIME}20`,
              }}>
                QUANT<span style={{ color: TEXT }}>_</span>OS
              </div>
              <p style={{
                margin: 0, color: SEC, fontSize: '1.05rem', maxWidth: 560, lineHeight: 1.8,
                letterSpacing: '-0.01em',
              }}>
                Algorithmic trading system running two independent intraday strategies.
                The <span style={{ color: GREEN, fontWeight: 600 }}>Scalper</span> trades
                L2 order-book imbalances in real time.
                The <span style={{ color: '#c084fc', fontWeight: 600 }}>Pattern</span> strategy
                enters confirmed chart-pattern breakouts on 1-minute bar closes.
              </p>
            </div>

            {/* Right: status cards */}
            <div style={{ display: 'flex', gap: 16, flexShrink: 0, flexWrap: 'wrap' }}>
              {/* Account value */}
              <div style={{
                background: 'rgba(5,36,36,0.85)',
                border: `1px solid ${BORDER}`,
                borderRadius: 12, padding: '20px 24px',
                backdropFilter: 'blur(16px)',
                display: 'flex', flexDirection: 'column', gap: 8, minWidth: 180,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <Wallet size={13} color={DIM} />
                  <span style={{ fontSize: '0.62rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                    Account Value
                  </span>
                </div>
                <div style={{
                  fontFamily: 'JetBrains Mono, monospace', fontSize: '1.4rem', fontWeight: 700,
                  color: TEXT, letterSpacing: '-0.5px',
                }}>
                  {scalperState?.account_details?.liquidation_value != null
                    ? `$${scalperState.account_details.liquidation_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : <span style={{ color: DIM, fontSize: '1.1rem' }}>—</span>
                  }
                </div>
                <div style={{ fontSize: '0.62rem', color: DIM, letterSpacing: '0.04em' }}>
                  LIQUIDATION VALUE
                </div>
              </div>

              {/* System status */}
              <div style={{
                background: 'rgba(5,36,36,0.85)',
                border: `1px solid ${backendOnline ? 'rgba(171,255,2,0.2)' : 'rgba(255,68,102,0.2)'}`,
                borderRadius: 12, padding: '20px 24px',
                backdropFilter: 'blur(16px)',
                display: 'flex', flexDirection: 'column', gap: 12, minWidth: 200,
                boxShadow: backendOnline ? `0 0 40px rgba(171,255,2,0.06)` : 'none',
              }}>
                <div style={{ fontSize: '0.62rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                  System Status
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: backendOnline ? LIME : RED,
                    boxShadow: backendOnline ? `0 0 12px ${LIME}` : `0 0 12px ${RED}`,
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
              fontSize: '0.68rem', color: DIM, letterSpacing: '0.16em',
              textTransform: 'uppercase', marginBottom: 20, fontWeight: 600,
            }}>
              Modules
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 16,
            }}>
              {CARDS.map(({ to, icon: Icon, label, sub, accent, tag }) => (
                <button
                  key={to}
                  onClick={() => navigate(to)}
                  style={{
                    background: 'rgba(5,36,36,0.7)',
                    border: `1px solid ${BORDER}`,
                    borderRadius: 12,
                    padding: '24px 26px',
                    cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex', flexDirection: 'column', gap: 14,
                    position: 'relative', overflow: 'hidden',
                    transition: 'all 0.3s cubic-bezier(.16,1,.3,1)',
                    backdropFilter: 'blur(8px)',
                  }}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = accent
                    el.style.background = 'rgba(10,46,46,0.95)'
                    el.style.boxShadow = `0 0 30px ${accent}15, 0 8px 32px rgba(0,0,0,0.4)`
                    el.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = 'rgba(171,255,2,0.08)'
                    el.style.background = 'rgba(5,36,36,0.7)'
                    el.style.boxShadow = 'none'
                    el.style.transform = 'translateY(0)'
                  }}
                >
                  {/* Top accent line */}
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                    background: `linear-gradient(90deg, ${accent}, transparent)`,
                  }} />

                  {/* Icon + badges row */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{
                      width: 44, height: 44, borderRadius: 10,
                      background: `${accent}12`,
                      border: `1px solid ${accent}25`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Icon size={20} color={accent} />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {tag && (
                        <span style={{
                          fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.1em',
                          color: accent, background: `${accent}10`,
                          border: `1px solid ${accent}30`,
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
                      display: 'flex', alignItems: 'center', gap: 8,
                      marginBottom: 6,
                    }}>
                      <span style={{
                        fontSize: '1rem', fontWeight: 700, color: TEXT,
                        fontFamily: 'Inter, sans-serif', letterSpacing: '-0.01em',
                      }}>
                        {label}
                      </span>
                      <ArrowRight size={14} color={DIM} style={{ opacity: 0.5 }} />
                    </div>
                    <div style={{ fontSize: '0.8rem', color: SEC, lineHeight: 1.6 }}>
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
          background: 'rgba(171,255,2,0.03)',
          borderTop: `1px solid ${BORDER}`,
          padding: '7px 0', flexShrink: 0,
        }}>
          {bottomItems.length > 0
            ? <Ticker items={bottomItems} speed={32} direction="reverse" />
            : <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM, padding: '0 20px' }}>—</div>
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
