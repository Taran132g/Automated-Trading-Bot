import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { MetricCard } from '@/components/ui/MetricCard'
import { useWebSocket } from '@/hooks/useWebSocket'
import { logsService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

type LogEntry = Record<string, string | number | undefined> & {
  ts?: string; level?: string; event?: string; symbol?: string
  direction?: string; price?: number; ratio?: number; message?: string; raw?: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: SEC, WARNING: '#f59e0b', WARN: '#f59e0b', ERROR: RED,
}

const EVENT_COLORS: Record<string, string> = {
  ALERT: GREEN, SYSTEM: DIM, ERROR: RED, MARKET: '#3b82f6',
}

export function GrokPage() {
  const [lines, setLines] = useState(1000)
  const [symbolFilter, setSymbolFilter] = useState('')
  const [levels, setLevels] = useState('INFO,WARNING,ERROR')
  const [activeTab, setActiveTab] = useState<'alerts' | 'market' | 'imbalance' | 'raw'>('alerts')
  const [liveEntries, setLiveEntries] = useState<LogEntry[]>([])
  const [paused, setPaused] = useState(false)
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  const { data: initData } = useQuery({
    queryKey: ['logs', lines, symbolFilter, levels],
    queryFn: () => logsService.tail(lines, symbolFilter, levels).then((r) => r.data.logs),
    staleTime: 5000,
  })

  useEffect(() => {
    if (initData) setLiveEntries(initData.slice().reverse())
  }, [initData])

  const onWsMessage = useCallback((data: unknown) => {
    if (pausedRef.current) return
    const entry = data as LogEntry
    if (!entry) return
    if (symbolFilter && entry.symbol?.toString().toUpperCase() !== symbolFilter.toUpperCase()) return
    setLiveEntries((prev) => [entry, ...prev].slice(0, 3000))
  }, [symbolFilter])

  useWebSocket({ url: '/api/logs/ws', onMessage: onWsMessage })

  const alerts = liveEntries.filter((e) => e.event === 'ALERT' || String(e.event).includes('ALERT'))
  const market = liveEntries.filter((e) => e.event === 'MARKET' || String(e.event).includes('MARKET') || String(e.event).includes('FLUX'))
  const imbalance = liveEntries.filter((e) => String(e.event).includes('IMBALANCE'))
  const errors = liveEntries.filter((e) => ['ERROR', 'WARNING', 'WARN'].includes(String(e.level).toUpperCase()))

  const lastHeartbeat = liveEntries.find((e) => String(e.event).includes('HEARTBEAT') || String(e.event).includes('SYSTEM'))?.ts ?? '\u2014'

  const TABS = [
    { key: 'alerts', label: 'Alerts', count: alerts.length },
    { key: 'market', label: 'Market Flux', count: market.length },
    { key: 'imbalance', label: 'Imbalance', count: imbalance.length },
    { key: 'raw', label: 'Raw', count: liveEntries.length },
  ]

  const activeData = { alerts, market, imbalance, raw: liveEntries }[activeTab]

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          GROK LOG MONITOR
        </h2>
        <button onClick={() => setPaused(!paused)} style={{
          padding: '5px 14px', borderRadius: 20, cursor: 'pointer',
          fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', fontWeight: 600,
          border: `1px solid ${paused ? 'rgba(245,158,11,0.3)' : BORDER}`,
          background: paused ? 'rgba(245,158,11,0.06)' : 'transparent',
          color: paused ? '#f59e0b' : DIM,
          transition: 'all 0.15s',
        }}>
          {paused ? '\u25b6 RESUME' : '\u2016 PAUSE'}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: SEC }}>Lines</label>
          <select value={lines} onChange={(e) => setLines(Number(e.target.value))}
            style={{ background: CARD, border: `1px solid ${BORDER}`, color: TEXT, borderRadius: 8, padding: '5px 10px', fontSize: '0.78rem' }}>
            {[100, 500, 1000, 2000, 5000].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: SEC }}>Symbol</label>
          <input value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())} placeholder="BBAI"
            style={{ background: CARD, border: `1px solid ${BORDER}`, color: TEXT, borderRadius: 8, padding: '5px 12px', fontSize: '0.78rem', width: 80, outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: SEC }}>Level</label>
          <select value={levels} onChange={(e) => setLevels(e.target.value)}
            style={{ background: CARD, border: `1px solid ${BORDER}`, color: TEXT, borderRadius: 8, padding: '5px 10px', fontSize: '0.78rem' }}>
            <option value="INFO,WARNING,ERROR">All</option>
            <option value="WARNING,ERROR">Warn+Error</option>
            <option value="ERROR">Error Only</option>
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Total Entries" value={liveEntries.length.toLocaleString()} />
        <MetricCard label="Alerts" value={alerts.length.toLocaleString()} color={GREEN} />
        <MetricCard label="Errors / Warnings" value={errors.length.toLocaleString()} color={errors.length > 0 ? RED : TEXT} />
        <MetricCard label="Last Heartbeat" value={lastHeartbeat ? String(lastHeartbeat).split(' ')[1] ?? '\u2014' : '\u2014'} />
      </div>

      <div style={{ flex: 1, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${BORDER}` }}>
          {TABS.map(({ key, label, count }) => (
            <button key={key} onClick={() => setActiveTab(key as typeof activeTab)} style={{
              padding: '11px 18px', background: 'none', border: 'none', cursor: 'pointer',
              color: activeTab === key ? TEXT : DIM,
              borderBottom: activeTab === key ? `2px solid ${ACCENT}` : '2px solid transparent',
              fontSize: '0.78rem', fontFamily: 'Inter', fontWeight: activeTab === key ? 600 : 400,
              transition: 'all 0.15s',
            }}>
              {label} <span style={{ color: activeTab === key ? ACCENT : DIM, marginLeft: 4, fontFamily: 'JetBrains Mono', fontSize: '0.68rem' }}>{count}</span>
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px' }}>
          {activeData?.length === 0 && (
            <div style={{ color: DIM, fontSize: '0.78rem', textAlign: 'center', padding: 20 }}>No entries</div>
          )}
          {activeData?.slice(0, 500).map((entry, i) => {
            const isLong = String(entry.direction).toLowerCase() === 'bullish' || String(entry.side).toLowerCase() === 'buy'
            const levelColor = LEVEL_COLORS[String(entry.level).toUpperCase()] ?? SEC
            const eventColor = EVENT_COLORS[String(entry.event)] ?? SEC
            return (
              <div key={i} style={{
                display: 'flex', gap: 10, padding: '6px 0',
                borderBottom: `1px solid ${BORDER}`,
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem', alignItems: 'flex-start',
                borderLeft: entry.event === 'ALERT' ? `2px solid ${isLong ? GREEN : RED}` : '2px solid transparent',
                paddingLeft: entry.event === 'ALERT' ? 10 : 0,
              }}>
                <span style={{ color: DIM, minWidth: 80, flexShrink: 0 }}>{String(entry.ts ?? '').split(' ')[1] ?? ''}</span>
                <span style={{ color: levelColor, minWidth: 48, flexShrink: 0 }}>{String(entry.level ?? 'INFO').substring(0, 4)}</span>
                <span style={{ color: eventColor, minWidth: 72, flexShrink: 0 }}>{String(entry.event ?? '')}</span>
                {entry.symbol && <span style={{ color: TEXT, fontWeight: 700, minWidth: 48 }}>{entry.symbol}</span>}
                {entry.direction && <span style={{ color: isLong ? GREEN : RED, minWidth: 64 }}>{entry.direction}</span>}
                {entry.price !== undefined && <span style={{ color: TEXT }}>${Number(entry.price).toFixed(2)}</span>}
                {entry.ratio !== undefined && <span style={{ color: SEC }}>r:{Number(entry.ratio).toFixed(2)}</span>}
                {entry.message && <span style={{ color: SEC, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.message}</span>}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
