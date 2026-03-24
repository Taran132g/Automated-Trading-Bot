import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { PnLCurve } from '@/components/charts/PnLCurve'
import { Badge } from '@/components/ui/Badge'
import { patternService } from '@/services/api'

export function PatternLabPage() {
  const [range, setRange] = useState<'today' | 'all'>('today')

  const { data: state } = useQuery({
    queryKey: ['pattern-state'],
    queryFn: () => patternService.getState().then((r) => r.data),
    refetchInterval: 5000,
  })

  const { data: equityCurve } = useQuery({
    queryKey: ['pattern-equity', range],
    queryFn: () => patternService.getEquityCurve(range).then((r) => r.data.points),
    refetchInterval: 10000,
  })

  const { data: performance } = useQuery({
    queryKey: ['pattern-performance'],
    queryFn: () => patternService.getPerformance().then((r) => r.data.rows),
    refetchInterval: 10000,
  })

  const openPositions = Object.entries(state?.positions ?? {}).filter(([, qty]) => qty !== 0)

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
          PATTERN LAB
        </h2>
        <Badge type="shadow" label="SHADOW TEST" />
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Shadow Daily PnL" value={`${(state?.daily_pnl ?? 0) >= 0 ? '+' : ''}$${Math.abs(state?.daily_pnl ?? 0).toFixed(2)}`} color={(state?.daily_pnl ?? 0) >= 0 ? '#A855F7' : '#EF4444'} />
        <MetricCard label="Shadow Total PnL" value={`${(state?.total_pnl ?? 0) >= 0 ? '+' : ''}$${Math.abs(state?.total_pnl ?? 0).toFixed(2)}`} color={(state?.total_pnl ?? 0) >= 0 ? '#A855F7' : '#EF4444'} />
        <MetricCard label="Pattern Win Rate" value={`${state?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(state?.win_rate ?? 0) > 50 ? '#A855F7' : '#F8FAFC'} />
        <MetricCard label="Pattern Trades" value={state?.trades_today?.toLocaleString() ?? '0'} sub="TODAY" />
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 7, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <SectionHeader>Shadow Strategy Trajectory</SectionHeader>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['today', 'all'] as const).map((r) => (
                <button key={r} onClick={() => setRange(r)} style={{
                  padding: '3px 10px', borderRadius: 20, border: '1px solid #1F2937',
                  background: range === r ? '#1F2937' : 'transparent',
                  color: range === r ? '#F8FAFC' : '#64748B',
                  fontSize: '0.7rem', cursor: 'pointer', fontFamily: 'Inter',
                }}>
                  {r === 'today' ? 'Today' : 'All Time'}
                </button>
              ))}
            </div>
          </div>
          <PnLCurve data={equityCurve ?? []} color="#A855F7" height={220} />
        </div>

        <div style={{ flex: 3, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Shadow Positions</SectionHeader>
          {openPositions.length === 0 ? (
            <div style={{ color: '#64748B', fontSize: '0.78rem' }}>No open positions</div>
          ) : (
            openPositions.map(([sym, qty]) => (
              <div key={sym} style={{
                borderLeft: `3px solid ${(qty as number) > 0 ? '#A855F7' : '#EF4444'}`,
                padding: '8px 12px', marginBottom: 8, background: '#0B0E14', borderRadius: '0 6px 6px 0',
                fontFamily: 'Roboto Mono', fontSize: '0.82rem',
              }}>
                <span style={{ fontWeight: 700 }}>{sym}</span>
                <span style={{ color: '#94A3B8', margin: '0 8px' }}>{Math.abs(qty as number)} shares</span>
                <span style={{ color: (qty as number) > 0 ? '#A855F7' : '#EF4444' }}>{(qty as number) > 0 ? 'LONG' : 'SHORT'}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {performance && performance.length > 0 && (
        <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Pattern System Performance</SectionHeader>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Today PnL/Share</th>
                <th>Today Win%</th>
                <th>All Time PnL/Share</th>
                <th>All Time Win%</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {performance.map((row: { symbol: string; total_pnl: number; win_rate: number; trades: number; today_pi: number; alltime_pi: number; today_win_rate: number }) => (
                <tr key={row.symbol}>
                  <td style={{ fontWeight: 700, fontFamily: 'Roboto Mono', color: '#A855F7' }}>{row.symbol}</td>
                  <td style={{ color: (row.today_pi ?? 0) >= 0 ? '#A855F7' : '#EF4444', fontFamily: 'Roboto Mono', fontWeight: 600 }}>
                    {(row.today_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.today_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#1F2937', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.today_win_rate ?? 0}%`, background: '#A855F7', height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: '#94A3B8', minWidth: 40 }}>{(row.today_win_rate ?? 0).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: (row.alltime_pi ?? 0) >= 0 ? '#A855F7' : '#EF4444', fontFamily: 'Roboto Mono' }}>
                    {(row.alltime_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.alltime_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#1F2937', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.win_rate}%`, background: '#475569', height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: '#64748B', minWidth: 40 }}>{row.win_rate.toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: '#94A3B8' }}>{row.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
