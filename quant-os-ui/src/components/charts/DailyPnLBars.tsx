import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface Bar { date: string; daily_pnl: number; trade_count: number }

export function DailyPnLBars({ data, height = 220 }: { data: Bar[]; height?: number }) {
  if (!data?.length) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#55556a', fontSize: '0.8rem' }}>No data</div>
  }

  const pnls = data.map(d => d.daily_pnl)
  const minVal = Math.min(0, ...pnls)
  const maxVal = Math.max(0, ...pnls)
  const yDomain: [number, number] = [minVal, maxVal]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fill: '#55556a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis domain={yDomain} tick={{ fill: '#55556a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} width={60} />
        <Tooltip
          contentStyle={{ background: '#12121c', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: '0.78rem', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}
          labelStyle={{ color: '#8b8b9e' }}
          formatter={(v) => [`$${Number(v).toFixed(2)}`, 'PnL']}
        />
        <Bar dataKey="daily_pnl" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.daily_pnl >= 0 ? '#22c55e' : '#ef4444'} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
