import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { MetricCard } from '@/components/ui/MetricCard'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { DailyPnLBars } from '@/components/charts/DailyPnLBars'
import { WinLossDonut } from '@/components/charts/WinLossDonut'
import { analyticsService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'

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
  const pfDisplay = pf === null || pf === undefined ? '\u2014' : pf === Infinity ? '\u221e' : pf.toFixed(2)

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
        RISK &amp; PERFORMANCE ANALYTICS
      </h2>

      {/* Paste history panel */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '16px 20px' }}>
        <button
          onClick={() => setShowPaste(!showPaste)}
          style={{ background: 'none', border: 'none', color: SEC, fontSize: '0.78rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, padding: 0 }}
        >
          {showPaste ? '\u25bc' : '\u25b6'} Paste Schwab Trade History (optional)
        </button>
        {showPaste && (
          <div style={{ marginTop: 12 }}>
            <textarea
              value={historyText}
              onChange={(e) => setHistoryText(e.target.value)}
              rows={5}
              placeholder="Paste filled orders text from Schwab here..."
              style={{
                width: '100%', background: '#0a0a12', border: `1px solid ${BORDER}`, borderRadius: 8,
                color: TEXT, padding: '10px 14px', fontSize: '0.78rem', fontFamily: 'JetBrains Mono, monospace',
                resize: 'vertical', outline: 'none', boxSizing: 'border-box',
              }}
            />
            <button
              onClick={() => parseMutation.mutate(historyText)}
              disabled={!historyText.trim() || parseMutation.isPending}
              style={{
                marginTop: 8, padding: '9px 20px', background: historyText.trim() ? '#c8ff00' : '#191925',
                color: historyText.trim() ? '#06060b' : DIM, border: 'none', borderRadius: 8,
                fontSize: '0.78rem', fontWeight: 600, cursor: historyText.trim() ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
              }}
            >
              {parseMutation.isPending ? 'Parsing...' : 'Parse & Analyze'}
            </button>
          </div>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12 }}>
        <MetricCard label="Profit Factor" value={pfDisplay} color={pf && pf > 1 ? GREEN : RED} />
        <MetricCard label="Win Rate" value={`${summary?.win_rate?.toFixed(1) ?? '0.0'}%`} color={(summary?.win_rate ?? 0) > 50 ? GREEN : TEXT} />
        <MetricCard label="Risk / Reward" value={summary?.risk_reward?.toFixed(2) ?? '0.00'} />
        <MetricCard label="Round Trips" value={summary?.total_round_trips?.toLocaleString() ?? '0'} />
      </div>

      {/* Charts */}
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 6, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Daily PnL</SectionHeader>
          <DailyPnLBars data={dailyPnL ?? []} />
        </div>
        <div style={{ flex: 4, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
          <SectionHeader>Win / Loss Distribution</SectionHeader>
          <WinLossDonut wins={winLoss?.wins ?? 0} losses={winLoss?.losses ?? 0} />
        </div>
      </div>

      {/* Parsed history results */}
      {parseMutation.data && !parseMutation.data.error && (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
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
                    <td style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace' }}>{sym}</td>
                    <td>{s.fills}</td>
                    <td style={{ color: s.total_pi >= 0 ? GREEN : RED }}>${s.total_pi?.toFixed(2)}</td>
                    <td style={{ color: s.total_pnl >= 0 ? GREEN : RED }}>${s.total_pnl?.toFixed(2)}</td>
                    <td style={{ color: s.pnl_per_share >= 0 ? GREEN : RED, fontFamily: 'JetBrains Mono, monospace' }}>${s.pnl_per_share?.toFixed(4)}</td>
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
