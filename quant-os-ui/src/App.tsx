import { useState, useEffect, useRef } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProtectedRoute } from '@/components/layout/ProtectedRoute'
import { RootLayout } from '@/components/layout/RootLayout'
import { LoginPage } from '@/pages/LoginPage'
import { HomePage } from '@/pages/HomePage'
import { TerminalPage } from '@/pages/TerminalPage'
import { BacktestPage } from '@/pages/BacktestPage'
import { PatternLabPage } from '@/pages/PatternLabPage'
import { PatternPage } from '@/pages/PatternPage'
import { ComparisonPage } from '@/pages/ComparisonPage'
import { GrokPage } from '@/pages/GrokPage'
import { AgentsPage } from '@/pages/AgentsPage'
import { AdminPage } from '@/pages/AdminPage'
import { SignalsPage } from '@/pages/SignalsPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5000 } },
})

function playOpeningSound() {
  try {
    type AC = typeof AudioContext
    const AudioCtx: AC =
      window.AudioContext ||
      (window as Window & { webkitAudioContext?: AC }).webkitAudioContext!
    if (!AudioCtx) return
    const ac = new AudioCtx()
    const now = ac.currentTime

    // ── Opening ping: quick 440→880 Hz burst ──
    const ping = ac.createOscillator()
    const pingG = ac.createGain()
    ping.connect(pingG); pingG.connect(ac.destination)
    ping.type = 'sine'
    ping.frequency.setValueAtTime(440, now)
    ping.frequency.linearRampToValueAtTime(880, now + 0.06)
    pingG.gain.setValueAtTime(0, now)
    pingG.gain.linearRampToValueAtTime(0.18, now + 0.01)
    pingG.gain.exponentialRampToValueAtTime(0.001, now + 0.35)
    ping.start(now); ping.stop(now + 0.4)

    // ── Rising sweep: 90 → 680 Hz over 1.5 s ──
    const osc1 = ac.createOscillator()
    const g1 = ac.createGain()
    osc1.connect(g1); g1.connect(ac.destination)
    osc1.type = 'sine'
    osc1.frequency.setValueAtTime(90, now)
    osc1.frequency.exponentialRampToValueAtTime(680, now + 1.5)
    g1.gain.setValueAtTime(0, now)
    g1.gain.linearRampToValueAtTime(0.11, now + 0.08)
    g1.gain.linearRampToValueAtTime(0.04, now + 1.3)
    g1.gain.linearRampToValueAtTime(0, now + 1.9)
    osc1.start(now); osc1.stop(now + 2)

    // ── Octave harmonic: 180 → 1360 Hz ──
    const osc2 = ac.createOscillator()
    const g2 = ac.createGain()
    osc2.connect(g2); g2.connect(ac.destination)
    osc2.type = 'sine'
    osc2.frequency.setValueAtTime(180, now)
    osc2.frequency.exponentialRampToValueAtTime(1360, now + 1.5)
    g2.gain.setValueAtTime(0, now)
    g2.gain.linearRampToValueAtTime(0.04, now + 0.1)
    g2.gain.linearRampToValueAtTime(0, now + 1.9)
    osc2.start(now); osc2.stop(now + 2)

    // ── Noise whoosh: bandpass sweep ──
    const bufLen = Math.floor(ac.sampleRate * 2)
    const buf = ac.createBuffer(1, bufLen, ac.sampleRate)
    const data = buf.getChannelData(0)
    for (let i = 0; i < bufLen; i++) data[i] = Math.random() * 2 - 1
    const noise = ac.createBufferSource()
    noise.buffer = buf
    const bpf = ac.createBiquadFilter()
    bpf.type = 'bandpass'
    bpf.frequency.setValueAtTime(300, now)
    bpf.frequency.exponentialRampToValueAtTime(4000, now + 1.5)
    bpf.Q.value = 1.5
    const gn = ac.createGain()
    noise.connect(bpf); bpf.connect(gn); gn.connect(ac.destination)
    gn.gain.setValueAtTime(0, now)
    gn.gain.linearRampToValueAtTime(0.025, now + 0.05)
    gn.gain.linearRampToValueAtTime(0, now + 1.6)
    noise.start(now); noise.stop(now + 2)
  } catch {
    // Audio unavailable — silent fallback
  }
}

