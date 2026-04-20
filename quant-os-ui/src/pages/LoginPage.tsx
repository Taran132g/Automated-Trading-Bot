import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authService } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

const BG = '#06060b'
const ACCENT = '#c8ff00'
const TEXT = '#f0f0f5'
const DIM = '#55556a'
const FAINT = '#33334a'
const SEC = '#8b8b9e'
const RED = '#ef4444'
const BORDER = 'rgba(255,255,255,0.06)'

export function LoginPage() {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const setToken = useAuthStore((s) => s.setToken)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (code.length !== 6) return
    setLoading(true)
    setError('')
    try {
      const res = await authService.login(code)
      setToken(res.data.token)
      navigate('/terminal')
    } catch {
      setError('Invalid TOTP code. Try again.')
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: `radial-gradient(ellipse at 50% 30%, #111118 0%, ${BG} 55%)`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Subtle dot grid */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none',
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.02) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
      }} />

      <div style={{ width: 380, position: 'relative', zIndex: 1 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 44 }}>
          <div style={{
            fontFamily: 'Inter, sans-serif', fontSize: '2.6rem', fontWeight: 900,
            color: ACCENT, letterSpacing: '-0.05em',
            textShadow: '0 0 80px rgba(200,255,0,0.1)',
          }}>
            QUANT<span style={{ color: FAINT }}>_</span><span style={{ color: TEXT }}>OS</span>
          </div>
          <div style={{ color: DIM, fontSize: '0.75rem', marginTop: 8, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
            Trading Terminal
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: 'rgba(12,12,20,0.8)',
          border: `1px solid ${BORDER}`,
          borderRadius: 16, padding: '36px 32px',
          backdropFilter: 'blur(20px)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
        }}>
          <div style={{
            fontSize: '0.66rem', color: DIM, textTransform: 'uppercase',
            letterSpacing: '0.14em', marginBottom: 24,
          }}>
            Authentication Required
          </div>

          <form onSubmit={handleSubmit}>
            <label style={{ fontSize: '0.78rem', color: SEC, display: 'block', marginBottom: 10 }}>
              6-Digit TOTP Code
            </label>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              style={{
                width: '100%',
                background: '#0a0a12',
                border: `1px solid ${error ? RED : BORDER}`,
                borderRadius: 10,
                padding: '16px 18px',
                fontSize: '2rem',
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 700,
                color: TEXT,
                textAlign: 'center',
                letterSpacing: '0.4em',
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.2s, box-shadow 0.2s',
              }}
              autoFocus
              onFocus={(e) => { if (!error) { e.target.style.borderColor = ACCENT; e.target.style.boxShadow = '0 0 0 1px rgba(200,255,0,0.1)' } }}
              onBlur={(e) => { e.target.style.borderColor = error ? RED : 'rgba(255,255,255,0.06)'; e.target.style.boxShadow = 'none' }}
            />

            {error && (
              <div style={{ color: RED, fontSize: '0.75rem', marginTop: 10 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={code.length !== 6 || loading}
              style={{
                width: '100%', marginTop: 24, padding: '14px',
                background: code.length === 6 && !loading ? ACCENT : '#191925',
                color: code.length === 6 && !loading ? '#06060b' : DIM,
                border: 'none', borderRadius: 10,
                fontSize: '0.82rem', fontWeight: 700,
                fontFamily: 'Inter, sans-serif',
                letterSpacing: '0.08em', textTransform: 'uppercase',
                cursor: code.length === 6 && !loading ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s',
              }}
            >
              {loading ? 'Authenticating...' : 'Authenticate'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
