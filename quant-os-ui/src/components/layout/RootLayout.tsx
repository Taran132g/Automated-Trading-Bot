import { useState, useEffect, useRef } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  Activity, BarChart2, Radio, Search, FlaskConical,
  GitCompare, Terminal, Bot, ShieldAlert, LogOut,
  LineChart, LayoutDashboard, ChevronDown,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { authService, adminService, terminalService } from '@/services/api'
import { useQuery } from '@tanstack/react-query'

const BORDER = 'rgba(255,255,255,0.06)'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const BG_BAR = '#08080e'
const BG_DROPDOWN = '#0e0e1a'

function isMarketOpen() {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const d = et.getDay()
  const mins = et.getHours() * 60 + et.getMinutes()
  return d >= 1 && d <= 5 && mins >= 570 && mins < 960
}

type DropdownItem = { to: string; icon: React.ElementType; label: string; tag?: string }

const TAG_COLORS: Record<string, string> = {
  LIVE: GREEN,
  SIM: '#3b82f6',
  AUTH: '#f59e0b',
}

function NavDropdown({
  label, items,
}: { label: string; items: DropdownItem[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          background: 'none', border: 'none', cursor: 'pointer',
          color: open ? TEXT : SEC, fontSize: '0.78rem', fontWeight: 500,
          padding: '0 12px', height: 44,
          transition: 'color 0.12s',
          fontFamily: 'Inter, sans-serif',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = TEXT }}
        onMouseLeave={e => { if (!open) e.currentTarget.style.color = SEC }}
      >
        {label}
        <ChevronDown
          size={11}
          style={{
            transition: 'transform 0.18s',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            opacity: 0.6,
          }}
        />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, zIndex: 200,
          background: BG_DROPDOWN,
          border: `1px solid ${BORDER}`,
          borderRadius: 8,
          minWidth: 180,
          padding: '4px 0',
          boxShadow: '0 16px 40px rgba(0,0,0,0.6)',
          animation: 'dropIn 0.15s cubic-bezier(0.16,1,0.3,1) both',
        }}>
          {items.map(({ to, icon: Icon, label: lbl, tag }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 9,
                padding: '8px 14px',
                color: isActive ? TEXT : SEC,
                background: isActive ? 'rgba(200,255,0,0.04)' : 'transparent',
                textDecoration: 'none',
                fontSize: '0.78rem',
                transition: 'all 0.1s',
              })}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
            >
              <Icon size={13} style={{ flexShrink: 0, opacity: 0.7 }} />
              <span style={{ flex: 1 }}>{lbl}</span>
              {tag && (
                <span style={{
                  fontSize: '0.48rem', fontWeight: 700, letterSpacing: '0.08em',
                  color: TAG_COLORS[tag] ?? SEC,
                  fontFamily: 'JetBrains Mono, monospace',
                }}>
                  {tag}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

function BotStatusDot({ online }: { online: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ position: 'relative', width: 8, height: 8 }}>
        <span style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: online ? GREEN : RED,
          animation: online ? 'botPulseCore 2s ease-in-out infinite' : 'none',
        }} />
        {online && (
          <span style={{
            position: 'absolute', inset: -3,
            borderRadius: '50%',
            border: `1px solid ${GREEN}`,
            opacity: 0,
            animation: 'botPulseRing 2s ease-out infinite',
          }} />
        )}
      </div>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '0.66rem',
        color: online ? SEC : DIM,
        letterSpacing: '0.04em',
      }}>
        {online ? 'BOT ON' : 'BOT OFF'}
      </span>
    </div>
  )
}

