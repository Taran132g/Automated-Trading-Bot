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
      background: '#111827',
      border: '1px solid #1F2937',
      borderRadius: 6,
      padding: '8px 12px',
      fontFamily: 'Roboto Mono',
      fontSize: '0.78rem',
      color: '#F8FAFC',
    }}>
      <div style={{ color: '#94A3B8', fontSize: '0.68rem', marginBottom: 2 }}>
        {p.payload.datetime_est}
      </div>
      <div style={{ color: p.value >= 0 ? '#00FF99' : '#EF4444', fontWeight: 700 }}>
        ${p.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
    </div>
  )
}

export function PnLCurve({ data, color = '#00FF99', height = 240 }: PnLCurveProps) {
  if (!data?.length) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B', fontSize: '0.8rem' }}>
        No data available
      </div>
    )
  }

  const values = data.map(d => d.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const pad = (maxVal - minVal) * 0.05 || Math.abs(minVal) * 0.05 || 1
  const yDomain: [number, number] = [minVal - pad, maxVal + pad]

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.18} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="datetime_est"
          tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={yDomain}
          tick={{ fill: '#64748B', fontSize: 10, fontFamily: 'Roboto Mono' }}
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
