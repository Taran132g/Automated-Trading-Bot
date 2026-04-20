import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Menu } from 'lucide-react'

export function RootLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#06060b' }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="mobile-overlay"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 40, display: 'none',
          }}
        />
      )}

      {/* Sidebar */}
      <div className={`sidebar-wrapper ${sidebarOpen ? 'open' : ''}`}>
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        {/* Mobile top bar */}
        <div className="mobile-topbar" style={{
          display: 'none',
          alignItems: 'center', gap: 12, padding: '0 16px', height: 48,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          background: '#0a0a12',
          flexShrink: 0,
        }}>
          <button onClick={() => setSidebarOpen(true)} style={{
            background: 'none', border: 'none', color: '#8b8b9e',
            cursor: 'pointer', padding: 4,
          }}>
            <Menu size={20} />
          </button>
          <span style={{
            fontFamily: 'Inter, sans-serif', fontSize: '0.88rem', fontWeight: 800,
            color: '#c8ff00', letterSpacing: '-0.02em',
          }}>
            QUANT<span style={{ color: '#33334a' }}>_</span><span style={{ color: '#f0f0f5' }}>OS</span>
          </span>
        </div>

        <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <Outlet />
        </main>
      </div>

      <style>{`
        .sidebar-wrapper {
          display: flex;
          flex-shrink: 0;
        }
        @media (max-width: 768px) {
          .sidebar-wrapper {
            position: fixed;
            left: -260px;
            top: 0;
            bottom: 0;
            z-index: 50;
            transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          }
          .sidebar-wrapper.open { left: 0; }
          .mobile-overlay { display: block !important; }
          .mobile-topbar { display: flex !important; }
        }
      `}</style>
    </div>
  )
}
