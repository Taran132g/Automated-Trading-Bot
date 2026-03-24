import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { DailyPnLBars } from '@/components/charts/DailyPnLBars'
import { WinLossDonut } from '@/components/charts/WinLossDonut'
import { analyticsService } from '@/services/api'

export function AnalyticsPage() {
  const [historyText, setHistoryText] = useState('')
  const [showPaste, setShowPaste] = useState(false)

  const { data: summary } = useQuery({
    queryKey: ['analytics-summary'],
    queryFn: () => analyticsService.getSummary().then((r) => r.data),
    refetchInterval: 30000,
  })

  const { data: dailyPnL } = useQuery({
    queryKey: ['daily-pnl'],
    queryFn: () => analyticsService.getDailyPnL().then((r) => r.data.bars),
    refetchInterval: 60000,
  })

  const { data: winLoss } = useQuery({
    queryKey: ['win-loss'],
    queryFn: () => analyticsService.getWinLoss().then((r) => r.data),
    refetchInterval: 30000,
  })

  const parseMutation = useMutation({
    mutationFn: (text: string) => analyticsService.parseHistory(text).then((r) => r.data),
  })

  const pf = summary?.profit_factor
  const pfDisplay = pf === null || pf === undefined ? '—' : pf === Infinity ? '∞' : pf.toFixed(2)

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
        RISK &amp; PERFORMANCE ANALYTICS
      </h2>

      {/* Paste history panel */}
      <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '14px 18px' }}>
        <button
          onClick={() => setShowPaste(!showPaste)}
          style={{ background: 'none', border: 'none', color: '#94A3B8', fontSize: '0.78rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, padding: 0 }}
        >
          {showPaste ? '▼' : '▶'} Paste Schwab Trade History (optional)
        </button>
        {showPaste && (
          <div style={{ marginTop: 12 }}>
            <textarea
              value={historyText}
              onChange={(e) => setHistoryText(e.target.value)}
              rows={5}
              placeholder="Paste filled orders text from Schwab here..."
              style={{
                width: '100%', background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6,
                color: '#E2E8F0', padding: '10px 12px', fontSize: '0.78rem', fontFamily: 'Roboto Mono',
                resize: 'vertical', outline: 'none', boxSizing: 'border-box',
              }}
            />
            <button
              onClick={() => parseMutation.mutate(historyText)}
              disabled={!historyText.trim() || parseMutation.isPending}
              style={{
                marginTop: 8, padding: '8px 18px', background: historyText.trim() ? '#00FF99' : '#1F2937',
                color: historyText.trim() ? '#0B0E14' : '#64748B', border: 'none', borderRadius: 6,
                fontSize: '0.78rem', fontWeight: 600, cursor: historyText.trim() ? 'pointer' : 'not-allowed',
              }}
            >
              {parseMutation.isPending ? 'Parsing...' : 'Parse & Analyze'}
            </button>
          </div>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Profit Factor" value={pfDisplay} color={pf && pf > 1 ? '#00FF99' : '#EF4444'} />
        <MetricCard label="Win Rate" value={`${summary?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(summary?.win_rate ?? 0) > 50 ? '#00FF99' : '#F8FAFC'} />
        <MetricCard label="Risk / Reward" value={summary?.risk_reward?.toFixed(2) ?? '0.00'} />
        <MetricCard label="Round Trips" value={summary?.total_round_trips?.toLocaleString() ?? '0'} />
      </div>

      {/* Charts */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 6, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Daily PnL</SectionHeader>
          <DailyPnLBars data={dailyPnL ?? []} />
        </div>
        <div style={{ flex: 4, background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Win / Loss Distribution</SectionHeader>
          <WinLossDonut wins={winLoss?.wins ?? 0} losses={winLoss?.losses ?? 0} />
        </div>
      </div>

      {/* Parsed history results */}
      {parseMutation.data && !parseMutation.data.error && (
        <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
          <SectionHeader>Parsed Trade Analysis</SectionHeader>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <MetricCard label="Total PnL" value={`$${parseMutation.data.total_pnl?.toFixed(2) ?? '0.00'}`} />
            <MetricCard label="Total PI" value={`$${parseMutation.data.total_pi?.toFixed(2) ?? '0.00'}`} />
            <MetricCard label="Win Rate" value={`${parseMutation.data.win_rate?.toFixed(1) ?? '0.0'}%`} />
            <MetricCard label="Fills" value={parseMutation.data.total_fills?.toLocaleString() ?? '0'} />
          </div>
          {parseMutation.data.symbol_summaries && (
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Fills</th>
                  <th>Total PI</th>
                  <th>Total PnL</th>
                  <th>PnL/Share</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(parseMutation.data.symbol_summaries as Record<string, Record<string, number>>).map(([sym, s]) => (
                  <tr key={sym}>
                    <td style={{ fontWeight: 700, fontFamily: 'Roboto Mono' }}>{sym}</td>
                    <td>{s.fills}</td>
                    <td style={{ color: s.total_pi >= 0 ? '#00FF99' : '#EF4444' }}>${s.total_pi?.toFixed(2)}</td>
                    <td style={{ color: s.total_pnl >= 0 ? '#00FF99' : '#EF4444' }}>${s.total_pnl?.toFixed(2)}</td>
                    <td style={{ color: s.pnl_per_share >= 0 ? '#00FF99' : '#EF4444', fontFamily: 'Roboto Mono' }}>${s.pnl_per_share?.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
