import { useEffect, useRef, useState } from 'react'
import { Activity, Radio } from 'lucide-react'

interface Signal {
  id: number
  created_at: string
  channel: string
  raw_text: string | null
  image_path: string | null
  entry: number | null
  sl: number | null
  sl_distance_pct: number | null
  tp_levels: number[]
  quantity: number | null
  position_size_usdt: number | null
  risk_amount_usdt: number | null
  risk_pct: number | null
  balance_usdt: number | null
  has_sizing: number
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
  const short = name.length > 30 ? name.slice(0, 28) + '\u2026' : name
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

function SignalCard({ signal, isNew }: { signal: Signal; isNew: boolean }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])

  const hasSizing = signal.has_sizing === 1 && signal.entry != null && signal.sl != null

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-40px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.45s cubic-bezier(0.22,1,0.36,1), opacity 0.35s ease',
      marginBottom: 16,
    }}>
      <div style={{
        background: CARD,
        border: `1px solid ${isNew ? ACCENT + '40' : BORDER}`,
        borderLeft: `3px solid ${ACCENT}`,
        borderRadius: 12, overflow: 'hidden',
        boxShadow: isNew ? `0 0 30px ${ACCENT}10` : 'none',
        transition: 'box-shadow 2s ease, border-color 2s ease',
      }}>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 18px', borderBottom: `1px solid ${BORDER}`,
          background: 'rgba(200,255,0,0.02)',
        }}>
          <ChannelBadge name={signal.channel} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: DIM }}>
            {formatDate(signal.created_at)} {formatTime(signal.created_at)}
          </span>
        </div>

        {/* Raw message body */}
        {signal.raw_text ? (
          <div style={{ padding: '16px 18px', borderBottom: signal.image_path || hasSizing ? `1px solid ${BORDER}` : 'none' }}>
            <pre style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem',
              color: TEXT, lineHeight: 1.7, margin: 0,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {signal.raw_text}
            </pre>
          </div>
        ) : null}

        {/* Chart image */}
        {signal.image_path ? (
          <div style={{ padding: '14px 18px', borderBottom: hasSizing ? `1px solid ${BORDER}` : 'none' }}>
            <img
              src={`/api/signals/image/${signal.image_path}`}
              alt="Signal chart"
              style={{
                maxWidth: '100%', maxHeight: 400,
                borderRadius: 8, display: 'block',
                border: `1px solid ${BORDER}`,
              }}
            />
          </div>
        ) : null}

        {/* Bet sizing block */}
        {hasSizing ? (
          <div style={{ padding: '14px 18px', background: 'rgba(200,255,0,0.015)' }}>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem',
              color: ACCENT, letterSpacing: 1, marginBottom: 10,
            }}>
              YOUR BET (YUBIT) — $200 RISK
            </div>
            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
              <SizingItem label="Entry" value={`$${signal.entry!.toLocaleString()}`} color={TEXT} />
              <SizingItem
                label="Stop Loss"
                value={`$${signal.sl!.toLocaleString()}`}
                color={RED}
                sub={`${signal.sl_distance_pct}% away`}
              />
              <SizingItem
                label="Quantity"
                value={`${signal.quantity} coins`}
                color={ACCENT}
                large
              />
              <SizingItem
                label="Position Size"
                value={`$${signal.position_size_usdt!.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                color={TEXT}
              />
              <SizingItem
                label="Risk"
                value={`$${signal.risk_amount_usdt!.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                color={RED}
                sub={`${signal.risk_pct}% of $${signal.balance_usdt!.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              />
              {signal.tp_levels.length > 0 && (
                <div>
                  <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM, marginBottom: 3 }}>
                    TAKE PROFITS
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {signal.tp_levels.map((tp, i) => (
                      <span key={i} style={{
                        fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem',
                        color: GREEN,
                        background: `${GREEN}10`, border: `1px solid ${GREEN}30`,
                        borderRadius: 4, padding: '1px 7px',
                      }}>
                        TP{i + 1}: ${tp.toLocaleString()}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function SizingItem({ label, value, color, sub, large }: {
  label: string; value: string; color: string; sub?: string; large?: boolean
}) {
  return (
    <div>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: large ? '1rem' : '0.82rem',
        fontWeight: large ? 700 : 400,
        color,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM, marginTop: 1 }}>
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

  const withSizing = signals.filter(s => s.has_sizing === 1).length

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
            SIGNAL FEED
          </span>
          <span style={{ width: 1, height: 18, background: BORDER, display: 'inline-block' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>
            Live Channel Monitor
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
          { label: 'With Sizing', value: withSizing },
          { label: 'Image Only', value: signals.filter(s => s.image_path && !s.has_sizing).length },
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
      <div style={{ padding: '24px 28px', maxWidth: 900, margin: '0 auto' }}>
        {signals.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, paddingTop: 120 }}>
            <Radio size={40} color={FAINT} />
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem', color: DIM }}>
              Listening for signals...
            </div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: FAINT }}>
              Messages from your channels will appear here
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
