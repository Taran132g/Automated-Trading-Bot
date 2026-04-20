export function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '0.7rem',
      fontWeight: 600,
      color: '#8b8b9e',
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      marginBottom: 14,
      paddingBottom: 8,
      borderBottom: '1px solid rgba(255,255,255,0.06)',
    }}>
      {children}
    </div>
  )
}
