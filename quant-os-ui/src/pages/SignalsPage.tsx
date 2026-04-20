import { useEffect, useRef, useState } from 'react'
import { Activity, TrendingUp, TrendingDown, Zap, Radio } from 'lucide-react'

interface Signal {
  id: number
  created_at: string
  channel: string
  symbol: string
  side: string
  entry: number
  sl: number
  sl_distance_pct: number
  tp_levels: number[]
  rr_ratios: number[]
  leverage: number
  quantity: number
  position_size_usdt: number
  margin_required_usdt: number
  risk_amount_usdt: number
  risk_pct: number
  balance_usdt: number
  trade_card: string
  approved: number
}

const GREEN = '#22c55e'
const RED = '#ef4444'
const ACCENT = '#c8ff00'
const DIM = '#55556a'
const BG = '#06060b'
const CARD = '#0c0c14'
const BORDER = 'rgba(255,255,255,0.06)'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const FAINT = '#33334a'

function formatTime(iso: string) {
  try {
    return new Date(iso + 'Z').toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch { return iso }
}

function formatDate(iso: string) {
  try {
    return new Date(iso + 'Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch { return '' }
}

function ChannelBadge({ name }: { name: string }) {
  const short = name.length > 28 ? name.slice(0, 26) + '\u2026' : name
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'rgba(200,255,0,0.04)', border: '1px solid rgba(200,255,0,0.12)',
      borderRadius: 4, padding: '2px 8px',
      fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem',
      color: ACCENT, letterSpacing: 0.5,
    }}>
      <Radio size={9} />
      {short}
    </span>
  )
}

function RRBadge({ rr }: { rr: number }) {
  const color = rr >= 2 ? GREEN : rr >= 1 ? '#f59e0b' : RED
  return (
    <span style={{
      background: `${color}12`, border: `1px solid ${color}30`,
      borderRadius: 3, padding: '1px 6px',
      fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color,
    }}>
      1:{rr}
    </span>
  )
}

