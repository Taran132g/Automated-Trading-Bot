import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authService } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

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
      background: 'radial-gradient(ellipse at 50% 30%, #0a3030 0%, #031818 60%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Grid texture */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none',
        backgroundImage:
          'linear-gradient(rgba(171,255,2,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(171,255,2,0.03) 1px, transparent 1px)',
        backgroundSize: '80px 80px',
      }} />

      <div style={{ width: 360, position: 'relative', zIndex: 1 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontFamily: 'Inter, sans-serif', fontSize: '2.4rem', fontWeight: 900,
            color: '#abff02', letterSpacing: '-0.04em',
            textShadow: '0 0 60px rgba(171,255,2,0.15)',
          }}>
            QUANT<span style={{ color: '#e4f0e4' }}>_</span>OS
          </div>
          <div style={{ color: '#4a6a5a', fontSize: '0.78rem', marginTop: 6, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Trading Terminal
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: 'rgba(5,36,36,0.85)',
          border: '1px solid rgba(171,255,2,0.1)',
          borderRadius: 12, padding: '32px 28px',
          backdropFilter: 'blur(16px)',
        }}>
          <div style={{
            fontSize: '0.68rem', color: '#4a6a5a', textTransform: 'uppercase',
            letterSpacing: '0.12em', marginBottom: 20,
          }}>
            Authentication Required
          </div>

          <form onSubmit={handleSubmit}>
            <label style={{ fontSize: '0.78rem', color: '#7a9a8a', display: 'block', marginBottom: 8 }}>
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
                background: '#031818',
                border: `1px solid ${error ? '#ff4466' : 'rgba(171,255,2,0.1)'}`,
                borderRadius: 8,
                padding: '14px 16px',
                fontSize: '2rem',
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 700,
                color: '#e4f0e4',
                textAlign: 'center',
                letterSpacing: '0.4em',
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.2s',
              }}
              autoFocus
              onFocus={(e) => { if (!error) e.target.style.borderColor = '#abff02' }}
              onBlur={(e) => { e.target.style.borderColor = error ? '#ff4466' : 'rgba(171,255,2,0.1)' }}
            />

            {error && (
              <div style={{ color: '#ff4466', fontSize: '0.75rem', marginTop: 8 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={code.length !== 6 || loading}
              style={{
                width: '100%', marginTop: 20, padding: '13px',
                background: code.length === 6 && !loading ? '#abff02' : '#0d3d3d',
                color: code.length === 6 && !loading ? '#031818' : '#4a6a5a',
                border: 'none', borderRadius: 8,
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
