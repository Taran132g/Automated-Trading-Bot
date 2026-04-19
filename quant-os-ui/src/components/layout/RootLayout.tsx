import { Outlet, useNavigate } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'

export function RootLayout() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden', background: '#031818' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '0 20px', height: 44,
        borderBottom: '1px solid rgba(171,255,2,0.08)',
        background: '#052424',
        flexShrink: 0,
      }}>
        <button
          onClick={() => navigate('/')}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#4a6a5a', padding: '4px 8px', borderRadius: 6,
            fontSize: '0.78rem', fontFamily: 'JetBrains Mono, monospace',
            transition: 'color 0.2s',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#abff02' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#4a6a5a' }}
        >
          <ChevronLeft size={14} />
          Home
        </button>

        <div style={{ width: 1, height: 18, background: 'rgba(171,255,2,0.08)' }} />

        <span style={{
          fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', fontWeight: 800,
          color: '#abff02', letterSpacing: '-0.02em',
        }}>
          QUANT<span style={{ color: '#e4f0e4' }}>_</span>OS
        </span>
      </div>

      {/* Page content */}
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Outlet />
      </main>
    </div>
  )
}
