import { useEffect, useRef, useState } from 'react'
import { Activity, Radio, Bell, MessageSquare, Filter } from 'lucide-react'

const GREEN  = '#22c55e'
const RED    = '#ef4444'
const ACCENT = '#c8ff00'
const DIM    = '#55556a'
const BG     = '#06060b'
const CARD   = '#0c0c14'
const BORDER = 'rgba(255,255,255,0.06)'
const TEXT   = '#f0f0f5'
const FAINT  = '#33334a'
const ORANGE = '#f59e0b'
const BLUE   = '#3b82f6'

// Stable color per channel name
const CHANNEL_PALETTE = [ACCENT, GREEN, BLUE, ORANGE, '#a78bfa', '#f472b6', '#34d399']
function channelColor(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return CHANNEL_PALETTE[Math.abs(h) % CHANNEL_PALETTE.length]
}

interface Message {
  id: number
  created_at: string
  channel: string
  raw_text: string | null
  image_path: string | null
  has_sizing: number
  entry: number | null
  sl: number | null
  tp_levels: number[]
}

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
  const color = channelColor(name)
  const short = name.length > 28 ? name.slice(0, 26) + '…' : name
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: `${color}10`, border: `1px solid ${color}30`,
      borderRadius: 4, padding: '2px 8px',
      fontFamily: 'JetBrains Mono, monospace', fontSize: '0.66rem',
      color, letterSpacing: 0.4,
    }}>
      <Radio size={8} />
      {short}
    </span>
  )
}

function MessageCard({ msg, isNew }: { msg: Message; isNew: boolean }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => { requestAnimationFrame(() => setVisible(true)) }, [])
  const color = channelColor(msg.channel)
  const hasSizing = msg.has_sizing === 1

  return (
    <div style={{
      transform: visible ? 'translateY(0)' : 'translateY(-20px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.35s cubic-bezier(0.22,1,0.36,1), opacity 0.25s ease',
      marginBottom: 12,
    }}>
      <div style={{
        background: CARD,
        border: `1px solid ${isNew ? color + '50' : BORDER}`,
        borderLeft: `3px solid ${hasSizing ? GREEN : color}`,
        borderRadius: 10, overflow: 'hidden',
        boxShadow: isNew ? `0 0 30px ${color}10` : 'none',
        transition: 'box-shadow 2s ease, border-color 2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '9px 16px', borderBottom: `1px solid ${BORDER}`,
          background: `${color}05`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ChannelBadge name={msg.channel} />
            {hasSizing && (
              <span style={{
                background: `${GREEN}18`, border: `1px solid ${GREEN}40`,
                borderRadius: 4, padding: '1px 7px',
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem',
                color: GREEN, fontWeight: 700, letterSpacing: 1,
              }}>
                SIGNAL
              </span>
            )}
          </div>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: DIM }}>
            {formatDate(msg.created_at)} · {formatTime(msg.created_at)}
          </span>
        </div>

        {/* Body */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: msg.image_path ? '1fr 1fr' : '1fr',
        }}>
          {msg.raw_text ? (
            <div style={{
              padding: '14px 16px',
              borderRight: msg.image_path ? `1px solid ${BORDER}` : 'none',
            }}>
              <pre style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.76rem',
                color: TEXT, lineHeight: 1.7, margin: 0,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {msg.raw_text}
              </pre>
            </div>
          ) : null}

          {msg.image_path ? (
            <div style={{ padding: '14px 16px' }}>
              <img
                src={`/api/signals/image/${msg.image_path}`}
                alt="Message image"
                style={{
                  width: '100%', maxHeight: 280, objectFit: 'contain',
                  borderRadius: 6, display: 'block',
                  border: `1px solid ${BORDER}`,
                  background: '#08080f',
                }}
              />
            </div>
          ) : null}
        </div>

        {/* Parsed signal strip */}
        {hasSizing && (msg.entry || msg.sl || msg.tp_levels.length > 0) && (
          <div style={{
            padding: '10px 16px', borderTop: `1px solid ${BORDER}`,
            background: `${GREEN}06`,
            display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center',
          }}>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.6rem', color: GREEN, letterSpacing: 1 }}>
              PARSED
            </span>
            {msg.entry && (
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: TEXT }}>
                Entry <span style={{ color: ACCENT }}>${msg.entry.toLocaleString()}</span>
              </span>
            )}
            {msg.sl && (
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: TEXT }}>
                SL <span style={{ color: RED }}>${msg.sl.toLocaleString()}</span>
              </span>
            )}
            {msg.tp_levels.map((tp, i) => (
              <span key={i} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: GREEN }}>
                TP{i + 1} ${tp.toLocaleString()}
              </span>
            ))}
          </div>
        )}
      </div>
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
      display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
      background: on ? ACCENT : 'transparent',
      border: `1px solid ${ACCENT}`,
      transition: 'background 0.3s', marginRight: 5,
    }} />
  )
}

