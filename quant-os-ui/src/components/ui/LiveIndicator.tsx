export function LiveIndicator({ isLive }: { isLive: boolean }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 10px',
      borderRadius: 20,
      border: `1px solid ${isLive ? '#00FF99' : '#334155'}`,
      background: isLive ? 'rgba(0,255,153,0.06)' : 'transparent',
      fontSize: '0.72rem',
      fontFamily: 'Roboto Mono',
      fontWeight: 600,
      color: isLive ? '#00FF99' : '#64748B',
      letterSpacing: '0.08em',
    }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: isLive ? '#00FF99' : '#64748B',
          display: 'inline-block',
        }}
        className={isLive ? 'pulse-live' : ''}
      />
      {isLive ? 'MARKET LIVE' : 'MARKET CLOSED'}
    </div>
  )
}
