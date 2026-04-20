import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { PnLCurve } from '@/components/charts/PnLCurve'
import { Badge } from '@/components/ui/Badge'
import { paperService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const BLUE = '#3b82f6'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

export function BacktestPage() {
  const [range, setRange] = useState<'today' | 'all'>('today')

  const { data: state } = useQuery({
    queryKey: ['paper-state'],
    queryFn: () => paperService.getState().then((r) => r.data),
    refetchInterval: 5000,
  })

  const { data: equityCurve } = useQuery({
    queryKey: ['paper-equity', range],
    queryFn: () => paperService.getEquityCurve(range).then((r) => r.data.points),
    refetchInterval: 10000,
  })

  const { data: performance } = useQuery({
    queryKey: ['paper-performance'],
    queryFn: () => paperService.getPerformance().then((r) => r.data.rows),
    refetchInterval: 10000,
  })

  const openPositions = Object.entries(state?.positions ?? {}).filter(([, qty]) => qty !== 0)

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
          PAPER TRADING
        </h2>
        <Badge type="simulation" label="SIMULATION" />
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Daily PnL" value={`${state?.daily_pnl >= 0 ? '+' : ''}$${Math.abs(state?.daily_pnl ?? 0).toFixed(2)}`} color={(state?.daily_pnl ?? 0) >= 0 ? BLUE : RED} />
        <MetricCard label="Total PnL" value={`${(state?.total_pnl ?? 0) >= 0 ? '+' : ''}$${Math.abs(state?.total_pnl ?? 0).toFixed(2)}`} color={(state?.total_pnl ?? 0) >= 0 ? BLUE : RED} />
        <MetricCard label="Win Rate" value={`${state?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(state?.win_rate ?? 0) > 50 ? BLUE : TEXT} sub="TODAY" />
        <MetricCard label="Trades Today" value={state?.trades_today?.toLocaleString() ?? '0'} />
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 7, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <SectionHeader>Cumulative PnL</SectionHeader>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['today', 'all'] as const).map((r) => (
                <button key={r} onClick={() => setRange(r)} style={{
                  padding: '4px 12px', borderRadius: 20, border: `1px solid ${BORDER}`,
                  background: range === r ? '#191925' : 'transparent',
                  color: range === r ? TEXT : DIM,
                  fontSize: '0.7rem', cursor: 'pointer', fontFamily: 'Inter',
                  transition: 'all 0.15s',
                }}>
                  {r === 'today' ? 'Today' : 'All Time'}
                </button>
              ))}
            </div>
          </div>
          <PnLCurve data={equityCurve ?? []} color={BLUE} height={220} />
        </div>

        <div style={{ flex: 3, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px', overflowY: 'auto' }}>
          <SectionHeader>Paper Positions</SectionHeader>
          {openPositions.length === 0 ? (
            <div style={{ color: DIM, fontSize: '0.78rem' }}>No open positions</div>
          ) : (
            openPositions.map(([sym, qty]) => (
              <div key={sym} style={{
                borderLeft: `3px solid ${(qty as number) > 0 ? BLUE : RED}`,
                padding: '10px 14px', marginBottom: 8, background: '#0c0c14', borderRadius: '0 8px 8px 0',
                fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem',
              }}>
                <span style={{ color: TEXT, fontWeight: 700 }}>{sym}</span>
                <span style={{ color: SEC, margin: '0 10px' }}>{Math.abs(qty as number)} shares</span>
                <span style={{ color: (qty as number) > 0 ? BLUE : RED }}>{(qty as number) > 0 ? 'LONG' : 'SHORT'}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {performance && performance.length > 0 && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Symbol Performance</SectionHeader>
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
                  <td style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: BLUE }}>{row.symbol}</td>
                  <td style={{ color: (row.today_pi ?? 0) >= 0 ? BLUE : RED, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                    {(row.today_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.today_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#0c0c14', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.today_win_rate ?? 0}%`, background: BLUE, height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: SEC, minWidth: 40 }}>{(row.today_win_rate ?? 0).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: (row.alltime_pi ?? 0) >= 0 ? BLUE : RED, fontFamily: 'JetBrains Mono, monospace' }}>
                    {(row.alltime_pi ?? 0) >= 0 ? '+' : ''}${Math.abs(row.alltime_pi ?? 0).toFixed(4)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, background: '#0c0c14', borderRadius: 4, height: 4 }}>
                        <div style={{ width: `${row.win_rate}%`, background: DIM, height: 4, borderRadius: 4 }} />
                      </div>
                      <span style={{ color: DIM, minWidth: 40 }}>{row.win_rate.toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ color: SEC }}>{row.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
