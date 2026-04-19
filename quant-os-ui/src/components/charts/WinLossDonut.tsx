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
            <Cell fill="#00ff88" fillOpacity={0.85} />
            <Cell fill="#ff4466" fillOpacity={0.85} />
          </Pie>
          <Tooltip
            contentStyle={{ background: '#0a2e2e', border: '1px solid rgba(171,255,2,0.12)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}
            formatter={(v, name) => [Number(v), String(name)]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div style={{
        position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.5rem', fontWeight: 700, color: '#e4f0e4' }}>
          {winPct}%
        </div>
        <div style={{ fontSize: '0.62rem', color: '#4a6a5a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          win rate
        </div>
      </div>
    </div>
  )
}
