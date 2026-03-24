import { NavLink, useNavigate } from 'react-router-dom'
import {
  Activity, FlaskConical, Search, GitCompare,
  Terminal, Bot, ShieldAlert, LogOut, Cpu, X
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authService } from '@/services/api'
import { useQuery } from '@tanstack/react-query'
import { adminService } from '@/services/api'

const NAV = [
  { to: '/terminal',   icon: Activity,    label: 'Terminal' },
  { to: '/backtest',   icon: Search,      label: 'Backtest' },
  { to: '/patterns',   icon: FlaskConical, label: 'Pattern Lab' },
  { to: '/comparison', icon: GitCompare,  label: 'Comparison' },
  { to: '/grok',       icon: Terminal,    label: 'Grok Monitor' },
  { to: '/agents',     icon: Bot,         label: 'AI Agents' },
  { to: '/admin',      icon: ShieldAlert, label: 'Admin' },
]

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const clearToken = useAuthStore((s) => s.clearToken)
  const authenticated = useAuthStore((s) => s.authenticated)
  const navigate = useNavigate()

  const { data: statusData } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const backendOnline = statusData?.loop_running || statusData?.trader_running || statusData?.grok_running

  const handleLogout = async () => {
    try { await authService.logout() } catch { /* ignore */ }
    clearToken()
    navigate('/login')
  }

  return (
    <aside
      style={{ width: 220, minWidth: 220, background: '#0D1117', borderRight: '1px solid #1F2937' }}
      className="flex flex-col h-full"
    >
      {/* Logo */}
      <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid #1F2937' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Cpu size={18} color="#00FF99" />
            <span style={{ fontFamily: 'Roboto Mono', fontSize: '1rem', fontWeight: 700, color: '#00FF99', letterSpacing: 1 }}>
              QUANT_OS
            </span>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="sidebar-close-btn"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748B', padding: 4, display: 'none' }}
            >
              <X size={18} />
            </button>
          )}
        </div>
        <div style={{ fontSize: '0.65rem', color: '#64748B', marginTop: 3, fontFamily: 'Roboto Mono' }}>
          INSTITUTIONAL TERMINAL
        </div>
      </div>

      <style>{`
        @media (max-width: 768px) {
          .sidebar-close-btn { display: flex !important; }
        }
      `}</style>

      {/* Nav links */}
      <nav style={{ flex: 1, padding: '8px 0', overflowY: 'auto' }}>
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 16px',
              color: isActive ? '#00FF99' : '#94A3B8',
              background: isActive ? 'rgba(0,255,153,0.06)' : 'transparent',
              borderLeft: isActive ? '2px solid #00FF99' : '2px solid transparent',
              textDecoration: 'none',
              fontSize: '0.82rem',
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s',
            })}
          >
            <Icon size={14} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* System status */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid #1F2937' }}>
        <div style={{ fontSize: '0.65rem', color: '#64748B', marginBottom: 8, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          System
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: '#94A3B8', marginBottom: 6 }}>
          <span
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: backendOnline ? '#00FF99' : '#EF4444',
              boxShadow: backendOnline ? '0 0 6px #00FF99' : '0 0 6px #EF4444',
              display: 'inline-block',
            }}
          />
          Bot Backend
        </div>
        {authenticated && (
          <button
            onClick={handleLogout}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#64748B', fontSize: '0.78rem', padding: 0,
              marginTop: 4,
            }}
          >
            <LogOut size={12} />
            Disconnect Admin
          </button>
        )}
      </div>
    </aside>
  )
}
