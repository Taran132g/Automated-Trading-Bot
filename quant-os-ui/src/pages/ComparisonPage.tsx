import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { Badge } from '@/components/ui/Badge'
import { comparisonService } from '@/services/api'

export function ComparisonPage() {
  const [range, setRange] = useState<'all' | 'today'>('all')

  const { data } = useQuery({
    queryKey: ['comparison', range],
    queryFn: () => comparisonService.getStats(range).then((r) => r.data),
    refetchInterval: 10000,
  })

  const s = data?.scalp_stats
  const p = data?.pattern_stats

  const pnlColor = (v: number) => v > 0 ? '#00FF99' : v < 0 ? '#EF4444' : '#F8FAFC'
  const liftColor = (v: number) => v > 0 ? '#00FF99' : v < 0 ? '#EF4444' : '#94A3B8'
  const fmtPF = (v: number | null | undefined) =>
    v === null || v === undefined || v === Infinity ? '∞' : v.toFixed(2)

  const compRows = [
    {
      metric: 'Total PnL',
      scalp: `$${s?.total_pnl?.toFixed(2) ?? '0.00'}`,
      pat: `$${p?.total_pnl?.toFixed(2) ?? '0.00'}`,
      deltaVal: (p?.total_pnl ?? 0) - (s?.total_pnl ?? 0),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}`,
    },
    {
      metric: 'Win Rate',
      scalp: `${s?.win_rate?.toFixed(1) ?? '0.0'}%`,
      pat: `${p?.win_rate?.toFixed(1) ?? '0.0'}%`,
      deltaVal: (p?.win_rate ?? 0) - (s?.win_rate ?? 0),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
    },
    {
      metric: 'PnL / Share',
      scalp: `$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`,
      pat: `$${p?.pnl_per_share?.toFixed(4) ?? '0.0000'}`,
      deltaVal: (p?.pnl_per_share ?? 0) - (s?.pnl_per_share ?? 0),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(4)}`,
    },
    {
      metric: 'Avg PnL / Trade',
      scalp: `$${s?.avg_pnl_per_trade?.toFixed(2) ?? '0.00'}`,
      pat: `$${p?.avg_pnl_per_trade?.toFixed(2) ?? '0.00'}`,
      deltaVal: (p?.avg_pnl_per_trade ?? 0) - (s?.avg_pnl_per_trade ?? 0),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}`,
    },
    {
      metric: 'Profit Factor',
      scalp: fmtPF(s?.profit_factor),
      pat: fmtPF(p?.profit_factor),
      deltaVal: 0,
      fmt: () => '—',
      noColor: true,
    },
    {
      metric: 'Avg Win',
      scalp: `$${s?.avg_win?.toFixed(2) ?? '0.00'}`,
      pat: `$${p?.avg_win?.toFixed(2) ?? '0.00'}`,
      deltaVal: (p?.avg_win ?? 0) - (s?.avg_win ?? 0),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}`,
    },
    {
      metric: 'Avg Loss',
      scalp: `$${s?.avg_loss?.toFixed(2) ?? '0.00'}`,
      pat: `$${p?.avg_loss?.toFixed(2) ?? '0.00'}`,
      // lower avg loss is better for pattern → positive delta = pattern better
      deltaVal: -((p?.avg_loss ?? 0) - (s?.avg_loss ?? 0)),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}$${Math.abs(v).toFixed(2)}`,
    },
    {
      metric: 'Max Consec. Losses',
      scalp: String(s?.max_consec_loss ?? 0),
      pat: String(p?.max_consec_loss ?? 0),
      deltaVal: -((p?.max_consec_loss ?? 0) - (s?.max_consec_loss ?? 0)),
      fmt: (v: number) => `${v >= 0 ? '+' : ''}${Math.round(v)}`,
    },
    {
      metric: 'Total Trades',
      scalp: String(s?.total_trades ?? 0),
      pat: String(p?.total_trades ?? 0),
      deltaVal: 0,
      fmt: () => '—',
      noColor: true,
    },
  ]

  // Merge cumulative curves by trade index
  const scalpCurve = data?.scalp_curve ?? []
  const patternCurve = data?.pattern_curve ?? []
  const maxLen = Math.max(scalpCurve.length, patternCurve.length)
  const curveData = Array.from({ length: maxLen }, (_, i) => ({
    trade: i + 1,
    scalp: scalpCurve[i]?.value ?? null,
    pattern: patternCurve[i]?.value ?? null,
  }))
  const allCurveVals = curveData
    .flatMap((d) => [d.scalp, d.pattern])
    .filter((v): v is number => v !== null)
  const minCurve = allCurveVals.length ? Math.min(...allCurveVals) : 0
  const maxCurve = allCurveVals.length ? Math.max(...allCurveVals) : 1
  const curvePad = (maxCurve - minCurve) * 0.08 || Math.abs(minCurve) * 0.05 || 1

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
          STRATEGY COMPARISON
        </h2>
        <Badge type="live" label="SCALP" />
        <span style={{ color: '#64748B', fontSize: '0.8rem' }}>vs</span>
        <Badge type="pattern" label="PATTERN" />
      </div>

      {/* Range toggle */}
      <div style={{ display: 'flex', gap: 4 }}>
        {(['today', 'all'] as const).map((r) => (
          <button key={r} onClick={() => setRange(r)} style={{
            padding: '5px 14px', borderRadius: 20, border: '1px solid #1F2937',
            background: range === r ? '#1F2937' : 'transparent',
            color: range === r ? '#F8FAFC' : '#64748B',
            fontSize: '0.75rem', cursor: 'pointer', fontFamily: 'Inter',
          }}>
            {r === 'today' ? 'Today' : 'All Time'}
          </button>
        ))}
      </div>

      {/* KPI row — one per strategy */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <div style={{ marginBottom: 8 }}><Badge type="live" label="SCALP" /></div>
          <div style={{ display: 'flex', gap: 10 }}>
            <MetricCard label="Total PnL" value={`$${s?.total_pnl?.toFixed(2) ?? '0.00'}`} color={pnlColor(s?.total_pnl ?? 0)} />
            <MetricCard label="Win Rate" value={`${s?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(s?.win_rate ?? 0) >= 50 ? '#00FF99' : '#EF4444'} />
            <MetricCard label="PnL/Share" value={`$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`} color={pnlColor(s?.pnl_per_share ?? 0)} />
            <MetricCard label="Profit Factor" value={fmtPF(s?.profit_factor)} color={(s?.profit_factor ?? 0) >= 1.5 ? '#00FF99' : (s?.profit_factor ?? 0) >= 1 ? '#F59E0B' : '#EF4444'} />
          </div>
        </div>
        <div>
          <div style={{ marginBottom: 8 }}><Badge type="pattern" label="PATTERN" /></div>
          <div style={{ display: 'flex', gap: 10 }}>
            <MetricCard label="Total PnL" value={`$${p?.total_pnl?.toFixed(2) ?? '0.00'}`} color={pnlColor(p?.total_pnl ?? 0)} />
            <MetricCard label="Win Rate" value={`${p?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(p?.win_rate ?? 0) >= 50 ? '#00FF99' : '#EF4444'} />
            <MetricCard label="PnL/Share" value={`$${p?.pnl_per_share?.toFixed(4) ?? '0.0000'}`} color={pnlColor(p?.pnl_per_share ?? 0)} />
            <MetricCard label="Profit Factor" value={fmtPF(p?.profit_factor)} color={(p?.profit_factor ?? 0) >= 1.5 ? '#00FF99' : (p?.profit_factor ?? 0) >= 1 ? '#F59E0B' : '#EF4444'} />
          </div>
        </div>
      </div>

      {/* Comparison table + Cumulative PnL curve */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 4, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Side-by-Side Metrics</SectionHeader>
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th style={{ color: '#00FF99' }}>Scalp</th>
                <th style={{ color: '#A855F7' }}>Pattern</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {compRows.map((row) => (
                <tr key={row.metric}>
                  <td style={{ color: '#94A3B8' }}>{row.metric}</td>
                  <td style={{ fontFamily: 'Roboto Mono', color: '#00FF99' }}>{row.scalp}</td>
                  <td style={{ fontFamily: 'Roboto Mono', color: '#A855F7' }}>{row.pat}</td>
                  <td style={{ fontFamily: 'Roboto Mono', color: row.noColor ? '#94A3B8' : liftColor(row.deltaVal), fontWeight: 600 }}>
                    {row.noColor ? '—' : row.fmt(row.deltaVal)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ flex: 6, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Cumulative PnL by Trade #</SectionHeader>
          {curveData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={curveData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="trade"
                  tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  domain={[minCurve - curvePad, maxCurve + curvePad]}
                  tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${v.toFixed(0)}`}
                  width={65}
                />
                <ReferenceLine y={0} stroke="#1F2937" strokeDasharray="3 3" />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 6, fontFamily: 'Roboto Mono', fontSize: '0.78rem' }}
                  labelStyle={{ color: '#94A3B8' }}
                  labelFormatter={(v) => `Trade #${v}`}
                  formatter={(value, name) => [`$${(value as number)?.toFixed(2)}`, (name as string) === 'scalp' ? 'Scalp' : 'Pattern']}
                />
                <Line type="monotone" dataKey="scalp" stroke="#00FF99" strokeWidth={2} dot={false} connectNulls name="scalp" />
                <Line type="monotone" dataKey="pattern" stroke="#A855F7" strokeWidth={2} dot={false} connectNulls name="pattern" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: '0.8rem' }}>
              No data
            </div>
          )}
          <div style={{ display: 'flex', gap: 20, marginTop: 10, fontFamily: 'Roboto Mono', fontSize: '0.75rem' }}>
            <span style={{ color: '#00FF99' }}>— Scalp ({scalpCurve.length} trades)</span>
            <span style={{ color: '#A855F7' }}>— Pattern ({patternCurve.length} trades)</span>
          </div>
        </div>
      </div>

      {/* Symbol breakdown */}
      <div style={{ display: 'flex', gap: 16 }}>
        {[
          { label: 'SCALP', rows: data?.scalp_symbol_breakdown, color: '#00FF99', type: 'live' },
          { label: 'PATTERN', rows: data?.pattern_symbol_breakdown, color: '#A855F7', type: 'pattern' },
        ].map(({ label, rows, color, type }) => (
          <div key={label} style={{ flex: 1, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
            <div style={{ marginBottom: 12 }}>
              <Badge type={type} label={label} />
            </div>
            {rows && rows.length > 0 ? (
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Win%</th>
                    <th>Total PnL</th>
                    <th>PnL/Sh</th>
                    <th>Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {(rows as { symbol: string; win_rate: number; total_pnl: number; trades: number; pnl_per_share: number }[]).map((r) => (
                    <tr key={r.symbol}>
                      <td style={{ fontWeight: 700, fontFamily: 'Roboto Mono', color }}>{r.symbol}</td>
                      <td style={{ color: '#94A3B8' }}>{r.win_rate.toFixed(1)}%</td>
                      <td style={{ color: r.total_pnl >= 0 ? '#00FF99' : '#EF4444', fontFamily: 'Roboto Mono' }}>
                        {r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(2)}
                      </td>
                      <td style={{ color: r.pnl_per_share >= 0 ? '#00FF99' : '#EF4444', fontFamily: 'Roboto Mono' }}>
                        {r.pnl_per_share >= 0 ? '+' : ''}${r.pnl_per_share.toFixed(4)}
                      </td>
                      <td style={{ color: '#64748B' }}>{r.trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ color: '#64748B', fontSize: '0.78rem' }}>No data</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