function TopNav() {
  const [time, setTime] = useState('')
  const [open, setOpen] = useState(false)
  const clearToken = useAuthStore((s) => s.clearToken)
  const authenticated = useAuthStore((s) => s.authenticated)
  const navigate = useNavigate()

  useEffect(() => {
    const tick = () => {
      setTime(new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false }))
      setOpen(isMarketOpen())
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  const { data: scalperState } = useQuery({
    queryKey: ['terminal-state'],
    queryFn: () => terminalService.getState().then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })
  const { data: statusData } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 10000, retry: false,
  })

  const backendOnline = !!(statusData?.loop_running || statusData?.trader_running || statusData?.grok_running)
  const acctVal = scalperState?.account_details?.liquidation_value
  const dayPnl = scalperState?.daily_pnl

  const handleLogout = async () => {
    try { await authService.logout() } catch { /* ignore */ }
    clearToken()
    navigate('/login')
  }

  return (
    <div style={{
      height: 44, flexShrink: 0,
      display: 'flex', alignItems: 'stretch',
      background: BG_BAR,
      borderBottom: `1px solid ${BORDER}`,
      position: 'relative', zIndex: 100,
    }}>
      {/* Brand */}
      <div style={{
        padding: '0 24px',
        display: 'flex', alignItems: 'center',
        borderRight: `1px solid ${BORDER}`,
        flexShrink: 0,
      }}>
        <NavLink to="/" style={{ textDecoration: 'none' }}>
          <span style={{
            fontFamily: 'Inter, sans-serif', fontSize: '0.92rem',
            fontWeight: 900, letterSpacing: '-0.02em', color: ACCENT,
          }}>
            <span style={{ color: ACCENT }}>TN</span>Fund
          </span>
        </NavLink>
      </div>

      {/* Nav items */}
      <nav style={{ display: 'flex', alignItems: 'stretch', flex: 1 }}>
        <NavLink
          to="/"
          end
          style={({ isActive }) => ({
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 14px',
            color: isActive ? TEXT : SEC,
            borderBottom: isActive ? `2px solid ${ACCENT}` : '2px solid transparent',
            textDecoration: 'none', fontSize: '0.78rem', fontWeight: 500,
            transition: 'all 0.12s', fontFamily: 'Inter, sans-serif',
            marginBottom: isActive ? 0 : 0,
          })}
        >
          <LayoutDashboard size={13} />
          Dashboard
        </NavLink>

        <NavDropdown label="Live Trading" items={[
          { to: '/scalper', icon: Activity, label: 'Scalper', tag: 'LIVE' },
          { to: '/pattern', icon: BarChart2, label: 'Pattern', tag: 'LIVE' },
          { to: '/signals', icon: Radio, label: 'Signals', tag: 'LIVE' },
        ]} />
        <NavDropdown label="Simulation" items={[
          { to: '/backtest', icon: Search, label: 'Backtest', tag: 'SIM' },
          { to: '/patterns', icon: FlaskConical, label: 'Pattern Lab', tag: 'SIM' },
        ]} />
        <NavDropdown label="Analysis" items={[
          { to: '/comparison', icon: GitCompare, label: 'Comparison' },
          { to: '/analytics', icon: LineChart, label: 'Analytics' },
          { to: '/grok', icon: Terminal, label: 'Grok Monitor' },
          { to: '/agents', icon: Bot, label: 'AI Agents' },
          { to: '/admin', icon: ShieldAlert, label: 'Admin', tag: 'AUTH' },
        ]} />
      </nav>

      {/* Right section — live metrics */}
      <div style={{ display: 'flex', alignItems: 'stretch', marginLeft: 'auto' }}>
        {acctVal != null && (
          <div style={{
            padding: '0 18px', display: 'flex', flexDirection: 'column', justifyContent: 'center',
            borderLeft: `1px solid ${BORDER}`,
          }}>
            <div style={{ fontSize: '0.48rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 2 }}>Account</div>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.8rem', fontWeight: 700, color: TEXT }}>
              ${acctVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
        )}
        {dayPnl != null && (
          <div style={{
            padding: '0 18px', display: 'flex', flexDirection: 'column', justifyContent: 'center',
            borderLeft: `1px solid ${BORDER}`,
          }}>
            <div style={{ fontSize: '0.48rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 2 }}>Day P&L</div>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.8rem', fontWeight: 700,
              color: dayPnl >= 0 ? GREEN : RED,
            }}>
              {dayPnl >= 0 ? '+' : ''}${Math.abs(dayPnl).toFixed(2)}
            </div>
          </div>
        )}
        <div style={{
          padding: '0 18px', display: 'flex', alignItems: 'center',
          borderLeft: `1px solid ${BORDER}`,
        }}>
          <BotStatusDot online={backendOnline} />
        </div>
        <div style={{
          padding: '0 16px', display: 'flex', alignItems: 'center', gap: 10,
          borderLeft: `1px solid ${BORDER}`,
        }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.74rem', color: SEC }}>
            {time} ET
          </span>
          <span style={{
            fontSize: '0.54rem', fontWeight: 700, letterSpacing: '0.1em',
            padding: '2px 8px', borderRadius: 4,
            background: open ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)',
            border: `1px solid ${open ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
            color: open ? GREEN : RED,
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            {open ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
        {authenticated && (
          <button
            onClick={handleLogout}
            style={{
              padding: '0 16px', display: 'flex', alignItems: 'center', gap: 5,
              background: 'none', border: 'none', cursor: 'pointer',
              color: DIM, fontSize: '0.68rem',
              borderLeft: `1px solid ${BORDER}`,
              transition: 'color 0.12s',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = TEXT }}
            onMouseLeave={e => { e.currentTarget.style.color = DIM }}
          >
            <LogOut size={11} />
            Sign out
          </button>
        )}
      </div>

      <style>{`
        @keyframes botPulseCore {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.75; transform: scale(0.85); }
        }
        @keyframes botPulseRing {
          0%   { transform: scale(0.6); opacity: 0.6; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @keyframes dropIn {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}

export function RootLayout() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100vh', overflow: 'hidden',
      background: '#06060b',
    }}>
      <TopNav />
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Outlet />
      </main>
    </div>
  )
}
