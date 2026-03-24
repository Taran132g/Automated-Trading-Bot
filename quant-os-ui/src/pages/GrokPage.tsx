import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { MetricCard } from '@/components/ui/MetricCard'
import { useWebSocket } from '@/hooks/useWebSocket'
import { logsService } from '@/services/api'

type LogEntry = Record<string, string | number | undefined> & {
  ts?: string
  level?: string
  event?: string
  symbol?: string
  direction?: string
  price?: number
  ratio?: number
  message?: string
  raw?: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: '#94A3B8',
  WARNING: '#F59E0B',
  WARN: '#F59E0B',
  ERROR: '#EF4444',
}

const EVENT_COLORS: Record<string, string> = {
  ALERT: '#00FF99',
  SYSTEM: '#64748B',
  ERROR: '#EF4444',
  MARKET: '#60A5FA',
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

  // Initial load
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

  const lastHeartbeat = liveEntries.find((e) => String(e.event).includes('HEARTBEAT') || String(e.event).includes('SYSTEM'))?.ts ?? '—'

  const TABS = [
    { key: 'alerts', label: '🚨 Alerts', count: alerts.length },
    { key: 'market', label: '📊 Market Flux', count: market.length },
    { key: 'imbalance', label: '⚡ Imbalance', count: imbalance.length },
    { key: 'raw', label: '💻 Raw', count: liveEntries.length },
  ]

  const activeData = { alerts, market, imbalance, raw: liveEntries }[activeTab]

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
          GROK LOG MONITOR
        </h2>
        <button
          onClick={() => setPaused(!paused)}
          style={{
            padding: '5px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Roboto Mono',
            fontSize: '0.72rem', fontWeight: 600, border: '1px solid',
            borderColor: paused ? '#F59E0B' : '#1F2937',
            background: paused ? 'rgba(245,158,11,0.1)' : 'transparent',
            color: paused ? '#F59E0B' : '#64748B',
          }}
        >
          {paused ? '▶ RESUME' : '‖ PAUSE'}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: '#94A3B8' }}>Lines</label>
          <select value={lines} onChange={(e) => setLines(Number(e.target.value))}
            style={{ background: '#111827', border: '1px solid #1F2937', color: '#E2E8F0', borderRadius: 6, padding: '4px 8px', fontSize: '0.78rem' }}>
            {[100, 500, 1000, 2000, 5000].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: '#94A3B8' }}>Symbol</label>
          <input value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())} placeholder="BBAI"
            style={{ background: '#111827', border: '1px solid #1F2937', color: '#E2E8F0', borderRadius: 6, padding: '4px 10px', fontSize: '0.78rem', width: 80, outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: '0.72rem', color: '#94A3B8' }}>Level</label>
          <select value={levels} onChange={(e) => setLevels(e.target.value)}
            style={{ background: '#111827', border: '1px solid #1F2937', color: '#E2E8F0', borderRadius: 6, padding: '4px 8px', fontSize: '0.78rem' }}>
            <option value="INFO,WARNING,ERROR">All</option>
            <option value="WARNING,ERROR">Warn+Error</option>
            <option value="ERROR">Error Only</option>
          </select>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Total Entries" value={liveEntries.length.toLocaleString()} />
        <MetricCard label="Alerts" value={alerts.length.toLocaleString()} color="#00FF99" />
        <MetricCard label="Errors / Warnings" value={errors.length.toLocaleString()} color={errors.length > 0 ? '#EF4444' : '#F8FAFC'} />
        <MetricCard label="Last Heartbeat" value={lastHeartbeat ? String(lastHeartbeat).split(' ')[1] ?? '—' : '—'} />
      </div>

      {/* Tabs */}
      <div style={{ flex: 1, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid #1F2937' }}>
          {TABS.map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key as typeof activeTab)}
              style={{
                padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer',
                color: activeTab === key ? '#F8FAFC' : '#64748B',
                borderBottom: activeTab === key ? '2px solid #00FF99' : '2px solid transparent',
                fontSize: '0.78rem', fontFamily: 'Inter', fontWeight: activeTab === key ? 600 : 400,
              }}
            >
              {label} <span style={{ color: activeTab === key ? '#00FF99' : '#64748B', marginLeft: 4, fontFamily: 'Roboto Mono', fontSize: '0.68rem' }}>{count}</span>
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
          {activeData?.length === 0 && (
            <div style={{ color: '#64748B', fontSize: '0.78rem', textAlign: 'center', padding: 20 }}>No entries</div>
          )}
          {activeData?.slice(0, 500).map((entry, i) => {
            const isLong = String(entry.direction).toLowerCase() === 'bullish' || String(entry.side).toLowerCase() === 'buy'
            const levelColor = LEVEL_COLORS[String(entry.level).toUpperCase()] ?? '#94A3B8'
            const eventColor = EVENT_COLORS[String(entry.event)] ?? '#94A3B8'
            return (
              <div key={i} style={{
                display: 'flex', gap: 10, padding: '5px 0', borderBottom: '1px solid #0D1117',
                fontFamily: 'Roboto Mono', fontSize: '0.72rem', alignItems: 'flex-start',
                borderLeft: entry.event === 'ALERT' ? `2px solid ${isLong ? '#00FF99' : '#EF4444'}` : '2px solid transparent',
                paddingLeft: entry.event === 'ALERT' ? 8 : 0,
              }}>
                <span style={{ color: '#64748B', minWidth: 80, flexShrink: 0 }}>{String(entry.ts ?? '').split(' ')[1] ?? ''}</span>
                <span style={{ color: levelColor, minWidth: 48, flexShrink: 0 }}>{String(entry.level ?? 'INFO').substring(0, 4)}</span>
                <span style={{ color: eventColor, minWidth: 72, flexShrink: 0 }}>{String(entry.event ?? '')}</span>
                {entry.symbol && <span style={{ color: '#E2E8F0', fontWeight: 700, minWidth: 48 }}>{entry.symbol}</span>}
                {entry.direction && <span style={{ color: isLong ? '#00FF99' : '#EF4444', minWidth: 64 }}>{entry.direction}</span>}
                {entry.price !== undefined && <span style={{ color: '#F8FAFC' }}>${Number(entry.price).toFixed(2)}</span>}
                {entry.ratio !== undefined && <span style={{ color: '#94A3B8' }}>r:{Number(entry.ratio).toFixed(2)}</span>}
                {entry.message && <span style={{ color: '#94A3B8', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.message}</span>}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
