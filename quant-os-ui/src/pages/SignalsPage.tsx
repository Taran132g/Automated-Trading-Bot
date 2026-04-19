import { useEffect, useRef, useState } from 'react'
import { Activity, TrendingUp, TrendingDown, Zap, Radio, AlertTriangle } from 'lucide-react'

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

const LONG_COLOR = '#00FF99'
const SHORT_COLOR = '#FF4466'
const DIM = '#64748B'
const BG = '#0B0E14'
const CARD_BG = '#0D1117'
const BORDER = '#1F2937'

function formatTime(iso: string) {
  try {
    return new Date(iso + 'Z').toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch {
    return iso
  }
}

function formatDate(iso: string) {
  try {
    return new Date(iso + 'Z').toLocaleDateString('en-US', {
      month: 'short', day: 'numeric',
    })
  } catch {
    return ''
  }
}

function ChannelBadge({ name }: { name: string }) {
  // Shorten long channel names
  const short = name.length > 28 ? name.slice(0, 26) + '…' : name
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'rgba(0,255,153,0.07)', border: '1px solid rgba(0,255,153,0.2)',
      borderRadius: 4, padding: '2px 8px',
      fontFamily: 'Roboto Mono', fontSize: '0.68rem',
      color: LONG_COLOR, letterSpacing: 0.5,
    }}>
      <Radio size={9} />
      {short}
    </span>
  )
}

function RRBadge({ rr }: { rr: number }) {
  const color = rr >= 2 ? LONG_COLOR : rr >= 1 ? '#F59E0B' : SHORT_COLOR
  return (
    <span style={{
      background: `${color}18`, border: `1px solid ${color}44`,
      borderRadius: 3, padding: '1px 6px',
      fontFamily: 'Roboto Mono', fontSize: '0.68rem', color,
    }}>
      1:{rr}
    </span>
  )
}

