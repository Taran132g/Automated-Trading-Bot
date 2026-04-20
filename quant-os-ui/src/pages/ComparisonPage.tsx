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
const PURPLE = '#a78bfa'
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
  const p = data?.pattern_stats

  const pnlColor = (v: number) => v > 0 ? GREEN : v < 0 ? RED : TEXT
  const liftColor = (v: number) => v > 0 ? GREEN : v < 0 ? RED : SEC
  const fmtPF = (v: number | null | undefined) =>
    v === null || v === undefined || v === Infinity ? '\u221e' : v.toFixed(2)

  const compRows = [
    { metric: 'Total PnL', scalp: `$${s?.total_pnl?.toFixed(2) ?? '0.00'}`, pat: `$${p?.total_pnl?.toFixed(2) ?? '0.00'}`, deltaVal: (p?.total_pnl ?? 0) - (s?.total_pnl ?? 0), fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}` },
    { metric: 'Win Rate', scalp: `${s?.win_rate?.toFixed(1) ?? '0.0'}%`, pat: `${p?.win_rate?.toFixed(1) ?? '0.0'}%`, deltaVal: (p?.win_rate ?? 0) - (s?.win_rate ?? 0), fmt: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` },
    { metric: 'PnL / Share', scalp: `$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`, pat: `$${p?.pnl_per_share?.toFixed(4) ?? '0.0000'}`, deltaVal: (p?.pnl_per_share ?? 0) - (s?.pnl_per_share ?? 0), fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(4)}` },
    { metric: 'Avg PnL / Trade', scalp: `$${s?.avg_pnl_per_trade?.toFixed(2) ?? '0.00'}`, pat: `$${p?.avg_pnl_per_trade?.toFixed(2) ?? '0.00'}`, deltaVal: (p?.avg_pnl_per_trade ?? 0) - (s?.avg_pnl_per_trade ?? 0), fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}` },
    { metric: 'Profit Factor', scalp: fmtPF(s?.profit_factor), pat: fmtPF(p?.profit_factor), deltaVal: 0, fmt: () => '\u2014', noColor: true },
    { metric: 'Avg Win', scalp: `$${s?.avg_win?.toFixed(2) ?? '0.00'}`, pat: `$${p?.avg_win?.toFixed(2) ?? '0.00'}`, deltaVal: (p?.avg_win ?? 0) - (s?.avg_win ?? 0), fmt: (v: number) => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}` },
    { metric: 'Avg Loss', scalp: `$${s?.avg_loss?.toFixed(2) ?? '0.00'}`, pat: `$${p?.avg_loss?.toFixed(2) ?? '0.00'}`, deltaVal: -((p?.avg_loss ?? 0) - (s?.avg_loss ?? 0)), fmt: (v: number) => `${v >= 0 ? '+' : ''}$${Math.abs(v).toFixed(2)}` },
    { metric: 'Max Consec. Losses', scalp: String(s?.max_consec_loss ?? 0), pat: String(p?.max_consec_loss ?? 0), deltaVal: -((p?.max_consec_loss ?? 0) - (s?.max_consec_loss ?? 0)), fmt: (v: number) => `${v >= 0 ? '+' : ''}${Math.round(v)}` },
    { metric: 'Total Trades', scalp: String(s?.total_trades ?? 0), pat: String(p?.total_trades ?? 0), deltaVal: 0, fmt: () => '\u2014', noColor: true },
  ]

  const scalpCurve = data?.scalp_curve ?? []
  const patternCurve = data?.pattern_curve ?? []
  const maxLen = Math.max(scalpCurve.length, patternCurve.length)
  const curveData = Array.from({ length: maxLen }, (_, i) => ({
    trade: i + 1,
    scalp: scalpCurve[i]?.value ?? null,
    pattern: patternCurve[i]?.value ?? null,
  }))
  const allCurveVals = curveData.flatMap((d) => [d.scalp, d.pattern]).filter((v): v is number => v !== null)
  const minCurve = allCurveVals.length ? Math.min(...allCurveVals) : 0
  const maxCurve = allCurveVals.length ? Math.max(...allCurveVals) : 1

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          STRATEGY COMPARISON
        </h2>
        <Badge type="live" label="SCALP" />
        <span style={{ color: DIM, fontSize: '0.8rem' }}>vs</span>
        <Badge type="pattern" label="PATTERN" />
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <div style={{ marginBottom: 8 }}><Badge type="live" label="SCALP" /></div>
          <div style={{ display: 'flex', gap: 10 }}>
            <MetricCard label="Total PnL" value={`$${s?.total_pnl?.toFixed(2) ?? '0.00'}`} color={pnlColor(s?.total_pnl ?? 0)} />
            <MetricCard label="Win Rate" value={`${s?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(s?.win_rate ?? 0) >= 50 ? GREEN : RED} />
            <MetricCard label="PnL/Share" value={`$${s?.pnl_per_share?.toFixed(4) ?? '0.0000'}`} color={pnlColor(s?.pnl_per_share ?? 0)} />
            <MetricCard label="Profit Factor" value={fmtPF(s?.profit_factor)} color={(s?.profit_factor ?? 0) >= 1.5 ? GREEN : (s?.profit_factor ?? 0) >= 1 ? '#f59e0b' : RED} />
          </div>
        </div>
        <div>
          <div style={{ marginBottom: 8 }}><Badge type="pattern" label="PATTERN" /></div>
          <div style={{ display: 'flex', gap: 10 }}>
            <MetricCard label="Total PnL" value={`$${p?.total_pnl?.toFixed(2) ?? '0.00'}`} color={pnlColor(p?.total_pnl ?? 0)} />
            <MetricCard label="Win Rate" value={`${p?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(p?.win_rate ?? 0) >= 50 ? GREEN : RED} />
            <MetricCard label="PnL/Share" value={`$${p?.pnl_per_share?.toFixed(4) ?? '0.0000'}`} color={pnlColor(p?.pnl_per_share ?? 0)} />
            <MetricCard label="Profit Factor" value={fmtPF(p?.profit_factor)} color={(p?.profit_factor ?? 0) >= 1.5 ? GREEN : (p?.profit_factor ?? 0) >= 1 ? '#f59e0b' : RED} />
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 4, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Side-by-Side Metrics</SectionHeader>
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th style={{ color: GREEN }}>Scalp</th>
                <th style={{ color: PURPLE }}>Pattern</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {compRows.map((row) => (
                <tr key={row.metric}>
                  <td style={{ color: SEC }}>{row.metric}</td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace', color: GREEN }}>{row.scalp}</td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace', color: PURPLE }}>{row.pat}</td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace', color: row.noColor ? SEC : liftColor(row.deltaVal), fontWeight: 600 }}>
                    {row.noColor ? '\u2014' : row.fmt(row.deltaVal)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ flex: 6, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Cumulative PnL by Trade #</SectionHeader>
          {curveData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={curveData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="trade" tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                <YAxis domain={minCurve === maxCurve ? [minCurve - 1, maxCurve + 1] : [minCurve, maxCurve]}
                  tick={{ fill: DIM, fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false}
                  tickFormatter={(v) => `$${v.toFixed(0)}`} width={65} />
                <ReferenceLine y={0} stroke={BORDER} strokeDasharray="3 3" />
                <Tooltip
                  contentStyle={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: '0.78rem', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}
                  labelStyle={{ color: SEC }}
                  labelFormatter={(v) => `Trade #${v}`}
                  formatter={(value, name) => [`$${(value as number)?.toFixed(2)}`, (name as string) === 'scalp' ? 'Scalp' : 'Pattern']}
                />
                <Line type="monotone" dataKey="scalp" stroke={GREEN} strokeWidth={2} dot={false} connectNulls name="scalp" />
                <Line type="monotone" dataKey="pattern" stroke={PURPLE} strokeWidth={2} dot={false} connectNulls name="pattern" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: DIM, fontSize: '0.8rem' }}>
              No data
            </div>
          )}
          <div style={{ display: 'flex', gap: 20, marginTop: 10, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem' }}>
            <span style={{ color: GREEN }}>&mdash; Scalp ({scalpCurve.length} trades)</span>
            <span style={{ color: PURPLE }}>&mdash; Pattern ({patternCurve.length} trades)</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {[
          { label: 'SCALP', rows: data?.scalp_symbol_breakdown, color: GREEN, type: 'live' },
          { label: 'PATTERN', rows: data?.pattern_symbol_breakdown, color: PURPLE, type: 'pattern' },
        ].map(({ label, rows, color, type }) => (
          <div key={label} style={{ flex: 1, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ marginBottom: 12 }}><Badge type={type} label={label} /></div>
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
                      <td style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color }}>{r.symbol}</td>
                      <td style={{ color: SEC }}>{r.win_rate.toFixed(1)}%</td>
                      <td style={{ color: r.total_pnl >= 0 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace' }}>
                        {r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(2)}
                      </td>
                      <td style={{ color: r.pnl_per_share >= 0 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace' }}>
                        {r.pnl_per_share >= 0 ? '+' : ''}${r.pnl_per_share.toFixed(4)}
                      </td>
                      <td style={{ color: DIM }}>{r.trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ color: DIM, fontSize: '0.78rem' }}>No data</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