export function TelegramPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [channels, setChannels] = useState<string[]>([])
  const [activeChannel, setActiveChannel] = useState('all')
  const [newIds, setNewIds] = useState<Set<number>>(new Set())
  const [connected, setConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/api/telegram/ws`

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
          setMessages(msg.messages)
          if (msg.channels) setChannels(msg.channels)
        } else if (msg.type === 'new_messages' && msg.messages.length > 0) {
          const incoming: Message[] = msg.messages
          const ids = new Set(incoming.map((m: Message) => m.id))
          setNewIds(prev => new Set([...prev, ...ids]))
          setMessages(prev => [...incoming, ...prev])
          setTimeout(() => setNewIds(prev => {
            const next = new Set(prev)
            ids.forEach(id => next.delete(id))
            return next
          }), 6000)
        }
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  // Send channel filter to server when it changes (after initial connect)
  const prevChannel = useRef(activeChannel)
  useEffect(() => {
    if (prevChannel.current === activeChannel) return
    prevChannel.current = activeChannel
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'filter', channel: activeChannel }))
    }
  }, [activeChannel])

  const withImages = messages.filter(m => m.image_path)
  const textOnly   = messages.filter(m => !m.image_path)

  return (
    <div style={{ minHeight: '100vh', background: BG, color: TEXT }}>

      {/* Sticky header */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 10,
        background: 'rgba(6,6,11,0.93)',
        backdropFilter: 'blur(16px)',
        borderBottom: `1px solid ${BORDER}`,
        padding: '0 28px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 56,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <MessageSquare size={16} color={ACCENT} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: '0.9rem', color: ACCENT, letterSpacing: 2 }}>
            TELEGRAM FEED
          </span>
          <span style={{ width: 1, height: 18, background: BORDER, display: 'inline-block' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: DIM }}>
            {messages.length} messages · {channels.length} channels
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* Channel filter pills */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Filter size={11} color={DIM} />
            {(['all', ...channels]).map(ch => {
              const isActive = activeChannel === ch
              const color = ch === 'all' ? DIM : channelColor(ch)
              const label = ch === 'all' ? 'All' : (ch.length > 18 ? ch.slice(0, 16) + '…' : ch)
              return (
                <button key={ch} onClick={() => setActiveChannel(ch)}
                  style={{
                    background: isActive ? `${color}18` : 'transparent',
                    border: `1px solid ${isActive ? color + '50' : FAINT}`,
                    borderRadius: 6, padding: '3px 10px',
                    color: isActive ? color : DIM,
                    fontSize: '0.66rem', cursor: 'pointer',
                    fontFamily: 'JetBrains Mono, monospace',
                    transition: 'all 0.12s',
                  }}>
                  {label}
                </button>
              )
            })}
          </div>

          {lastUpdate && (
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: DIM }}>
              {lastUpdate}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <LiveDot />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: connected ? ACCENT : RED }}>
              {connected ? 'LIVE' : 'RECONNECTING'}
            </span>
          </div>
        </div>
      </div>

      {/* Two-column layout: media messages left, text-only right */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 360px',
        minHeight: 'calc(100vh - 56px)',
      }}>

        {/* Left — messages with images + rich signals */}
        <div style={{ borderRight: `1px solid ${BORDER}` }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '12px 24px', borderBottom: `1px solid ${BORDER}`,
            background: `${ACCENT}04`,
            position: 'sticky', top: 56, zIndex: 5,
          }}>
            <Activity size={12} color={ACCENT} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: ACCENT, fontWeight: 700, letterSpacing: 1 }}>
              MEDIA & SIGNALS
            </span>
            <span style={{
              marginLeft: 4,
              background: `${ACCENT}18`, border: `1px solid ${ACCENT}30`,
              borderRadius: 10, padding: '0 7px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: ACCENT,
            }}>
              {withImages.length}
            </span>
          </div>

          <div style={{ padding: '18px 24px' }}>
            {withImages.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 80, gap: 12 }}>
                <Activity size={32} color={FAINT} />
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.76rem', color: DIM }}>
                  No messages with images yet
                </span>
              </div>
            ) : (
              withImages.map(m => (
                <MessageCard key={m.id} msg={m} isNew={newIds.has(m.id)} />
              ))
            )}
          </div>
        </div>

        {/* Right — text-only messages */}
        <div style={{ background: '#080810' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '12px 16px', borderBottom: `1px solid ${BORDER}`,
            position: 'sticky', top: 56, zIndex: 5,
            background: '#080810',
          }}>
            <Bell size={11} color={DIM} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: DIM, fontWeight: 700, letterSpacing: 1 }}>
              TEXT UPDATES
            </span>
            <span style={{
              marginLeft: 4,
              background: BORDER, border: `1px solid ${FAINT}`,
              borderRadius: 10, padding: '0 7px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem', color: DIM,
            }}>
              {textOnly.length}
            </span>
          </div>

          <div style={{ padding: '12px' }}>
            {textOnly.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 60, gap: 10 }}>
                <Bell size={24} color={FAINT} />
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', color: FAINT }}>
                  No text messages yet
                </span>
              </div>
            ) : (
              textOnly.map(m => (
                <MessageCard key={m.id} msg={m} isNew={newIds.has(m.id)} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
