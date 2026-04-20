import { useState, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Menu } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { adminService, terminalService } from '@/services/api'

const BORDER = 'rgba(255,255,255,0.06)'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const FAINT = '#33334a'
const ACCENT = '#c8ff00'
const BG0 = '#06060b'
const BG_BAR = '#08080e'

function isMarketOpen() {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const d = et.getDay()
  const mins = et.getHours() * 60 + et.getMinutes()
  return d >= 1 && d <= 5 && mins >= 570 && mins < 960
}

function TopBar({ onMobileMenu }: { onMobileMenu: () => void }) {
  const [time, setTime] = useState('')
  const [open, setOpen] = useState(false)

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
    refetchInterval: 10000,
    retry: false,
  })

  const { data: statusData } = useQuery({
    queryKey: ['admin-status'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  })

  const acctVal = scalperState?.account_details?.liquidation_value
  const dayPnl = scalperState?.daily_pnl
  const backendOnline = statusData?.loop_running || statusData?.trader_running || statusData?.grok_running

  return (
    <div style={{
      height: 44,
      flexShrink: 0,
      display: 'flex',
      alignItems: 'stretch',
      background: BG_BAR,
      borderBottom: `1px solid ${BORDER}`,
    }}>
      {/* Brand block — matches sidebar width */}
      <div style={{
        width: 200,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        borderRight: `1px solid ${BORDER}`,
        gap: 10,
      }}>
        <button
          className="mobile-menu-btn"
          onClick={onMobileMenu}
          style={{
            display: 'none',
            background: 'none',
            border: 'none',
            color: SEC,
            cursor: 'pointer',
            padding: 0,
            lineHeight: 1,
          }}
        >
          <Menu size={16} />
        </button>
        <span style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.88rem',
          fontWeight: 800,
          color: ACCENT,
          letterSpacing: '-0.02em',
        }}>
          QUANT<span style={{ color: FAINT }}>_</span><span style={{ color: TEXT }}>OS</span>
        </span>
      </div>

      {/* Live metrics strip */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'stretch', justifyContent: 'flex-end' }}>
        {acctVal != null && (
          <div style={{
            padding: '0 22px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            borderRight: `1px solid ${BORDER}`,
          }}>
            <div style={{ fontSize: '0.5rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 2 }}>
              Account
            </div>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.82rem',
              fontWeight: 700,
              color: TEXT,
            }}>
              ${acctVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
        )}
        {dayPnl != null && (
          <div style={{
            padding: '0 22px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            borderRight: `1px solid ${BORDER}`,
          }}>
            <div style={{ fontSize: '0.5rem', color: DIM, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 2 }}>
              Day P&L
            </div>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.82rem',
              fontWeight: 700,
              color: dayPnl >= 0 ? GREEN : RED,
            }}>
              {dayPnl >= 0 ? '+' : ''}${Math.abs(dayPnl).toFixed(2)}
            </div>
          </div>
        )}
        <div style={{
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          borderRight: `1px solid ${BORDER}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: backendOnline ? GREEN : RED,
              boxShadow: backendOnline ? `0 0 5px ${GREEN}` : 'none',
              display: 'inline-block',
            }} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: backendOnline ? SEC : DIM }}>
              {backendOnline ? 'SYS ON' : 'SYS OFF'}
            </span>
          </div>
        </div>
        <div style={{
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          <span style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '0.78rem',
            color: SEC,
            letterSpacing: '0.02em',
          }}>
            {time} ET
          </span>
          <span style={{
            fontSize: '0.56rem',
            fontWeight: 700,
            letterSpacing: '0.1em',
            padding: '3px 9px',
            borderRadius: 4,
            background: open ? 'rgba(34,197,94,0.07)' : 'rgba(239,68,68,0.07)',
            border: `1px solid ${open ? 'rgba(34,197,94,0.18)' : 'rgba(239,68,68,0.18)'}`,
            color: open ? GREEN : RED,
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            MKT {open ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
      </div>
    </div>
  )
}

export function RootLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden', background: BG0 }}>
      <TopBar onMobileMenu={() => setSidebarOpen(true)} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.65)',
              zIndex: 40,
            }}
          />
        )}

        <div className={`sidebar-wrapper ${sidebarOpen ? 'open' : ''}`}>
          <Sidebar onClose={() => setSidebarOpen(false)} />
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
            left: -200px;
            top: 44px;
            bottom: 0;
            z-index: 50;
            transition: left 0.28s cubic-bezier(0.4, 0, 0.2, 1);
          }
          .sidebar-wrapper.open { left: 0; }
          .mobile-menu-btn { display: flex !important; }
        }
      `}</style>
    </div>
  )
}
