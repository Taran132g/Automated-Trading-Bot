import { NavLink, useNavigate } from 'react-router-dom'
import {
  Activity, FlaskConical, Search, GitCompare,
  Terminal, Bot, ShieldAlert, LogOut, X, BarChart2
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authService } from '@/services/api'
import { useQuery } from '@tanstack/react-query'
import { adminService } from '@/services/api'

const LIME = '#abff02'
const GREEN = '#00ff88'
const RED = '#ff4466'
const DIM = '#4a6a5a'
const SEC = '#7a9a8a'
const TEXT = '#e4f0e4'
const BORDER = 'rgba(171,255,2,0.08)'

const NAV = [
  { to: '/scalper',    icon: Activity,    label: 'Scalper' },
  { to: '/backtest',   icon: Search,      label: 'Backtest' },
  { to: '/pattern',    icon: BarChart2,   label: 'Pattern' },
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
      style={{ width: 220, minWidth: 220, background: '#052424', borderRight: `1px solid ${BORDER}` }}
      className="flex flex-col h-full"
    >
      {/* Logo */}
      <div style={{ padding: '20px 16px 16px', borderBottom: `1px solid ${BORDER}` }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{
            fontFamily: 'Inter, sans-serif', fontSize: '1rem', fontWeight: 800,
            color: LIME, letterSpacing: '-0.02em',
          }}>
            QUANT<span style={{ color: TEXT }}>_</span>OS
          </span>
          {onClose && (
            <button onClick={onClose} className="sidebar-close-btn"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: DIM, padding: 4, display: 'none' }}>
              <X size={18} />
            </button>
          )}
        </div>
        <div style={{ fontSize: '0.62rem', color: DIM, marginTop: 3, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.1em' }}>
          TRADING TERMINAL
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
          <NavLink key={to} to={to} onClick={onClose}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 16px',
              color: isActive ? LIME : SEC,
              background: isActive ? 'rgba(171,255,2,0.06)' : 'transparent',
              borderLeft: isActive ? `2px solid ${LIME}` : '2px solid transparent',
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
      <div style={{ padding: '12px 16px', borderTop: `1px solid ${BORDER}` }}>
        <div style={{ fontSize: '0.62rem', color: DIM, marginBottom: 8, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          System
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: SEC, marginBottom: 6 }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: backendOnline ? LIME : RED,
            boxShadow: backendOnline ? `0 0 6px ${LIME}` : `0 0 6px ${RED}`,
            display: 'inline-block',
          }} />
          Bot Backend
        </div>
        {authenticated && (
          <button onClick={handleLogout} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: 'none', cursor: 'pointer',
            color: DIM, fontSize: '0.78rem', padding: 0, marginTop: 4,
          }}>
            <LogOut size={12} />
            Disconnect Admin
          </button>
        )}
      </div>
    </aside>
  )
}