function SignalCard({ signal, isNew }: { signal: Signal; isNew: boolean }) {
  const isLong = signal.side === 'long'
  const accent = isLong ? LONG_COLOR : SHORT_COLOR
  const Icon = isLong ? TrendingUp : TrendingDown

  // Extract Claude's Take from trade_card text
  const takeMatch = signal.trade_card.match(/Claude's Take[^\n]*\n([\s\S]*?)(?=\n\*|$)/i)
  const claudeTake = takeMatch
    ? takeMatch[1].replace(/\*/g, '').replace(/_/g, '').trim()
    : ''

  const [visible, setVisible] = useState(false)
  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-40px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.45s cubic-bezier(0.22,1,0.36,1), opacity 0.35s ease',
      marginBottom: 16,
    }}>
      <div style={{
        background: CARD_BG,
        border: `1px solid ${isNew ? accent + '55' : BORDER}`,
        borderLeft: `3px solid ${accent}`,
        borderRadius: 10,
        overflow: 'hidden',
        boxShadow: isNew ? `0 0 24px ${accent}18` : 'none',
        transition: 'box-shadow 2s ease, border-color 2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 16px', borderBottom: `1px solid ${BORDER}`,
          background: `${accent}08`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon size={16} color={accent} />
            <span style={{
              fontFamily: 'Roboto Mono', fontWeight: 700, fontSize: '1rem',
              color: accent, letterSpacing: 1,
            }}>
              {signal.symbol}
            </span>
            <span style={{
              background: `${accent}22`, border: `1px solid ${accent}55`,
              borderRadius: 4, padding: '1px 8px',
              fontFamily: 'Roboto Mono', fontSize: '0.7rem',
              color: accent, fontWeight: 700, letterSpacing: 1,
            }}>
              {signal.side.toUpperCase()}
            </span>
            {signal.approved ? null : (
              <span style={{
                background: '#FF446618', border: '1px solid #FF446644',
                borderRadius: 4, padding: '1px 8px',
                fontFamily: 'Roboto Mono', fontSize: '0.68rem', color: SHORT_COLOR,
              }}>
                SKIPPED
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ChannelBadge name={signal.channel} />
            <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.68rem', color: DIM }}>
              {formatDate(signal.created_at)} {formatTime(signal.created_at)}
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 0 }}>
          {/* Entry / SL / TP */}
          <div style={{ padding: '12px 16px', borderRight: `1px solid ${BORDER}` }}>
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.65rem', color: DIM, marginBottom: 8, letterSpacing: 1 }}>
              PRICE LEVELS
            </div>
            <Row label="Entry" value={`$${signal.entry.toLocaleString()}`} color="#E2E8F0" />
            <Row label="Stop Loss" value={`$${signal.sl.toLocaleString()}`} color={SHORT_COLOR}
              sub={`${signal.sl_distance_pct}% away`} />
            {signal.tp_levels.map((tp, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: DIM }}>TP{i + 1}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: LONG_COLOR }}>
                    ${tp.toLocaleString()}
                  </span>
                  {signal.rr_ratios[i] !== undefined && <RRBadge rr={signal.rr_ratios[i]} />}
                </div>
              </div>
            ))}
            {signal.tp_levels.length === 0 && (
              <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: DIM }}>No TP given</span>
            )}
          </div>

          {/* Your Order */}
          <div style={{ padding: '12px 16px', borderRight: `1px solid ${BORDER}` }}>
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.65rem', color: DIM, marginBottom: 8, letterSpacing: 1 }}>
              YOUR ORDER (YUBIT)
            </div>
            <Row label="Qty" value={`${signal.quantity} coins`} color="#E2E8F0" highlight />
            <Row label="Position" value={`$${signal.position_size_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color="#E2E8F0" />
            <Row label="Leverage" value={`${signal.leverage}x`} color={accent} />
            <Row label="Margin" value={`$${signal.margin_required_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} color="#E2E8F0" />
            <Row
              label="Risk"
              value={`$${signal.risk_amount_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              color={SHORT_COLOR}
              sub={`${signal.risk_pct}% of $${signal.balance_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            />
          </div>

          {/* Claude's Take */}
          <div style={{ padding: '12px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Zap size={11} color="#A855F7" />
              <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.65rem', color: '#A855F7', letterSpacing: 1 }}>
                CLAUDE'S TAKE
              </span>
            </div>
            {claudeTake ? (
              <p style={{
                fontFamily: 'Roboto Mono', fontSize: '0.7rem', color: '#94A3B8',
                lineHeight: 1.6, margin: 0,
              }}>
                {claudeTake}
              </p>
            ) : (
              <p style={{ fontFamily: 'Roboto Mono', fontSize: '0.7rem', color: DIM, margin: 0 }}>
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
        <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.7rem', color: DIM }}>{label}</span>
        <span style={{
          fontFamily: 'Roboto Mono', fontSize: highlight ? '0.85rem' : '0.75rem',
          color, fontWeight: highlight ? 700 : 400,
        }}>
          {value}
        </span>
      </div>
      {sub && (
        <div style={{ textAlign: 'right', fontFamily: 'Roboto Mono', fontSize: '0.62rem', color: DIM }}>
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
      background: on ? LONG_COLOR : 'transparent',
      border: `1px solid ${LONG_COLOR}`,
      transition: 'background 0.3s',
      marginRight: 6,
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
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 3000)
      }
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
          // Clear "new" highlight after 8s
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
    <div style={{ minHeight: '100vh', background: BG, color: '#E2E8F0' }}>
      {/* ── Header ── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 10,
        background: 'rgba(11,14,20,0.92)',
        backdropFilter: 'blur(12px)',
        borderBottom: `1px solid ${BORDER}`,
        padding: '0 28px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 56,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Activity size={18} color={LONG_COLOR} />
          <span style={{
            fontFamily: 'Roboto Mono', fontWeight: 700, fontSize: '0.9rem',
            color: LONG_COLOR, letterSpacing: 2,
          }}>
            SIGNAL ADVISOR
          </span>
          <span style={{ width: 1, height: 18, background: BORDER, display: 'inline-block' }} />
          <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: DIM }}>
            Personal Trade Feed
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          {lastUpdate && (
            <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.68rem', color: DIM }}>
              Updated {lastUpdate}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <LiveDot />
            <span style={{
              fontFamily: 'Roboto Mono', fontSize: '0.72rem',
              color: connected ? LONG_COLOR : SHORT_COLOR,
            }}>
              {connected ? 'LIVE' : 'RECONNECTING'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Stats bar ── */}
      <div style={{
        display: 'flex', gap: 0,
        borderBottom: `1px solid ${BORDER}`,
        background: CARD_BG,
      }}>
        {[
          { label: 'Total Signals', value: signals.length },
          { label: 'Approved', value: signals.filter(s => s.approved).length },
          { label: 'Skipped', value: signals.filter(s => !s.approved).length },
          { label: 'Channels', value: new Set(signals.map(s => s.channel)).size },
        ].map((stat, i) => (
          <div key={i} style={{
            flex: 1, padding: '10px 20px',
            borderRight: i < 3 ? `1px solid ${BORDER}` : 'none',
          }}>
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.62rem', color: DIM, letterSpacing: 1 }}>
              {stat.label.toUpperCase()}
            </div>
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '1.1rem', fontWeight: 700, color: '#E2E8F0' }}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Feed ── */}
      <div style={{ padding: '20px 28px', maxWidth: 1300, margin: '0 auto' }}>
        {signals.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: 16, paddingTop: 120,
          }}>
            <Radio size={40} color={DIM} />
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.85rem', color: DIM }}>
              Listening for signals…
            </div>
            <div style={{ fontFamily: 'Roboto Mono', fontSize: '0.72rem', color: '#374151' }}>
              Trade cards will appear here as your channels post them
            </div>
          </div>
        ) : (
          signals.map(signal => (
            <SignalCard
              key={signal.id}
              signal={signal}
              isNew={newIds.has(signal.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}
