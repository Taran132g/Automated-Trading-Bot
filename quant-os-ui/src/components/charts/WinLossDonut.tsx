import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface WinLossDonutProps { wins: number; losses: number; height?: number }

export function WinLossDonut({ wins, losses, height = 220 }: WinLossDonutProps) {
  const data = [
    { name: 'Wins', value: wins },
    { name: 'Losses', value: losses },
  ]
  const total = wins + losses
  const winPct = total > 0 ? ((wins / total) * 100).toFixed(1) : '0.0'

  return (
    <div style={{ position: 'relative', height }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius="55%" outerRadius="75%" dataKey="value" strokeWidth={0}>
            <Cell fill="#22c55e" fillOpacity={0.85} />
            <Cell fill="#ef4444" fillOpacity={0.85} />
          </Pie>
          <Tooltip
            contentStyle={{ background: '#12121c', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: '0.78rem', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}
            formatter={(v, name) => [Number(v), String(name)]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div style={{
        position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.5rem', fontWeight: 700, color: '#f0f0f5' }}>
          {winPct}%
        </div>
        <div style={{ fontSize: '0.62rem', color: '#55556a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          win rate
        </div>
      </div>
    </div>
  )
}
