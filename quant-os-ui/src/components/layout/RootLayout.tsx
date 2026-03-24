import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Menu, X } from 'lucide-react'

export function RootLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#0B0E14', position: 'relative' }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 40, display: 'none',
          }}
          className="mobile-overlay"
        />
      )}

      {/* Sidebar — always visible on desktop, slide-in on mobile */}
      <div
        style={{
          position: 'relative',
          zIndex: 50,
          flexShrink: 0,
        }}
        className={`sidebar-wrapper${sidebarOpen ? ' open' : ''}`}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Mobile top bar */}
        <div className="mobile-topbar" style={{
          display: 'none',
          alignItems: 'center',
          gap: 12,
          padding: '12px 16px',
          borderBottom: '1px solid #1F2937',
          background: '#0D1117',
          flexShrink: 0,
        }}>
          <button
            onClick={() => setSidebarOpen(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', padding: 4, display: 'flex' }}
          >
            <Menu size={20} />
          </button>
          <span style={{ fontFamily: 'Roboto Mono', fontSize: '0.9rem', fontWeight: 700, color: '#00FF99', letterSpacing: 1 }}>
            QUANT_OS
          </span>
        </div>

        <Outlet />
      </main>

      <style>{`
        @media (max-width: 768px) {
          .mobile-topbar { display: flex !important; }
          .mobile-overlay { display: block !important; }
          .sidebar-wrapper {
            position: fixed !important;
            top: 0; left: 0; bottom: 0;
            transform: translateX(-100%);
            transition: transform 0.25s ease;
          }
          .sidebar-wrapper.open {
            transform: translateX(0);
          }
        }
      `}</style>
    </div>
  )
}
