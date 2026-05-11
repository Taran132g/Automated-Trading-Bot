import { NavLink, useNavigate } from 'react-router-dom'
import {
  Activity, Search, GitCompare,
  Terminal, Bot, ShieldAlert, LogOut, X, Radio,
  LayoutDashboard, LineChart,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authService, adminService } from '@/services/api'
import { useQuery } from '@tanstack/react-query'

const BORDER = 'rgba(255,255,255,0.06)'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const BG = '#09090f'

const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Dashboard', tag: null, end: true },
    ],
  },
  {
    label: 'Live Trading',
    items: [
      { to: '/scalper', icon: Activity, label: 'Scalper', tag: 'LIVE', end: false },
      { to: '/signals', icon: Radio, label: 'Signals', tag: 'LIVE', end: false },
    ],
  },
  {
    label: 'Simulation',
    items: [
      { to: '/backtest', icon: Search, label: 'Backtest', tag: 'SIM', end: false },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { to: '/comparison', icon: GitCompare, label: 'Comparison', tag: null, end: false },
      { to: '/analytics', icon: LineChart, label: 'Analytics', tag: null, end: false },
      { to: '/grok', icon: Terminal, label: 'Grok Monitor', tag: null, end: false },
      { to: '/agents', icon: Bot, label: 'AI Agents', tag: null, end: false },
      { to: '/admin', icon: ShieldAlert, label: 'Admin', tag: 'AUTH', end: false },
    ],
  },
]

const TAG_COLORS: Record<string, string> = {
  LIVE: GREEN,
  SIM: '#3b82f6',
  AUTH: '#f59e0b',
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
    <aside style={{
      width: 200,
      minWidth: 200,
      background: BG,
      borderRight: `1px solid ${BORDER}`,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      position: 'relative',
    }}>
      {onClose && (
        <button
          onClick={onClose}
          className="sidebar-close-btn"
          style={{
            display: 'none',
            position: 'absolute',
            top: 8,
            right: 8,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: DIM,
            padding: 4,
          }}
        >
          <X size={14} />
        </button>
      )}

      <nav style={{ flex: 1, padding: '8px 0 12px', overflowY: 'auto' }}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} style={{ marginBottom: 2 }}>
            <div style={{
              padding: '10px 16px 4px',
              fontSize: '0.54rem',
              fontWeight: 700,
              color: DIM,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
            }}>
              {group.label}
            </div>
            {group.items.map(({ to, icon: Icon, label, tag, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={onClose}
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  gap: 9,
                  padding: '6px 14px',
                  color: isActive ? TEXT : SEC,
                  background: isActive ? 'rgba(200,255,0,0.035)' : 'transparent',
                  borderLeft: `2px solid ${isActive ? ACCENT : 'transparent'}`,
                  textDecoration: 'none',
                  fontSize: '0.8rem',
                  fontWeight: isActive ? 500 : 400,
                  transition: 'all 0.1s',
                })}
              >
                <Icon size={13} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1, lineHeight: 1.2 }}>{label}</span>
                {tag && (
                  <span style={{
                    fontSize: '0.5rem',
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    color: TAG_COLORS[tag] ?? SEC,
                    fontFamily: 'JetBrains Mono, monospace',
                    flexShrink: 0,
                  }}>
                    {tag}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div style={{ padding: '10px 14px 14px', borderTop: `1px solid ${BORDER}` }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          marginBottom: authenticated ? 8 : 0,
        }}>
          <span style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: backendOnline ? GREEN : RED,
            boxShadow: backendOnline ? `0 0 5px ${GREEN}` : 'none',
            display: 'inline-block',
            flexShrink: 0,
          }} />
          <span style={{ fontSize: '0.7rem', color: backendOnline ? SEC : DIM }}>
            {backendOnline ? 'System Online' : 'System Offline'}
          </span>
        </div>
        {authenticated && (
          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: DIM,
              fontSize: '0.68rem',
              padding: 0,
              transition: 'color 0.12s',
            }}
          >
            <LogOut size={11} />
            Sign out
          </button>
        )}
      </div>

      <style>{`
        @media (max-width: 768px) {
          .sidebar-close-btn { display: flex !important; }
        }
      `}</style>
    </aside>
  )
}
