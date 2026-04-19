export function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '0.72rem',
      fontWeight: 600,
      color: '#7a9a8a',
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      marginBottom: 12,
      paddingBottom: 6,
      borderBottom: '1px solid rgba(171,255,2,0.08)',
    }}>
      {children}
    </div>
  )
}