function CircleReveal({ onDone }: { onDone: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textRef   = useRef<HTMLDivElement>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width  = window.innerWidth
    canvas.height = window.innerHeight

    const cx   = canvas.width  / 2
    const cy   = canvas.height / 2
    const maxR = Math.hypot(cx, cy) + 20   // radius to cover all 4 corners

    const EXPAND_DUR = 1700  // ms: circle opening
    const FADE_DUR   = 350   // ms: overlay fade-out after circle is open

    const DOT_COUNT  = 14
    const DOT_ANGLES = Array.from({ length: DOT_COUNT }, (_, i) => (i / DOT_COUNT) * Math.PI * 2)
    // Every 3rd dot is slightly larger
    const DOT_SIZES  = DOT_ANGLES.map((_, i) => (i % 3 === 0 ? 3 : 2))

    const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4)

    let startTs: number | null = null
    let rafId: number

    playOpeningSound()

    const frame = (ts: number) => {
      if (startTs === null) startTs = ts
      const elapsed = ts - startTs

      const expandT = Math.min(elapsed / EXPAND_DUR, 1)
      const fadeT   = elapsed > EXPAND_DUR
        ? Math.min((elapsed - EXPAND_DUR) / FADE_DUR, 1)
        : 0

      const eased  = easeOutQuart(expandT)
      const radius = eased * maxR

      // Fade out the entire canvas after circle fully opens
      canvas.style.opacity = fadeT > 0 ? String(1 - fadeT) : '1'

      // Text fades out in the first 55% of the expansion
      if (textRef.current) {
        textRef.current.style.opacity = String(Math.max(0, 1 - expandT / 0.55))
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // ── Dark overlay with circular cutout (evenodd creates the hole) ──
      ctx.save()
      ctx.fillStyle = '#06060b'
      ctx.beginPath()
      ctx.rect(0, 0, canvas.width, canvas.height)
      if (radius > 1) ctx.arc(cx, cy, radius, 0, Math.PI * 2, false)
      ctx.fill('evenodd')
      ctx.restore()

      // ── Lime circle edge ring ──
      if (expandT > 0.01 && expandT < 0.99) {
        ctx.save()
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(200,255,0,${0.35 * (1 - expandT * 0.6)})`
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.restore()
      }

      // ── White dots on circle perimeter ──
      if (expandT > 0.02 && expandT < 0.97) {
        DOT_ANGLES.forEach((angle, i) => {
          const x = cx + radius * Math.cos(angle)
          const y = cy + radius * Math.sin(angle)

          // Skip dots that are off-screen
          if (x < -12 || x > canvas.width + 12 || y < -12 || y > canvas.height + 12) return

          // Glow halo
          const grad = ctx.createRadialGradient(x, y, 0, x, y, 10)
          grad.addColorStop(0, 'rgba(255,255,255,0.5)')
          grad.addColorStop(1, 'rgba(255,255,255,0)')
          ctx.fillStyle = grad
          ctx.beginPath()
          ctx.arc(x, y, 10, 0, Math.PI * 2)
          ctx.fill()

          // Core dot
          ctx.beginPath()
          ctx.arc(x, y, DOT_SIZES[i], 0, Math.PI * 2)
          ctx.fillStyle = 'rgba(255,255,255,0.92)'
          ctx.fill()
        })
      }

      if (elapsed < EXPAND_DUR + FADE_DUR) {
        rafId = requestAnimationFrame(frame)
      } else {
        onDoneRef.current()
      }
    }

    rafId = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9998, pointerEvents: 'none' }}>
      {/* Canvas: circle animation */}
      <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Centered text — fades as circle opens */}
      <div
        ref={textRef}
        style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none',
          userSelect: 'none',
        }}
      >
        <div style={{
          fontSize: '0.6rem',
          letterSpacing: '0.5em',
          color: '#55556a',
          textTransform: 'uppercase',
          marginBottom: 20,
        }}>
          Welcome Trader
        </div>
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '3.8rem',
          fontWeight: 900,
          letterSpacing: '-0.04em',
          color: '#f0f0f5',
          lineHeight: 1,
        }}>
          QUANT<span style={{ color: '#33334a' }}>_</span><span style={{ color: '#c8ff00' }}>OS</span>
        </div>
        <div style={{
          fontSize: '0.74rem',
          color: '#55556a',
          marginTop: 14,
          letterSpacing: '0.06em',
        }}>
          Algorithmic Trading Infrastructure
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [showReveal, setShowReveal] = useState(
    () => !sessionStorage.getItem('qos_welcomed'),
  )

  return (
    <QueryClientProvider client={queryClient}>
      {showReveal && (
        <CircleReveal
          onDone={() => {
            sessionStorage.setItem('qos_welcomed', '1')
            setShowReveal(false)
          }}
        />
      )}
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RootLayout />}>
            <Route index element={<HomePage />} />
            <Route path="/scalper" element={<TerminalPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/pattern" element={<PatternPage />} />
            <Route path="/patterns" element={<PatternLabPage />} />
            <Route path="/comparison" element={<ComparisonPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/grok" element={<GrokPage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/signals" element={<SignalsPage />} />
            <Route path="/admin" element={
              <ProtectedRoute>
                <AdminPage />
              </ProtectedRoute>
            } />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
