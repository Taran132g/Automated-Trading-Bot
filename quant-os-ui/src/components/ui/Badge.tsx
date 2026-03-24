const BADGE_STYLES: Record<string, { bg: string; color: string }> = {
  live:         { bg: 'rgba(0,255,153,0.1)',   color: '#00FF99' },
  paper:        { bg: 'rgba(96,165,250,0.15)',  color: '#60A5FA' },
  simulation:   { bg: 'rgba(96,165,250,0.15)',  color: '#60A5FA' },
  pattern:      { bg: 'rgba(168,85,247,0.15)',  color: '#A855F7' },
  shadow:       { bg: 'rgba(168,85,247,0.15)',  color: '#A855F7' },
  post_market:  { bg: 'rgba(96,165,250,0.15)',  color: '#60A5FA' },
  alert_quality:{ bg: 'rgba(74,222,128,0.15)', color: '#4ADE80' },
  risk_monitor: { bg: 'rgba(248,113,113,0.15)', color: '#F87171' },
  optimizer:    { bg: 'rgba(192,132,252,0.15)', color: '#C084FC' },
  baseline:     { bg: 'rgba(96,165,250,0.15)',  color: '#60A5FA' },
  filter:       { bg: 'rgba(168,85,247,0.15)',  color: '#A855F7' },
}

interface BadgeProps {
  type: string
  label?: string
  small?: boolean
}

export function Badge({ type, label, small }: BadgeProps) {
  const style = BADGE_STYLES[type.toLowerCase()] ?? { bg: 'rgba(255,255,255,0.1)', color: '#F8FAFC' }
  return (
    <span style={{
      background: style.bg,
      color: style.color,
      border: `1px solid ${style.color}33`,
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