function SignalCard({ signal, isNew }: { signal: Signal; isNew: boolean }) {
  const isLong = signal.side === 'long'
  const accent = isLong ? GREEN : RED
  const Icon = isLong ? TrendingUp : TrendingDown

  const takeMatch = signal.trade_card.match(/Claude's Take[^\n]*\n([\s\S]*?)(?=\n\*|$)/i)
  const claudeTake = takeMatch ? takeMatch[1].replace(/\*/g, '').replace(/_/g, '').trim() : ''

  const [visible, setVisible] = useState(false)
  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-40px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.45s cubic-bezier(0.22,1,0.36,1), opacity 0.35s ease',
      marginBottom: 16,
    }}>
      <div style={{
        background: CARD,
        border: `1px solid ${isNew ? accent + '40' : BORDER}`,
        borderLeft: `3px solid ${accent}`,
        borderRadius: 12, overflow: 'hidden',
        boxShadow: isNew ? `0 0 30px ${accent}10` : 'none',
        transition: 'box-shadow 2s ease, border-color 2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 18px', borderBottom: `1px solid ${BORDER}`,
          background: `${accent}04`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon size={16} color={accent} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: '1rem', color: accent, letterSpacing: 1 }}>
              {signal.symbol}
            </span>
            <span style={{
              background: `${accent}12`, border: `1px solid ${accent}40`,
              borderRadius: 4, padding: '1px 8px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem',
              color: accent, fontWeight: 700, letterSpacing: 1,
            }}>
              {signal.side.toUpperCase()}
            </span>
            {signal.approved ? null : (
              <span style={{
                background: `${RED}10`, border: `1px solid ${RED}30`,
                borderRadius: 4, padding: '1px 8px',
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: RED,
              }}>
                SKIPPED
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ChannelBadge name={signal.channel} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: DIM }}>
              {formatDate(signal.created_at)} {formatTime(signal.created_at)}
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 0 }}>
          <div style={{ padding: '14px 18px', borderRight: `1px solid ${BORDER}` }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM, marginBottom: 8, letterSpacing: 1 }}>
              PRICE LEVELS
            </div>
            <Row label="Entry" value={`$${signal.entry.toLocaleString()}`} color={TEXT} />
            <Row label="Stop Loss" value={`$${signal.sl.toLocaleString()}`} color={RED} sub={`${signal.sl_distance_pct}% away`} />
            {signal.tp_levels.map((tp, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>TP{i + 1}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: GREEN }}>
                    ${tp.toLocaleString()}
                  </span>
                  {signal.rr_ratios[i] !== undefined && <RRBadge rr={signal.rr_ratios[i]} />}
                </div>
              </div>
            ))}
            {signal.tp_levels.length === 0 && (
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>No TP given</span>
            )}
          </div>

          <div style={{ padding: '14px 18px', borderRight: `1px solid ${BORDER}` }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM, marginBottom: 8, letterSpacing: 1 }}>
              YOUR ORDER (YUBIT)
            </div>
            <Row label="Qty" value={`${signal.quantity} coins`} color={TEXT} highlight />
            <Row label="Position" value={`$${signal.position_size_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color={TEXT} />
            <Row label="Leverage" value={`${signal.leverage}x`} color={accent} />
            <Row label="Margin" value={`$${signal.margin_required_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color={TEXT} />
            <Row label="Risk" value={`$${signal.risk_amount_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color={RED}
              sub={`${signal.risk_pct}% of $${signal.balance_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
          </div>

          <div style={{ padding: '14px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Zap size={11} color="#a78bfa" />
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: '#a78bfa', letterSpacing: 1 }}>
                CLAUDE'S TAKE
              </span>
            </div>
            {claudeTake ? (
              <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: SEC, lineHeight: 1.6, margin: 0 }}>
                {claudeTake}
              </p>
            ) : (
              <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM, margin: 0 }}>
                {signal.trade_card.replace(/\*/g, '').replace(/_/g, '').slice(0, 300)}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, color, sub, highlight }: {
  label: string; value: string; color: string; sub?: string; highlight?: boolean
}) {
  return (
    <div style={{ marginBottom: 5 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM }}>{label}</span>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace', fontSize: highlight ? '0.85rem' : '0.75rem',
          color, fontWeight: highlight ? 700 : 400,
        }}>
          {value}
        </span>
      </div>
      {sub && (
        <div style={{ textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function LiveDot() {
  const [on, setOn] = useState(true)
  useEffect(() => {
    const t = setInterval(() => setOn(v => !v), 900)
    return () => clearInterval(t)
  }, [])
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: on ? ACCENT : 'transparent',
      border: `1px solid ${ACCENT}`,
      transition: 'background 0.3s', marginRight: 6,
    }} />
  )
}

export function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [newIds, setNewIds] = useState<Set<number>>(new Set())
  const [connected, setConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/api/signals/ws`

    function connect() {
      const ws = new WebSocket(url)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => { setConnected(false); setTimeout(connect, 3000) }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        setLastUpdate(new Date().toLocaleTimeString())
        if (msg.type === 'init') {
          setSignals(msg.signals)
        } else if (msg.type === 'new_signals' && msg.signals.length > 0) {
          const incoming: Signal[] = msg.signals
          const ids = new Set(incoming.map((s: Signal) => s.id))
          setNewIds(prev => new Set([...prev, ...ids]))
          setSignals(prev => [...incoming, ...prev])
          setTimeout(() => setNewIds(prev => {
            const next = new Set(prev)
            ids.forEach(id => next.delete(id))
            return next
          }), 8000)
        }
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: BG, color: TEXT }}>
      {/* Header */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 10,
        background: 'rgba(6,6,11,0.92)',
        backdropFilter: 'blur(16px)',
        borderBottom: `1px solid ${BORDER}`,
        padding: '0 28px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 56,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Activity size={18} color={ACCENT} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: '0.9rem', color: ACCENT, letterSpacing: 2 }}>
            SIGNAL ADVISOR
          </span>
          <span style={{ width: 1, height: 18, background: BORDER, display: 'inline-block' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>
            Personal Trade Feed
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          {lastUpdate && (
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: DIM }}>
              Updated {lastUpdate}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <LiveDot />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: connected ? ACCENT : RED }}>
              {connected ? 'LIVE' : 'RECONNECTING'}
            </span>
          </div>
        </div>
      </div>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: 0, borderBottom: `1px solid ${BORDER}`, background: '#0a0a12' }}>
        {[
          { label: 'Total Signals', value: signals.length },
          { label: 'Approved', value: signals.filter(s => s.approved).length },
          { label: 'Skipped', value: signals.filter(s => !s.approved).length },
          { label: 'Channels', value: new Set(signals.map(s => s.channel)).size },
        ].map((stat, i) => (
          <div key={i} style={{
            flex: 1, padding: '12px 22px',
            borderRight: i < 3 ? `1px solid ${BORDER}` : 'none',
          }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem', color: DIM, letterSpacing: 1 }}>
              {stat.label.toUpperCase()}
            </div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.1rem', fontWeight: 700, color: TEXT }}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Feed */}
      <div style={{ padding: '24px 28px', maxWidth: 1300, margin: '0 auto' }}>
        {signals.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, paddingTop: 120 }}>
            <Radio size={40} color={FAINT} />
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem', color: DIM }}>
              Listening for signals...
            </div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: FAINT }}>
              Trade cards will appear here as your channels post them
            </div>
          </div>
        ) : (
          signals.map(signal => (
            <SignalCard key={signal.id} signal={signal} isNew={newIds.has(signal.id)} />
          ))
        )}
      </div>
    </div>
  )
}
