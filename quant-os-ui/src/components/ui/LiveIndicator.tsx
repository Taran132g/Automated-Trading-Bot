export function LiveIndicator({ isLive }: { isLive: boolean }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 12px',
      borderRadius: 20,
      border: `1px solid ${isLive ? 'rgba(200,255,0,0.2)' : 'rgba(255,255,255,0.06)'}`,
      background: isLive ? 'rgba(200,255,0,0.04)' : 'transparent',
      fontSize: '0.72rem',
      fontFamily: 'JetBrains Mono, monospace',
      fontWeight: 600,
      color: isLive ? '#c8ff00' : '#55556a',
      letterSpacing: '0.06em',
    }}>
      <span
        style={{
          width: 6, height: 6, borderRadius: '50%',
          background: isLive ? '#c8ff00' : '#55556a',
          color: isLive ? '#c8ff00' : '#55556a',
          display: 'inline-block',
        }}
        className={isLive ? 'pulse-live' : ''}
      />
      {isLive ? 'MARKET LIVE' : 'MARKET CLOSED'}
    </div>
  )
}
