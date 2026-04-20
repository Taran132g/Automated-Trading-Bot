interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
}

export function MetricCard({ label, value, sub, color = '#f0f0f5' }: MetricCardProps) {
  return (
    <div style={{
      background: '#12121c',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: 10,
      padding: '18px 20px',
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{
        fontSize: '0.64rem', color: '#55556a', textTransform: 'uppercase',
        letterSpacing: '0.12em', fontWeight: 600, marginBottom: 10,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '1.5rem', fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 700, color, lineHeight: 1.1, letterSpacing: '-0.02em',
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.62rem', color: '#55556a', marginTop: 6 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
