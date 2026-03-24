import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { RollingLineChart } from '@/components/charts/RollingLineChart'
import { WinLossDonut } from '@/components/charts/WinLossDonut'
import { Badge } from '@/components/ui/Badge'
import { comparisonService } from '@/services/api'

export function ComparisonPage() {
  const [range, setRange] = useState<'all' | 'today'>('all')

  const { data } = useQuery({
    queryKey: ['comparison', range],
    queryFn: () => comparisonService.getStats(range).then((r) => r.data),
    refetchInterval: 10000,
  })

  const b = data?.baseline_stats
  const p = data?.pattern_stats

  const rejectColor = (data?.reject_rate ?? 0) > 0 ? '#F59E0B' : '#F8FAFC'
  const liftColor = (lift: number) => lift > 0 ? '#00FF99' : lift < 0 ? '#EF4444' : '#F8FAFC'
  const fmtSign = (v: number) => (v >= 0 ? '+' : '') + v

  const fmtPF = (v: number | null | undefined) => {
    if (v === null || v === undefined) return '∞'
    if (v === Infinity) return '∞'
    return v.toFixed(2)
  }

  const compRows = [
    { metric: 'Win Rate', base: `${b?.win_rate?.toFixed(1) ?? '0.0'}%`, pat: `${p?.win_rate?.toFixed(1) ?? '0.0'}%`, delta: `${fmtSign(data?.wr_lift ?? 0)}%`, deltaVal: data?.wr_lift ?? 0 },
    { metric: 'PnL / Share', base: `$${b?.pnl_per_share?.toFixed(4) ?? '0.0000'}`, pat: `$${p?.pnl_per_share?.toFixed(4) ?? '0.0000'}`, delta: `${(data?.pps_lift ?? 0) >= 0 ? '+' : ''}$${data?.pps_lift?.toFixed(4) ?? '0.0000'}`, deltaVal: data?.pps_lift ?? 0 },
    { metric: 'Profit Factor', base: fmtPF(b?.profit_factor), pat: fmtPF(p?.profit_factor), delta: '—', deltaVal: 0 },
    { metric: 'Avg Win', base: `$${b?.avg_win?.toFixed(2) ?? '0.00'}`, pat: `$${p?.avg_win?.toFixed(2) ?? '0.00'}`, delta: `${((p?.avg_win ?? 0) - (b?.avg_win ?? 0)) >= 0 ? '+' : ''}$${((p?.avg_win ?? 0) - (b?.avg_win ?? 0)).toFixed(2)}`, deltaVal: (p?.avg_win ?? 0) - (b?.avg_win ?? 0) },
    { metric: 'Avg Loss', base: `$${b?.avg_loss?.toFixed(2) ?? '0.00'}`, pat: `$${p?.avg_loss?.toFixed(2) ?? '0.00'}`, delta: `${((p?.avg_loss ?? 0) - (b?.avg_loss ?? 0)) >= 0 ? '+' : ''}$${((p?.avg_loss ?? 0) - (b?.avg_loss ?? 0)).toFixed(2)}`, deltaVal: -((p?.avg_loss ?? 0) - (b?.avg_loss ?? 0)) },
    { metric: 'Max Consec. Losses', base: String(b?.max_consec_loss ?? 0), pat: String(p?.max_consec_loss ?? 0), delta: fmtSign((p?.max_consec_loss ?? 0) - (b?.max_consec_loss ?? 0)), deltaVal: -((p?.max_consec_loss ?? 0) - (b?.max_consec_loss ?? 0)) },
    { metric: 'Total Trades', base: String(b?.total_trades ?? 0), pat: String(p?.total_trades ?? 0), delta: fmtSign((p?.total_trades ?? 0) - (b?.total_trades ?? 0)), deltaVal: 0 },
    { metric: 'Total PnL', base: `$${b?.total_pnl?.toFixed(2) ?? '0.00'}`, pat: `$${p?.total_pnl?.toFixed(2) ?? '0.00'}`, delta: `${((p?.total_pnl ?? 0) - (b?.total_pnl ?? 0)) >= 0 ? '+' : ''}$${((p?.total_pnl ?? 0) - (b?.total_pnl ?? 0)).toFixed(2)}`, deltaVal: (p?.total_pnl ?? 0) - (b?.total_pnl ?? 0) },
  ]

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
          FILTER EFFECTIVENESS
        </h2>
        <Badge type="baseline" label="BASELINE" />
        <span style={{ color: '#64748B', fontSize: '0.8rem' }}>vs</span>
        <Badge type="filter" label="PATTERN" />
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

      {/* Filter summary KPIs */}
      <div>
        <SectionHeader>Filter Summary</SectionHeader>
        <div style={{ display: 'flex', gap: 12 }}>
          <MetricCard label="Filter Reject Rate" value={`${data?.reject_rate?.toFixed(1) ?? '0.0'}%`} color={rejectColor} />
          <MetricCard label="Win Rate Lift" value={`${fmtSign(data?.wr_lift ?? 0)}%`} color={liftColor(data?.wr_lift ?? 0)} sub="Pattern vs Baseline" />
          <MetricCard label="PnL/Share Lift" value={`${(data?.pps_lift ?? 0) >= 0 ? '+' : ''}$${data?.pps_lift?.toFixed(4) ?? '0.0000'}`} color={liftColor(data?.pps_lift ?? 0)} />
          <MetricCard label="Loss Prevention" value={`${data?.loss_prevention_rate?.toFixed(1) ?? '0.0'}%`} color={(data?.loss_prevention_rate ?? 0) >= 50 ? '#00FF99' : (data?.loss_prevention_rate ?? 0) < 40 ? '#EF4444' : '#F59E0B'} sub="Of blocked trades" />
        </div>
      </div>

      {/* Side-by-side comparison table */}
      <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
        <SectionHeader>Side-by-Side Comparison</SectionHeader>
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th style={{ color: '#60A5FA' }}>Baseline (Unfiltered)</th>
              <th style={{ color: '#A855F7' }}>Pattern (Filtered)</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            {compRows.map((row) => (
              <tr key={row.metric}>
                <td style={{ color: '#94A3B8' }}>{row.metric}</td>
                <td style={{ fontFamily: 'Roboto Mono', color: '#60A5FA' }}>{row.base}</td>
                <td style={{ fontFamily: 'Roboto Mono', color: '#A855F7' }}>{row.pat}</td>
                <td style={{ fontFamily: 'Roboto Mono', color: liftColor(row.deltaVal), fontWeight: 600 }}>{row.delta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Charts row */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 6, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>7-Day Rolling PnL/Share</SectionHeader>
          <RollingLineChart baseline={data?.baseline_rolling ?? []} pattern={data?.pattern_rolling ?? []} height={220} />
        </div>

        <div style={{ flex: 4, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Filtered Trade Outcomes</SectionHeader>
          {(data?.filtered_total ?? 0) > 0 ? (
            <>
              <div style={{ color: '#94A3B8', fontSize: '0.78rem', marginBottom: 12 }}>
                Of <strong style={{ color: '#F8FAFC' }}>{data?.filtered_total}</strong> blocked trades:
              </div>
              <WinLossDonut wins={data?.filtered_losers ?? 0} losses={data?.filtered_winners ?? 0} height={180} />
              <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 10, fontFamily: 'Roboto Mono', fontSize: '0.75rem' }}>
                <span style={{ color: '#00FF99' }}>✓ {data?.filtered_losers} losers blocked</span>
                <span style={{ color: '#EF4444' }}>✗ {data?.filtered_winners} winners missed</span>
              </div>
            </>
          ) : (
            <div style={{ color: '#64748B', fontSize: '0.78rem' }}>No filtered trade data</div>
          )}
        </div>
      </div>

      {/* Symbol breakdown */}
      <div style={{ display: 'flex', gap: 16 }}>
        {[
          { label: 'BASELINE', data: data?.baseline_symbol_breakdown, color: '#60A5FA', type: 'baseline' },
          { label: 'PATTERN', data: data?.pattern_symbol_breakdown, color: '#A855F7', type: 'filter' },
        ].map(({ label, data: rows, color, type }) => (
          <div key={label} style={{ flex: 1, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
            <div style={{ marginBottom: 12 }}>
              <Badge type={type} label={label} />
            </div>
            {rows && rows.length > 0 ? (
              <table>
                <thead><tr><th>Symbol</th><th>Win%</th><th>PnL</th><th>Trades</th></tr></thead>
                <tbody>
                  {(rows as { symbol: string; win_rate: number; total_pnl: number; trades: number }[]).map((r) => (
                    <tr key={r.symbol}>
                      <td style={{ fontWeight: 700, fontFamily: 'Roboto Mono', color }}>{r.symbol}</td>
                      <td style={{ color: '#94A3B8' }}>{r.win_rate.toFixed(1)}%</td>
                      <td style={{ color: r.total_pnl >= 0 ? '#00FF99' : '#EF4444', fontFamily: 'Roboto Mono' }}>
                        {r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(2)}
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
