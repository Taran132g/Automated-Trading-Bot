import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Cpu } from 'lucide-react'
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
      background: '#0B0E14',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <div style={{ width: 360 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Cpu size={28} color="#00FF99" />
            <span style={{ fontFamily: 'Roboto Mono', fontSize: '1.8rem', fontWeight: 700, color: '#00FF99', letterSpacing: 2 }}>
              QUANT_OS
            </span>
          </div>
          <div style={{ color: '#64748B', fontSize: '0.82rem' }}>Institutional Trading Terminal</div>
        </div>

        {/* Card */}
        <div style={{
          background: '#111827',
          border: '1px solid #1F2937',
          borderRadius: 12,
          padding: '32px 28px',
        }}>
          <div style={{ fontSize: '0.7rem', color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 20 }}>
            Authentication Required
          </div>

          <form onSubmit={handleSubmit}>
            <label style={{ fontSize: '0.78rem', color: '#94A3B8', display: 'block', marginBottom: 8 }}>
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
                background: '#0B0E14',
                border: `1px solid ${error ? '#EF4444' : '#1F2937'}`,
                borderRadius: 8,
                padding: '14px 16px',
                fontSize: '2rem',
                fontFamily: 'Roboto Mono',
                fontWeight: 700,
                color: '#F8FAFC',
                textAlign: 'center',
                letterSpacing: '0.4em',
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              autoFocus
              onFocus={(e) => { if (!error) e.target.style.borderColor = '#00FF99' }}
              onBlur={(e) => { e.target.style.borderColor = error ? '#EF4444' : '#1F2937' }}
            />

            {error && (
              <div style={{ color: '#EF4444', fontSize: '0.75rem', marginTop: 8 }}>{error}</div>
            )}

            <button
              type="submit"
              disabled={code.length !== 6 || loading}
              style={{
                width: '100%',
                marginTop: 20,
                padding: '13px',
                background: code.length === 6 && !loading ? '#00FF99' : '#1F2937',
                color: code.length === 6 && !loading ? '#0B0E14' : '#64748B',
                border: 'none',
                borderRadius: 8,
                fontSize: '0.82rem',
                fontWeight: 700,
                fontFamily: 'Inter',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                cursor: code.length === 6 && !loading ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
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
