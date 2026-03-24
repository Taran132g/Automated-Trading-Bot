import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface Bar { date: string; daily_pnl: number; trade_count: number }

export function DailyPnLBars({ data, height = 220 }: { data: Bar[]; height?: number }) {
  if (!data?.length) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: '0.8rem' }}>No data</div>
  }

  const pnls = data.map(d => d.daily_pnl)
  const minVal = Math.min(0, ...pnls)
  const maxVal = Math.max(0, ...pnls)
  const pad = (maxVal - minVal) * 0.1 || 1
  const yDomain: [number, number] = [minVal - pad, maxVal + pad]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis domain={yDomain} tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v}`} width={60} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 6, fontFamily: 'Roboto Mono', fontSize: '0.78rem' }}
          labelStyle={{ color: '#94A3B8' }}
          formatter={(v) => [`$${Number(v).toFixed(2)}`, 'PnL']}
        />
        <Bar dataKey="daily_pnl" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.daily_pnl >= 0 ? '#00FF99' : '#EF4444'} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
