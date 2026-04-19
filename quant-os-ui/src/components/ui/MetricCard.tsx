interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
}

export function MetricCard({ label, value, sub, color = '#e4f0e4' }: MetricCardProps) {
  return (
    <div style={{
      background: 'linear-gradient(180deg, #0a2e2e 0%, #052424 100%)',
      border: '1px solid rgba(171,255,2,0.08)',
      borderRadius: 8,
      padding: '16px 18px',
      flex: 1,
    }}>
      <div style={{
        fontSize: '0.68rem', color: '#4a6a5a', textTransform: 'uppercase',
        letterSpacing: '0.1em', fontWeight: 600, marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '1.7rem', fontFamily: 'JetBrains Mono, Roboto Mono, monospace',
        fontWeight: 700, color, lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.65rem', color: '#4a6a5a', marginTop: 5 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
