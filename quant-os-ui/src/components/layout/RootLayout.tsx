import { Outlet, useNavigate } from 'react-router-dom'
import { ChevronLeft, Cpu } from 'lucide-react'

export function RootLayout() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden', background: '#0B0E14' }}>
      {/* Slim top bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 20px',
        height: 44,
        borderBottom: '1px solid #1F2937',
        background: '#0D1117',
        flexShrink: 0,
      }}>
        <button
          onClick={() => navigate('/')}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#64748B', padding: '4px 8px', borderRadius: 6,
            fontSize: '0.78rem', fontFamily: 'Roboto Mono',
            transition: 'color 0.15s',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#00FF99' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#64748B' }}
        >
          <ChevronLeft size={14} />
          Home
        </button>

        <div style={{ width: 1, height: 18, background: '#1F2937' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Cpu size={14} color="#00FF99" />
          <span style={{
            fontFamily: 'Roboto Mono', fontSize: '0.78rem', fontWeight: 700,
            color: '#00FF99', letterSpacing: 1,
          }}>
            QUANT_OS
          </span>
        </div>
      </div>

      {/* Page content */}
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Outlet />
      </main>
    </div>
  )
}
