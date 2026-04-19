import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface Bar { date: string; daily_pnl: number; trade_count: number }

export function DailyPnLBars({ data, height = 220 }: { data: Bar[]; height?: number }) {
  if (!data?.length) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4a6a5a', fontSize: '0.8rem' }}>No data</div>
  }

  const pnls = data.map(d => d.daily_pnl)
  const minVal = Math.min(0, ...pnls)
  const maxVal = Math.max(0, ...pnls)
  const yDomain: [number, number] = [minVal, maxVal]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fill: '#4a6a5a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis domain={yDomain} tick={{ fill: '#4a6a5a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} width={60} />
        <Tooltip
          contentStyle={{ background: '#0a2e2e', border: '1px solid rgba(171,255,2,0.12)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}
          labelStyle={{ color: '#7a9a8a' }}
          formatter={(v) => [`$${Number(v).toFixed(2)}`, 'PnL']}
        />
        <Bar dataKey="daily_pnl" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.daily_pnl >= 0 ? '#00ff88' : '#ff4466'} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
