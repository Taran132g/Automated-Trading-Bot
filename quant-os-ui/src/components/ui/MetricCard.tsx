interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
  compact?: boolean
}

export function MetricCard({ label, value, sub, color = '#f0f0f5', compact = false }: MetricCardProps) {
  return (
    <div style={{
      background: '#0c0c14',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: compact ? 8 : 10,
      padding: compact ? '10px 14px' : '14px 18px',
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{
        fontSize: '0.54rem',
        color: '#55556a',
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        fontWeight: 600,
        marginBottom: compact ? 5 : 7,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: compact ? '1.05rem' : '1.35rem',
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 700,
        color,
        lineHeight: 1.1,
        letterSpacing: '-0.02em',
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.54rem', color: '#55556a', marginTop: 4 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
