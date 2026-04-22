import { useEffect, useRef, useState } from 'react'
import { Activity, Radio, TrendingUp, Bell } from 'lucide-react'

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
const FAINT = '#33334a'
const ORANGE = '#f59e0b'

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

function ChannelBadge({ name, color }: { name: string; color: string }) {
  const short = name.length > 30 ? name.slice(0, 28) + '\u2026' : name
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: `${color}08`, border: `1px solid ${color}20`,
      borderRadius: 4, padding: '2px 8px',
      fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem',
      color, letterSpacing: 0.5,
    }}>
      <Radio size={9} />
      {short}
    </span>
  )
}

function TradeCard({ signal, isNew }: { signal: Signal; isNew: boolean }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-30px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.4s cubic-bezier(0.22,1,0.36,1), opacity 0.3s ease',
      marginBottom: 16,
    }}>
      <div style={{
        background: CARD,
        border: `1px solid ${isNew ? GREEN + '50' : BORDER}`,
        borderLeft: `3px solid ${GREEN}`,
        borderRadius: 12, overflow: 'hidden',
        boxShadow: isNew ? `0 0 40px ${GREEN}12` : 'none',
        transition: 'box-shadow 2s ease, border-color 2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 18px', borderBottom: `1px solid ${BORDER}`,
          background: `${GREEN}04`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <TrendingUp size={14} color={GREEN} />
            <ChannelBadge name={signal.channel} color={GREEN} />
            <span style={{
              background: `${GREEN}15`, border: `1px solid ${GREEN}40`,
              borderRadius: 4, padding: '1px 8px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem',
              color: GREEN, fontWeight: 700, letterSpacing: 1,
            }}>
              BUY SIGNAL
            </span>
          </div>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: DIM }}>
            {formatDate(signal.created_at)} {formatTime(signal.created_at)}
          </span>
        </div>

        {/* Two-column: message + chart */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: signal.image_path ? '1fr 1fr' : '1fr',
          gap: 0,
        }}>
          {/* Raw message */}
          {signal.raw_text ? (
            <div style={{
              padding: '16px 18px',
              borderRight: signal.image_path ? `1px solid ${BORDER}` : 'none',
            }}>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem',
                color: DIM, letterSpacing: 1, marginBottom: 8,
              }}>
                SIGNAL MESSAGE
              </div>
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
            <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column' }}>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem',
                color: DIM, letterSpacing: 1, marginBottom: 8,
              }}>
                CHART
              </div>
              <img
                src={`/api/signals/image/${signal.image_path}`}
                alt="Signal chart"
                style={{
                  width: '100%', maxHeight: 320, objectFit: 'contain',
                  borderRadius: 8, display: 'block',
                  border: `1px solid ${BORDER}`,
                  background: '#08080f',
                }}
              />
            </div>
          ) : null}
        </div>

        {/* Bet sizing strip */}
        <div style={{
          padding: '12px 18px',
          borderTop: `1px solid ${BORDER}`,
          background: `${GREEN}06`,
          display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'flex-start',
        }}>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem',
            color: GREEN, letterSpacing: 1, alignSelf: 'center', minWidth: 80,
          }}>
            YOUR BET<br />$200 RISK
          </div>
          <SizingItem label="Entry" value={`$${signal.entry!.toLocaleString()}`} color={TEXT} />
          <SizingItem
            label="Stop Loss"
            value={`$${signal.sl!.toLocaleString()}`}
            color={RED}
            sub={`${signal.sl_distance_pct}% away`}
          />
          <SizingItem label="Quantity" value={`${signal.quantity} coins`} color={ACCENT} large />
          <SizingItem
            label="Position"
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
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem', color: DIM, marginBottom: 4 }}>
                TAKE PROFITS
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {signal.tp_levels.map((tp, i) => (
                  <span key={i} style={{
                    fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem',
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
    </div>
  )
}

function AlertCard({ signal, isNew }: { signal: Signal; isNew: boolean }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-20px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.35s ease, opacity 0.25s ease',
      marginBottom: 10,
    }}>
      <div style={{
        background: CARD,
        border: `1px solid ${isNew ? ORANGE + '40' : BORDER}`,
        borderLeft: `3px solid ${FAINT}`,
        borderRadius: 8, overflow: 'hidden',
        transition: 'border-color 2s ease',
      }}>
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 12,
          padding: '11px 16px',
        }}>
          <Bell size={12} color={DIM} style={{ marginTop: 3, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <ChannelBadge name={signal.channel} color={DIM} />
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: FAINT }}>
                {formatDate(signal.created_at)} {formatTime(signal.created_at)}
              </span>
            </div>
            {signal.raw_text ? (
              <pre style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.74rem',
                color: '#9090a8', lineHeight: 1.65, margin: 0,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {signal.raw_text}
              </pre>
            ) : null}
            {signal.image_path ? (
              <img
                src={`/api/signals/image/${signal.image_path}`}
                alt="Alert image"
                style={{
                  maxWidth: '100%', maxHeight: 240, objectFit: 'contain',
                  borderRadius: 6, display: 'block', marginTop: signal.raw_text ? 10 : 0,
                  border: `1px solid ${BORDER}`,
                }}
              />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function SizingItem({ label, value, color, sub, large }: {
  label: string; value: string; color: string; sub?: string; large?: boolean
}) {
  return (
    <div>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem', color: DIM, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: large ? '0.95rem' : '0.8rem',
        fontWeight: large ? 700 : 400,
        color,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem', color: DIM, marginTop: 1 }}>
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

  const tradeSignals = signals.filter(s => s.has_sizing === 1)
  const alerts = signals.filter(s => s.has_sizing === 0)

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

      {/* Two-column layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 380px',
        gap: 0,
        minHeight: 'calc(100vh - 56px)',
      }}>

        {/* Left — Trade Signals */}
        <div style={{ borderRight: `1px solid ${BORDER}`, minHeight: '100%' }}>
          {/* Section header */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '14px 24px',
            borderBottom: `1px solid ${BORDER}`,
            background: `${GREEN}04`,
            position: 'sticky', top: 56, zIndex: 5,
          }}>
            <TrendingUp size={13} color={GREEN} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: GREEN, fontWeight: 700, letterSpacing: 1 }}>
              BUY ORDERS
            </span>
            <span style={{
              marginLeft: 4,
              background: `${GREEN}15`, border: `1px solid ${GREEN}30`,
              borderRadius: 10, padding: '0 7px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: GREEN,
            }}>
              {tradeSignals.length}
            </span>
          </div>

          <div style={{ padding: '20px 24px' }}>
            {tradeSignals.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 80, gap: 12 }}>
                <TrendingUp size={32} color={FAINT} />
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', color: DIM }}>
                  No buy orders yet
                </span>
              </div>
            ) : (
              tradeSignals.map(s => (
                <TradeCard key={s.id} signal={s} isNew={newIds.has(s.id)} />
              ))
            )}
          </div>
        </div>

        {/* Right — Alerts */}
        <div style={{ background: '#080810' }}>
          {/* Section header */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '14px 18px',
            borderBottom: `1px solid ${BORDER}`,
            position: 'sticky', top: 56, zIndex: 5,
            background: '#080810',
          }}>
            <Bell size={12} color={DIM} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: DIM, fontWeight: 700, letterSpacing: 1 }}>
              ALERTS & UPDATES
            </span>
            <span style={{
              marginLeft: 4,
              background: BORDER, border: `1px solid ${FAINT}`,
              borderRadius: 10, padding: '0 7px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: DIM,
            }}>
              {alerts.length}
            </span>
          </div>

          <div style={{ padding: '14px 14px' }}>
            {alerts.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 60, gap: 10 }}>
                <Bell size={24} color={FAINT} />
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: FAINT }}>
                  No alerts yet
                </span>
              </div>
            ) : (
              alerts.map(s => (
                <AlertCard key={s.id} signal={s} isNew={newIds.has(s.id)} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
