export function LiveIndicator({ isLive }: { isLive: boolean }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 10px',
      borderRadius: 20,
      border: `1px solid ${isLive ? 'rgba(171,255,2,0.3)' : '#0d3d3d'}`,
      background: isLive ? 'rgba(171,255,2,0.06)' : 'transparent',
      fontSize: '0.72rem',
      fontFamily: 'JetBrains Mono, Roboto Mono, monospace',
      fontWeight: 600,
      color: isLive ? '#abff02' : '#4a6a5a',
      letterSpacing: '0.08em',
    }}>
      <span
        style={{
          width: 6, height: 6, borderRadius: '50%',
          background: isLive ? '#abff02' : '#4a6a5a',
          display: 'inline-block',
        }}
        className={isLive ? 'pulse-live' : ''}
      />
      {isLive ? 'MARKET LIVE' : 'MARKET CLOSED'}
    </div>
  )
}
