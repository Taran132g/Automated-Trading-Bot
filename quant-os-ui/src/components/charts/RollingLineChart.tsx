import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export interface RollingPoint { date: string; pnl_per_share: number }

interface Props {
  baseline: RollingPoint[]
  pattern: RollingPoint[]
  height?: number
}

export function RollingLineChart({ baseline, pattern, height = 240 }: Props) {
  const all: Record<string, { date: string; baseline?: number; pattern?: number }> = {}
  for (const p of baseline) {
    all[p.date] = { ...all[p.date], date: p.date, baseline: p.pnl_per_share }
  }
  for (const p of pattern) {
    all[p.date] = { ...all[p.date], date: p.date, pattern: p.pnl_per_share }
  }
  const data = Object.values(all).sort((a, b) => a.date.localeCompare(b.date))

  if (!data.length) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4a6a5a', fontSize: '0.8rem' }}>No data</div>
  }

  const allVals = data.flatMap(d => [d.baseline, d.pattern]).filter((v): v is number => v !== undefined)
  const minVal = Math.min(...allVals)
  const maxVal = Math.max(...allVals)
  const yDomain: [number, number] = minVal === maxVal ? [minVal - 0.001, maxVal + 0.001] : [minVal, maxVal]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fill: '#4a6a5a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
        <YAxis domain={yDomain} tick={{ fill: '#4a6a5a', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(3)}`} width={70} />
        <Tooltip
          contentStyle={{ background: '#0a2e2e', border: '1px solid rgba(171,255,2,0.12)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}
          labelStyle={{ color: '#7a9a8a' }}
        />
        <Legend wrapperStyle={{ fontSize: '0.75rem', fontFamily: 'JetBrains Mono', color: '#7a9a8a' }} />
        <Line type="monotone" dataKey="baseline" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3, fill: '#60a5fa' }} name="Baseline" />
        <Line type="monotone" dataKey="pattern" stroke="#c084fc" strokeWidth={2} dot={{ r: 3, fill: '#c084fc' }} name="Pattern" />
      </LineChart>
    </ResponsiveContainer>
  )
}
