import { NavLink, useNavigate } from 'react-router-dom'
import {
  Activity, FlaskConical, Search, GitCompare,
  Terminal, Bot, ShieldAlert, LogOut, X, BarChart2, Radio
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authService } from '@/services/api'
import { useQuery } from '@tanstack/react-query'
import { adminService } from '@/services/api'

const NAV = [
  { to: '/scalper',    icon: Activity,     label: 'Scalper',      tag: 'LIVE' as const },
  { to: '/pattern',    icon: BarChart2,    label: 'Pattern',      tag: 'LIVE' as const },
  { to: '/signals',    icon: Radio,        label: 'Signals',      tag: 'LIVE' as const },
  { to: '/comparison', icon: GitCompare,   label: 'Comparison',   tag: null },
  { to: '/grok',       icon: Terminal,     label: 'Grok Monitor', tag: null },
  { to: '/backtest',   icon: Search,       label: 'Backtest',     tag: 'SIM' as const },
  { to: '/patterns',   icon: FlaskConical, label: 'Pattern Lab',  tag: 'SIM' as const },
  { to: '/agents',     icon: Bot,          label: 'AI Agents',    tag: null },
  { to: '/admin',      icon: ShieldAlert,  label: 'Admin',        tag: 'AUTH' as const },
]

const TAG_COLORS: Record<string, string> = {
  LIVE: '#22c55e',
  SIM: '#3b82f6',
  AUTH: '#ef4444',
}

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
      style={{
        width: 232, minWidth: 232,
        background: '#0a0a12',
        borderRight: '1px solid rgba(255,255,255,0.06)',
      }}
      className="flex flex-col h-full"
    >
      {/* Logo */}
      <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{
            fontFamily: 'Inter, sans-serif', fontSize: '1.1rem', fontWeight: 800,
            color: '#c8ff00', letterSpacing: '-0.03em',
          }}>
            QUANT<span style={{ color: '#33334a' }}>_</span><span style={{ color: '#f0f0f5' }}>OS</span>
          </span>
          {onClose && (
            <button onClick={onClose} className="sidebar-close-btn"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#55556a', padding: 4, display: 'none' }}>
              <X size={18} />
            </button>
          )}
        </div>
        <div style={{
          fontSize: '0.56rem', color: '#33334a', marginTop: 4,
          fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.14em', textTransform: 'uppercase',
        }}>
          Trading Terminal
        </div>
      </div>

      <style>{`
        @media (max-width: 768px) {
          .sidebar-close-btn { display: flex !important; }
        }
      `}</style>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: '10px 8px', overflowY: 'auto' }}>
        {NAV.map(({ to, icon: Icon, label, tag }) => (
          <NavLink key={to} to={to} onClick={onClose}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 12px',
              margin: '1px 0',
              color: isActive ? '#f0f0f5' : '#8b8b9e',
              background: isActive ? 'rgba(200,255,0,0.05)' : 'transparent',
              borderRadius: 8,
              textDecoration: 'none',
              fontSize: '0.82rem',
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s ease',
              position: 'relative',
              overflow: 'hidden',
            })}
          >
            <Icon size={15} />
            <span style={{ flex: 1 }}>{label}</span>
            {tag && (
              <span style={{
                fontSize: '0.52rem', fontWeight: 700, letterSpacing: '0.08em',
                color: TAG_COLORS[tag] ?? '#8b8b9e',
                opacity: 0.7,
              }}>
                {tag}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* System status */}
      <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{
          fontSize: '0.58rem', color: '#33334a', marginBottom: 10,
          letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600,
        }}>
          System
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: '0.78rem', color: '#8b8b9e', marginBottom: 8,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: backendOnline ? '#22c55e' : '#ef4444',
            boxShadow: backendOnline ? '0 0 8px rgba(34,197,94,0.5)' : 'none',
            display: 'inline-block',
          }} />
          {backendOnline ? 'Backend Online' : 'Backend Offline'}
        </div>
        {authenticated && (
          <button onClick={handleLogout} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#55556a', fontSize: '0.75rem', padding: 0, marginTop: 4,
            transition: 'color 0.15s',
          }}>
            <LogOut size={12} />
            Disconnect
          </button>
        )}
      </div>
    </aside>
  )
}
