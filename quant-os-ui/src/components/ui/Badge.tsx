const BADGE_STYLES: Record<string, { bg: string; color: string }> = {
  live:          { bg: 'rgba(34,197,94,0.10)',   color: '#22c55e' },
  paper:         { bg: 'rgba(59,130,246,0.10)',  color: '#3b82f6' },
  simulation:    { bg: 'rgba(59,130,246,0.10)',  color: '#3b82f6' },
  pattern:       { bg: 'rgba(167,139,250,0.10)', color: '#a78bfa' },
  shadow:        { bg: 'rgba(167,139,250,0.10)', color: '#a78bfa' },
  post_market:   { bg: 'rgba(59,130,246,0.10)',  color: '#3b82f6' },
  alert_quality: { bg: 'rgba(34,197,94,0.10)',   color: '#22c55e' },
  risk_monitor:  { bg: 'rgba(239,68,68,0.10)',   color: '#ef4444' },
  optimizer:     { bg: 'rgba(167,139,250,0.10)', color: '#a78bfa' },
  baseline:      { bg: 'rgba(59,130,246,0.10)',  color: '#3b82f6' },
  filter:        { bg: 'rgba(167,139,250,0.10)', color: '#a78bfa' },
}

interface BadgeProps {
  type: string
  label?: string
  small?: boolean
}

export function Badge({ type, label, small }: BadgeProps) {
  const style = BADGE_STYLES[type.toLowerCase()] ?? { bg: 'rgba(255,255,255,0.06)', color: '#f0f0f5' }
  return (
    <span style={{
      background: style.bg,
      color: style.color,
      border: `1px solid ${style.color}25`,
      borderRadius: 20,
      padding: small ? '2px 8px' : '3px 10px',
      fontSize: small ? '0.62rem' : '0.7rem',
      fontWeight: 600,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
    }}>
      {label || type}
    </span>
  )
}
