const BADGE_STYLES: Record<string, { bg: string; color: string }> = {
  live:          { bg: 'rgba(0,255,136,0.1)',    color: '#00ff88' },
  paper:         { bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa' },
  simulation:    { bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa' },
  pattern:       { bg: 'rgba(192,132,252,0.12)', color: '#c084fc' },
  shadow:        { bg: 'rgba(192,132,252,0.12)', color: '#c084fc' },
  post_market:   { bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa' },
  alert_quality: { bg: 'rgba(74,222,128,0.12)',  color: '#4ade80' },
  risk_monitor:  { bg: 'rgba(248,113,113,0.12)', color: '#f87171' },
  optimizer:     { bg: 'rgba(192,132,252,0.12)', color: '#c084fc' },
  baseline:      { bg: 'rgba(96,165,250,0.12)',  color: '#60a5fa' },
  filter:        { bg: 'rgba(192,132,252,0.12)', color: '#c084fc' },
}

interface BadgeProps {
  type: string
  label?: string
  small?: boolean
}

export function Badge({ type, label, small }: BadgeProps) {
  const style = BADGE_STYLES[type.toLowerCase()] ?? { bg: 'rgba(255,255,255,0.08)', color: '#e4f0e4' }
  return (
    <span style={{
      background: style.bg,
      color: style.color,
      border: `1px solid ${style.color}30`,
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
