interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
}

export function MetricCard({ label, value, sub, color = '#F8FAFC' }: MetricCardProps) {
  return (
    <div
      style={{
        background: 'linear-gradient(180deg, #111827 0%, #0B0E14 100%)',
        border: '1px solid #1F2937',
        borderRadius: 8,
        padding: '16px 18px',
        flex: 1,
      }}
    >
      <div style={{ fontSize: '0.68rem', color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600, marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: '1.7rem', fontFamily: 'Roboto Mono', fontWeight: 700, color, lineHeight: 1.1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.65rem', color: '#64748B', marginTop: 5 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
