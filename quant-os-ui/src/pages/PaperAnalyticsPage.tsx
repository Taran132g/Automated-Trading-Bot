import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { paperService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

interface Bucket { key: string; pnl: number; trades: number; win_rate: number }
interface HourRow { hour: number; label: string; pnl: number; trades: number; win_rate: number }
interface MissSym { symbol: string; count: number; avg_cents: number }
interface Analytics {
  range: string
  trips: number
  by_hour: HourRow[]
  by_direction: Bucket[]
  by_symbol: Bucket[]
  by_conviction: Bucket[]
  misses: { total: number; avg_missed_cents: number; near_miss_pct: number; by_symbol: MissSym[] }
}

const money = (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}`
const pnlColor = (v: number) => (v > 0 ? GREEN : v < 0 ? RED : SEC)

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
      {children}
    </div>
  )
}

function chartTooltip() {
  return {
    contentStyle: { background: '#0c0c14', border: `1px solid ${BORDER}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: '0.74rem' },
    labelStyle: { color: SEC },
  }
}

function PnlBarChart({ data, xKey }: { data: Array<Record<string, unknown>>; xKey: string }) {
  const pnls = data.map((d) => Number(d.pnl))
  const dom: [number, number] = [Math.min(0, ...pnls), Math.max(0, ...pnls)]
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 6, left: 0, bottom: 0 }}>
        <XAxis dataKey={xKey} tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
        <YAxis domain={dom} tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} width={52} />
        <Tooltip
          {...chartTooltip()}
          formatter={(value, _name, item) => {
            const pl = ((item?.payload ?? {}) as Record<string, unknown>)
            return [`${money(Number(value))}  ·  ${pl.trades ?? 0} trades  ·  ${pl.win_rate ?? 0}% win`, 'P&L']
          }}
        />
        <ReferenceLine y={0} stroke={BORDER} />
        <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={Number(d.pnl) >= 0 ? GREEN : RED} fillOpacity={0.85} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function StatTable({ rows, head }: { rows: Array<[string, string, string, number]>; head: string[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
      <thead>
        <tr>{head.map((h, i) => (
          <th key={h} style={{ textAlign: i === 0 ? 'left' : 'right', color: DIM, fontWeight: 600, fontSize: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '6px 8px', borderBottom: `1px solid ${BORDER}` }}>{h}</th>
        ))}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td style={{ padding: '7px 8px', color: TEXT, fontFamily: 'JetBrains Mono', borderBottom: `1px solid ${BORDER}` }}>{r[0]}</td>
            <td style={{ padding: '7px 8px', textAlign: 'right', color: SEC, fontFamily: 'JetBrains Mono', borderBottom: `1px solid ${BORDER}` }}>{r[1]}</td>
            <td style={{ padding: '7px 8px', textAlign: 'right', color: pnlColor(r[3]), fontFamily: 'JetBrains Mono', borderBottom: `1px solid ${BORDER}` }}>{r[2]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function PaperAnalyticsPage() {
  const [range, setRange] = useState<'today' | 'all'>('all')
  const { data, isLoading } = useQuery({
    queryKey: ['paper-analytics', range],
    queryFn: () => paperService.getAnalytics(range).then((r) => r.data as Analytics),
    refetchInterval: 30000,
  })

  const trips = data?.trips ?? 0
  const netPnl = (data?.by_symbol ?? []).reduce((a, b) => a + b.pnl, 0)
  const misses = data?.misses
  const bestHour = (data?.by_hour ?? []).filter((h) => h.trades > 0).sort((a, b) => b.pnl - a.pnl)[0]
  const worstHour = (data?.by_hour ?? []).filter((h) => h.trades > 0).sort((a, b) => a.pnl - b.pnl)[0]
  const untagged = (data?.by_conviction ?? []).find((c) => c.key === 'untagged')

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          PAPER LAB — MAKER ANALYTICS
        </h2>
        <div style={{ display: 'flex', gap: 4, background: '#0c0c14', border: `1px solid ${BORDER}`, borderRadius: 8, padding: 3 }}>
          {(['today', 'all'] as const).map((r) => (
            <button key={r} onClick={() => setRange(r)}
              style={{ background: range === r ? '#1c1c2a' : 'transparent', color: range === r ? TEXT : DIM, border: 'none', borderRadius: 6, padding: '5px 14px', fontSize: '0.72rem', fontWeight: 600, cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {r === 'today' ? 'Today' : 'All-time'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div style={{ color: DIM, fontSize: '0.85rem' }}>Loading…</div>}

      {/* Summary */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <MetricCard label="Round-trips" value={trips} />
        <MetricCard label="Net P&L" value={money(netPnl)} color={pnlColor(netPnl)} />
        <MetricCard label="Best hour (ET)" value={bestHour ? bestHour.label : '—'} sub={bestHour ? money(bestHour.pnl) : undefined} color={GREEN} />
        <MetricCard label="Worst hour (ET)" value={worstHour ? worstHour.label : '—'} sub={worstHour ? money(worstHour.pnl) : undefined} color={RED} />
        <MetricCard label="Maker misses" value={misses?.total ?? 0} sub={misses ? `avg ${misses.avg_missed_cents}¢ off · ${misses.near_miss_pct}% within 1¢` : undefined} />
      </div>

      {/* Hour of day — the headline */}
      <Panel>
        <SectionHeader>P&amp;L BY HOUR OF DAY (ET) — WHEN THE EDGE SHOWS UP</SectionHeader>
        <PnlBarChart data={(data?.by_hour ?? []) as unknown as Array<Record<string, unknown>>} xKey="label" />
      </Panel>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Direction */}
        <Panel>
          <SectionHeader>LONG vs SHORT</SectionHeader>
          <StatTable
            head={['Direction', 'Trades / Win%', 'P&L']}
            rows={(data?.by_direction ?? []).map((d) => [
              d.key.toUpperCase(), `${d.trades} · ${d.win_rate}%`, money(d.pnl), d.pnl,
            ])}
          />
        </Panel>
        {/* Symbol */}
        <Panel>
          <SectionHeader>BY SYMBOL</SectionHeader>
          <StatTable
            head={['Symbol', 'Trades / Win%', 'P&L']}
            rows={(data?.by_symbol ?? []).map((d) => [
              d.key, `${d.trades} · ${d.win_rate}%`, money(d.pnl), d.pnl,
            ])}
          />
        </Panel>
      </div>

      {/* Conviction */}
      <Panel>
        <SectionHeader>P&amp;L BY CONVICTION (ENTRY IMBALANCE RATIO)</SectionHeader>
        <PnlBarChart data={(data?.by_conviction ?? []) as unknown as Array<Record<string, unknown>>} xKey="key" />
        <div style={{ marginTop: 10, fontSize: '0.72rem', color: DIM, lineHeight: 1.5 }}>
          Higher buckets = stronger order-book imbalance behind the trade.
          {untagged && untagged.trades > 0 && (
            <> <span style={{ color: SEC }}>{untagged.trades} “untagged”</span> trades predate conviction logging (29 Jun) — they’ll disappear as new data accrues.</>
          )}
        </div>
      </Panel>

      {/* Miss diagnostics */}
      <Panel>
        <SectionHeader>MAKER MISS DIAGNOSTICS — WHY ENTRIES DON’T FILL</SectionHeader>
        {misses && misses.total > 0 ? (
          <>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
              <MetricCard compact label="Total misses" value={misses.total} />
              <MetricCard compact label="Avg distance" value={`${misses.avg_missed_cents}¢`} sub="how far price was from the limit" />
              <MetricCard compact label="Near-misses (≤1¢)" value={`${misses.near_miss_pct}%`} color={misses.near_miss_pct >= 50 ? GREEN : TEXT} sub="barely missed → offset is tweakable" />
            </div>
            <StatTable
              head={['Symbol', 'Misses', 'Avg ¢ off']}
              rows={misses.by_symbol.map((m) => [m.symbol, String(m.count), `${m.avg_cents}¢`, 0])}
            />
          </>
        ) : (
          <div style={{ color: DIM, fontSize: '0.8rem' }}>No misses logged yet for this range. Data starts at the next market open.</div>
        )}
      </Panel>
    </div>
  )
}
