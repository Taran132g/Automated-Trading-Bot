import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Activity, BarChart2, Radio, TrendingUp, TrendingDown,
  ArrowRight, Zap, Shield, Brain,
} from 'lucide-react'
import {
  adminService, terminalService, patternService, marketService,
} from '@/services/api'
import type { QuoteItem } from '@/services/api'

const GREEN = '#22c55e'
const RED = '#ef4444'
const ACCENT = '#c8ff00'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const BORDER = 'rgba(255,255,255,0.06)'
const CARD = 'rgba(12,12,20,0.75)'

function useEntrance(delay = 0) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])
  return visible
}

function AnimBlock({
  children, delay = 0, style = {},
}: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  const visible = useEntrance(delay)
  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(18px)',
      transition: 'opacity 0.7s cubic-bezier(0.16,1,0.3,1), transform 0.7s cubic-bezier(0.16,1,0.3,1)',
      ...style,
    }}>
      {children}
    </div>
  )
}

function GridBackground() {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
      overflow: 'hidden',
    }}>
      {/* Grid lines */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px)
        `,
        backgroundSize: '60px 60px',
      }} />
      {/* Radial glow — top center */}
      <div style={{
        position: 'absolute',
        top: -200, left: '50%', transform: 'translateX(-50%)',
        width: 900, height: 500,
        background: 'radial-gradient(ellipse, rgba(200,255,0,0.04) 0%, transparent 70%)',
      }} />
      {/* Radial glow — bottom right */}
      <div style={{
        position: 'absolute',
        bottom: -100, right: -100,
        width: 600, height: 400,
        background: 'radial-gradient(ellipse, rgba(59,130,246,0.04) 0%, transparent 70%)',
      }} />
    </div>
  )
}

function StatPill({ label, value, color = SEC }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      background: CARD,
      border: `1px solid ${BORDER}`,
      borderRadius: 8,
      padding: '10px 18px',
      backdropFilter: 'blur(6px)',
    }}>
      <div style={{ fontSize: '0.5rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 5 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.05rem', fontWeight: 700, color }}>
        {value}
      </div>
    </div>
  )
}

function StrategyLiveCard({
  accent, icon: Icon, label, tag, running, pnl, winRate, to,
}: {
  accent: string; icon: React.ElementType; label: string; tag: string
  running: boolean; pnl?: number; winRate?: number; to: string
}) {
  const navigate = useNavigate()
  const pnlColor = pnl == null ? DIM : pnl >= 0 ? GREEN : RED
  return (
    <button
      onClick={() => navigate(to)}
      style={{
        flex: 1, minWidth: 0,
        background: CARD,
        border: `1px solid ${BORDER}`,
        borderRadius: 12,
        padding: '18px 20px',
        textAlign: 'left', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', gap: 12,
        backdropFilter: 'blur(8px)',
        transition: 'border-color 0.18s, background 0.18s',
        position: 'relative', overflow: 'hidden',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = `${accent}40`
        e.currentTarget.style.background = 'rgba(16,16,26,0.9)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = BORDER
        e.currentTarget.style.background = CARD
      }}
    >
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 1,
        background: `linear-gradient(90deg, ${accent}80, transparent 55%)`,
      }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon size={14} color={accent} />
          <span style={{ fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.12em', color: accent }}>
            {label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Animated status dot */}
          <div style={{ position: 'relative', width: 7, height: 7 }}>
            <span style={{
              position: 'absolute', inset: 0, borderRadius: '50%',
              background: running ? GREEN : DIM,
              animation: running ? 'botPulseCore 2s ease-in-out infinite' : 'none',
            }} />
            {running && (
              <span style={{
                position: 'absolute', inset: -3, borderRadius: '50%',
                border: `1px solid ${GREEN}`, opacity: 0,
                animation: 'botPulseRing 2s ease-out infinite',
              }} />
            )}
          </div>
          <span style={{
            fontSize: '0.48rem', fontWeight: 700, letterSpacing: '0.1em',
            fontFamily: 'JetBrains Mono',
            padding: '2px 6px', borderRadius: 3,
            background: `${accent}10`, border: `1px solid ${accent}25`,
            color: accent,
          }}>
            {tag}
          </span>
        </div>
      </div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '1.65rem', fontWeight: 700, color: pnlColor, letterSpacing: '-0.5px',
      }}>
        {pnl == null ? '—' : `${pnl >= 0 ? '+' : ''}$${Math.abs(pnl).toFixed(2)}`}
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        paddingTop: 10, borderTop: `1px solid ${BORDER}`,
        fontSize: '0.68rem', fontFamily: 'JetBrains Mono',
      }}>
        <span style={{ color: DIM }}>Win Rate</span>
        <span style={{ color: winRate != null && winRate > 50 ? GREEN : SEC }}>
          {winRate != null ? `${winRate.toFixed(1)}%` : '—'}
        </span>
      </div>
    </button>
  )
}

function PillarCard({
  icon: Icon, title, body, accent,
}: { icon: React.ElementType; title: string; body: string; accent: string }) {
  return (
    <div style={{
      background: CARD,
      border: `1px solid ${BORDER}`,
      borderRadius: 12,
      padding: '22px 22px',
      backdropFilter: 'blur(6px)',
      flex: 1, minWidth: 0,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: `${accent}12`, border: `1px solid ${accent}20`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 14,
      }}>
        <Icon size={16} color={accent} />
      </div>
      <div style={{ fontSize: '0.84rem', fontWeight: 700, color: TEXT, marginBottom: 8 }}>
        {title}
      </div>
      <div style={{ fontSize: '0.74rem', color: SEC, lineHeight: 1.65 }}>
        {body}
      </div>
    </div>
  )
}

export function HomePage() {
  const navigate = useNavigate()
  const heroVisible = useEntrance(100)

  const { data: status } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then(r => r.data),
    refetchInterval: 10000, retry: false,
  })
  const { data: scalperState } = useQuery({
    queryKey: ['terminal-state'],
    queryFn: () => terminalService.getState().then(r => r.data),
    refetchInterval: 10000, retry: false,
  })
  const { data: patternState } = useQuery({
    queryKey: ['pattern-state-live'],
    queryFn: () => patternService.getState('live').then(r => r.data),
    refetchInterval: 10000, retry: false,
  })
  const { data: marketData } = useQuery({
    queryKey: ['market-quotes'],
    queryFn: () => marketService.getQuotes().then(r => r.data),
    refetchInterval: 60000, staleTime: 55000, retry: false,
  })

  const backendOnline = !!(status?.loop_running || status?.trader_running || status?.grok_running)
  const acctVal = scalperState?.account_details?.liquidation_value
  const scalperPnl = scalperState?.daily_pnl
  const patternPnl = patternState?.daily_pnl
  const totalPnl = (scalperPnl ?? 0) + (patternPnl ?? 0)
  const movers: QuoteItem[] = [...(marketData?.top ?? []), ...(marketData?.bottom ?? [])].slice(0, 6)

  return (
    <div style={{
      position: 'relative', minHeight: '100%',
      background: '#06060b',
    }}>
      <GridBackground />

      <div style={{
        position: 'relative', zIndex: 1,
        maxWidth: 1100, margin: '0 auto',
        padding: '60px 32px 80px',
        display: 'flex', flexDirection: 'column', gap: 64,
      }}>

        {/* ── Hero ── */}
        <div style={{ textAlign: 'center' }}>
          <div style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? 'translateY(0)' : 'translateY(28px)',
            transition: 'opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1)',
          }}>
            <div style={{
              display: 'inline-block',
              fontSize: '0.6rem', letterSpacing: '0.5em',
              textTransform: 'uppercase', color: ACCENT,
              background: 'rgba(200,255,0,0.06)', border: '1px solid rgba(200,255,0,0.15)',
              borderRadius: 20, padding: '4px 16px', marginBottom: 28,
            }}>
              Algorithmic Trading Infrastructure
            </div>
            <h1 style={{
              margin: '0 0 20px',
              fontSize: 'clamp(2.6rem, 6vw, 4.2rem)',
              fontWeight: 900,
              color: TEXT,
              letterSpacing: '-0.04em',
              lineHeight: 1.08,
            }}>
              The Fund Starts<br />
              <span style={{
                background: `linear-gradient(135deg, ${ACCENT} 0%, #86efac 100%)`,
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}>
                Here.
              </span>
            </h1>
            <p style={{
              margin: '0 auto 36px',
              maxWidth: 520,
              fontSize: '1.05rem', color: SEC, lineHeight: 1.7, fontWeight: 400,
            }}>
              We are building a quantitative hedge fund from first principles —
              live execution, AI-assisted risk, and systematic edge.
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => navigate('/scalper')}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '12px 26px', borderRadius: 8,
                  background: ACCENT, border: 'none', cursor: 'pointer',
                  color: '#06060b', fontWeight: 700, fontSize: '0.84rem',
                  fontFamily: 'Inter, sans-serif', letterSpacing: '0.01em',
                  transition: 'opacity 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.opacity = '0.88' }}
                onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
              >
                Open Terminal <ArrowRight size={14} />
              </button>
              <button
                onClick={() => navigate('/analytics')}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '12px 26px', borderRadius: 8,
                  background: 'transparent',
                  border: `1px solid ${BORDER}`, cursor: 'pointer',
                  color: SEC, fontWeight: 500, fontSize: '0.84rem',
                  fontFamily: 'Inter, sans-serif',
                  transition: 'color 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = TEXT
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = SEC
                  e.currentTarget.style.borderColor = BORDER
                }}
              >
                View Analytics
              </button>
            </div>
          </div>
        </div>

        {/* ── Live stats strip ── */}
        <AnimBlock delay={200}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
            <StatPill
              label="Account Value"
              value={acctVal
                ? `$${acctVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—'}
            />
            <StatPill
              label="Day P&L"
              value={`${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}`}
              color={totalPnl >= 0 ? GREEN : RED}
            />
            <StatPill
              label="Win Rate"
              value={scalperState?.win_rate != null ? `${scalperState.win_rate.toFixed(1)}%` : '—'}
              color={(scalperState?.win_rate ?? 0) > 50 ? GREEN : SEC}
            />
            <StatPill
              label="System"
              value={backendOnline ? 'Online' : 'Offline'}
              color={backendOnline ? GREEN : RED}
            />
          </div>
        </AnimBlock>

        {/* ── Live strategies ── */}
        <AnimBlock delay={320}>
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: '0.56rem', color: DIM, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 4 }}>
              Live Strategies
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: TEXT }}>
              Active Modules
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <StrategyLiveCard
              accent={GREEN} icon={Activity} label="SCALPER" tag="LIVE"
              running={!!status?.trader_running}
              pnl={scalperPnl} winRate={scalperState?.win_rate}
              to="/scalper"
            />
            <StrategyLiveCard
              accent="#a78bfa" icon={BarChart2} label="PATTERN" tag="LIVE"
              running={!!status?.loop_running}
              pnl={patternPnl} winRate={patternState?.win_rate}
              to="/pattern"
            />
            <StrategyLiveCard
              accent="#22d3ee" icon={Radio} label="SIGNALS" tag="LIVE"
              running={!!status?.grok_running}
              pnl={undefined} winRate={undefined}
              to="/signals"
            />
          </div>
        </AnimBlock>

        {/* ── Mission pillars ── */}
        <AnimBlock delay={440}>
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: '0.56rem', color: DIM, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 4 }}>
              Our Mission
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: TEXT }}>
              Why We're Building This
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <PillarCard
              icon={Zap} accent={ACCENT} title="Systematic Edge"
              body="Every trade is defined by rules, not emotion. We use backtested signals, Kelly sizing, and real-time tape confirmation to enter only when the odds are in our favor."
            />
            <PillarCard
              icon={Brain} accent="#a78bfa" title="AI-Assisted Risk"
              body="Claude consults on every time-stopped trade, helping us decide whether to hold, take partial profits, or exit — removing the bias from in-the-moment decisions."
            />
            <PillarCard
              icon={Shield} accent="#22d3ee" title="Institutional Infrastructure"
              body="Live order execution, real-time P&L tracking, pattern detection, Telegram signal feeds, and a growing suite of quantitative tools — built to scale into a fund."
            />
          </div>
        </AnimBlock>

        {/* ── Market snapshot ── */}
        {movers.length > 0 && (
          <AnimBlock delay={560}>
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: '0.56rem', color: DIM, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 4 }}>
                Market Snapshot
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: TEXT }}>
                Today's Movers
              </div>
            </div>
            <div style={{
              background: CARD,
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              overflow: 'hidden',
              backdropFilter: 'blur(6px)',
            }}>
              {movers.map((q: QuoteItem, i) => {
                const pos = q.change_pct >= 0
                const Icon = pos ? TrendingUp : TrendingDown
                return (
                  <div key={q.symbol} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 22px',
                    borderBottom: i < movers.length - 1 ? `1px solid ${BORDER}` : 'none',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Icon size={12} color={pos ? GREEN : RED} />
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem', fontWeight: 700, color: TEXT, minWidth: 55 }}>
                        {q.symbol}
                      </span>
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', color: SEC }}>
                        ${q.price?.toFixed(2)}
                      </span>
                    </div>
                    <span style={{
                      fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', fontWeight: 600,
                      color: pos ? GREEN : RED,
                      background: pos ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)',
                      padding: '3px 10px', borderRadius: 5,
                    }}>
                      {pos ? '+' : ''}{q.change_pct.toFixed(2)}%
                    </span>
                  </div>
                )
              })}
            </div>
          </AnimBlock>
        )}

        {/* ── Footer line ── */}
        <AnimBlock delay={640}>
          <div style={{
            borderTop: `1px solid ${BORDER}`,
            paddingTop: 28,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            flexWrap: 'wrap', gap: 10,
          }}>
            <span style={{ fontSize: '0.72rem', color: DIM }}>
              TNFund — Algorithmic Trading Infrastructure
            </span>
            <span style={{ fontSize: '0.68rem', color: DIM }}>
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </span>
          </div>
        </AnimBlock>
      </div>

      <style>{`
        @keyframes botPulseCore {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.7; transform: scale(0.8); }
        }
        @keyframes botPulseRing {
          0%   { transform: scale(0.6); opacity: 0.5; }
          100% { transform: scale(2.5); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
