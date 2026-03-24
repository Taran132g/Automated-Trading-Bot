import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export interface RollingPoint { date: string; pnl_per_share: number }

interface Props {
  baseline: RollingPoint[]
  pattern: RollingPoint[]
  height?: number
}

export function RollingLineChart({ baseline, pattern, height = 240 }: Props) {
  // Merge by date
  const all: Record<string, { date: string; baseline?: number; pattern?: number }> = {}
  for (const p of baseline) {
    all[p.date] = { ...all[p.date], date: p.date, baseline: p.pnl_per_share }
  }
  for (const p of pattern) {
    all[p.date] = { ...all[p.date], date: p.date, pattern: p.pnl_per_share }
  }
  const data = Object.values(all).sort((a, b) => a.date.localeCompare(b.date))

  if (!data.length) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: '0.8rem' }}>No data</div>
  }

  const allVals = data.flatMap(d => [d.baseline, d.pattern]).filter((v): v is number => v !== undefined)
  const minVal = Math.min(...allVals)
  const maxVal = Math.max(...allVals)
  const pad = (maxVal - minVal) * 0.05 || Math.abs(minVal) * 0.05 || 0.001
  const yDomain: [number, number] = [minVal - pad, maxVal + pad]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }} tickLine={false} axisLine={false} />
        <YAxis domain={yDomain} tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }} tickLine={false} axisLine={false} tickFormatter={(v) => `$${v.toFixed(3)}`} width={70} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 6, fontFamily: 'Roboto Mono', fontSize: '0.78rem' }}
          labelStyle={{ color: '#94A3B8' }}
        />
        <Legend wrapperStyle={{ fontSize: '0.75rem', fontFamily: 'Roboto Mono', color: '#94A3B8' }} />
        <Line type="monotone" dataKey="baseline" stroke="#60A5FA" strokeWidth={2} dot={{ r: 3, fill: '#60A5FA' }} name="Baseline" />
        <Line type="monotone" dataKey="pattern" stroke="#A855F7" strokeWidth={2} dot={{ r: 3, fill: '#A855F7' }} name="Pattern" />
      </LineChart>
    </ResponsiveContainer>
  )
}
