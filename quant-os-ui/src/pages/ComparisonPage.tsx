import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { Badge } from '@/components/ui/Badge'
import { comparisonService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

export function ComparisonPage() {
  const [range, setRange] = useState<'all' | 'today'>('all')

  const { data } = useQuery({
    queryKey: ['comparison', range],
    queryFn: () => comparisonService.getStats(range).then((r) => r.data),
    refetchInterval: 10000,
  })

  const s = data?.scalp_stats
  const pnlColor = (v: number) => v > 0 ? GREEN : v < 0 ? RED : TEXT
  const fmtPF = (v: number | null | undefined) =>
    v === null || v === undefined || v === Infinity ? '∞' : v.toFixed(2)

  const statRows = [
    { metric: 'Total PnL',           value: `$${s?.total_pnl?.toFixed(2) ?? '0.00'}`,           color: pnlColor(s?.total_pnl ?? 0) },
    { metric: 'Win Rate',             value: `${s?.win_rate?.toFixed(1) ?? '0.0'}%`,              color: (s?.win_rate ?? 0) >= 50 ? GREEN : RED },
    { metric: 'PnL / Share',          value: `$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`,     color: pnlColor(s?.pnl_per_share ?? 0) },
    { metric: 'Avg PnL / Trade',      value: `$${s?.avg_pnl_per_trade?.toFixed(2) ?? '0.00'}`,   color: pnlColor(s?.avg_pnl_per_trade ?? 0) },
    { metric: 'Profit Factor',        value: fmtPF(s?.profit_factor),                             color: (s?.profit_factor ?? 0) >= 1.5 ? GREEN : (s?.profit_factor ?? 0) >= 1 ? '#f59e0b' : RED },
    { metric: 'Avg Win',              value: `$${s?.avg_win?.toFixed(2) ?? '0.00'}`,              color: GREEN },
    { metric: 'Avg Loss',             value: `$${s?.avg_loss?.toFixed(2) ?? '0.00'}`,             color: RED },
    { metric: 'Max Consec. Losses',   value: String(s?.max_consec_loss ?? 0),                     color: (s?.max_consec_loss ?? 0) <= 3 ? SEC : RED },
    { metric: 'Total Trades',         value: String(s?.total_trades ?? 0),                        color: SEC },
  ]

  const curve = data?.scalp_curve ?? []
  const curveData = curve.map((pt: { label: string; value: number }, i: number) => ({
    trade: i + 1,
    label: pt.label,
    value: pt.value,
  }))
  const vals = curveData.map((d: { value: number }) => d.value).filter((v: number) => v !== null)
  const minCurve = vals.length ? Math.min(...vals) : 0
  const maxCurve = vals.length ? Math.max(...vals) : 1

  const symRows = data?.scalp_symbol_breakdown ?? []

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          SCALPER PERFORMANCE
        </h2>
        <Badge type="live" label="SCALP" />
      </div>

      <div style={{ display: 'flex', gap: 4 }}>
        {(['today', 'all'] as const).map((r) => (
          <button key={r} onClick={() => setRange(r)} style={{
            padding: '5px 14px', borderRadius: 20, border: `1px solid ${BORDER}`,
            background: range === r ? '#191925' : 'transparent',
            color: range === r ? TEXT : DIM,
            fontSize: '0.75rem', cursor: 'pointer', fontFamily: 'Inter',
            transition: 'all 0.15s',
          }}>
            {r === 'today' ? 'Today' : 'All Time'}
          </button>
        ))}
      </div>

      {/* Top metric cards */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <MetricCard label="Total PnL" value={`$${s?.total_pnl?.toFixed(2) ?? '0.00'}`} color={pnlColor(s?.total_pnl ?? 0)} />
        <MetricCard label="Win Rate" value={`${s?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(s?.win_rate ?? 0) >= 50 ? GREEN : RED} />
        <MetricCard label="PnL / Share" value={`$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`} color={pnlColor(s?.pnl_per_share ?? 0)} />
        <MetricCard label="Profit Factor" value={fmtPF(s?.profit_factor)} color={(s?.profit_factor ?? 0) >= 1.5 ? GREEN : (s?.profit_factor ?? 0) >= 1 ? '#f59e0b' : RED} />
        <MetricCard label="Total Trades" value={String(s?.total_trades ?? 0)} color={SEC} />
      </div>

      {/* Equity curve + stats table */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 6, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Cumulative PnL by Trade</SectionHeader>
          {curveData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={curveData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="trade" tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                <YAxis
                  domain={minCurve === maxCurve ? [minCurve - 1, maxCurve + 1] : [minCurve, maxCurve]}
                  tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false}
                  tickFormatter={(v) => `$${v.toFixed(0)}`} width={65}
                />
                <ReferenceLine y={0} stroke={BORDER} strokeDasharray="3 3" />
                <Tooltip
                  contentStyle={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: '0.78rem', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}
                  labelStyle={{ color: SEC }}
                  labelFormatter={(v) => `Trade #${v}`}
                  formatter={(value) => [`$${(value as number)?.toFixed(2)}`, 'Cumulative PnL']}
                />
                <Line type="monotone" dataKey="value" stroke={GREEN} strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: DIM, fontSize: '0.8rem' }}>
              No data
            </div>
          )}
          <div style={{ marginTop: 10, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: GREEN }}>
            &mdash; Scalper ({curve.length} trades)
          </div>
        </div>

        <div style={{ flex: 4, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Full Stats</SectionHeader>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              {statRows.map((row) => (
                <tr key={row.metric} style={{ borderBottom: `1px solid ${BORDER}` }}>
                  <td style={{ padding: '8px 0', color: SEC, fontSize: '0.78rem' }}>{row.metric}</td>
                  <td style={{ padding: '8px 0', fontFamily: 'JetBrains Mono, monospace', color: row.color, textAlign: 'right', fontSize: '0.82rem', fontWeight: 600 }}>
                    {row.value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Symbol breakdown */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
        <SectionHeader>By Symbol</SectionHeader>
        {symRows.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Symbol', 'Win %', 'Total PnL', 'PnL / Share', 'Trades'].map((h) => (
                  <th key={h} style={{ padding: '6px 0', textAlign: h === 'Symbol' ? 'left' : 'right', fontSize: '0.7rem', color: DIM, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', borderBottom: `1px solid ${BORDER}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(symRows as { symbol: string; win_rate: number; total_pnl: number; trades: number; pnl_per_share: number }[]).map((r) => (
                <tr key={r.symbol} style={{ borderBottom: `1px solid ${BORDER}` }}>
                  <td style={{ padding: '9px 0', fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: GREEN }}>{r.symbol}</td>
                  <td style={{ padding: '9px 0', textAlign: 'right', color: r.win_rate >= 50 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem' }}>{r.win_rate.toFixed(1)}%</td>
                  <td style={{ padding: '9px 0', textAlign: 'right', color: r.total_pnl >= 0 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem' }}>
                    {r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(2)}
                  </td>
                  <td style={{ padding: '9px 0', textAlign: 'right', color: r.pnl_per_share >= 0 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem' }}>
                    {r.pnl_per_share >= 0 ? '+' : ''}${r.pnl_per_share.toFixed(4)}
                  </td>
                  <td style={{ padding: '9px 0', textAlign: 'right', color: DIM, fontSize: '0.82rem' }}>{r.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: DIM, fontSize: '0.78rem' }}>No data</div>
        )}
      </div>
    </div>
  )
}
