import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

interface Point {
  timestamp: number
  value: number
  datetime_est: string
}

interface PnLCurveProps {
  data: Point[]
  color?: string
  label?: string
  height?: number
}

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { payload: Point; value: number }[] }) => {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div style={{
      background: '#12121c',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 8,
      padding: '10px 14px',
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: '0.78rem',
      color: '#f0f0f5',
      boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
    }}>
      <div style={{ color: '#55556a', fontSize: '0.68rem', marginBottom: 3 }}>
        {p.payload.datetime_est}
      </div>
      <div style={{ color: p.value >= 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>
        ${p.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
    </div>
  )
}

export function PnLCurve({ data, color = '#c8ff00', height = 240 }: PnLCurveProps) {
  if (!data?.length) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#55556a', fontSize: '0.8rem' }}>
        No data available
      </div>
    )
  }

  const values = data.map(d => d.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const yDomain: [number, number] = minVal === maxVal ? [minVal - 1, maxVal + 1] : [minVal, maxVal]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.15} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="datetime_est"
          tick={{ fill: '#55556a', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={yDomain}
          tick={{ fill: '#55556a', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v.toLocaleString()}`}
          width={70}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#grad-${color.replace('#', '')})`}
          dot={false}
          activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
