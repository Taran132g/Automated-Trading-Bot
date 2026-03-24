export function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '0.72rem',
      fontWeight: 600,
      color: '#94A3B8',
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      marginBottom: 12,
      paddingBottom: 6,
      borderBottom: '1px solid #1F2937',
    }}>
      {children}
    </div>
  )
}
