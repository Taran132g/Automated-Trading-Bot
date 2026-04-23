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
import { ScreenerPage } from '@/pages/ScreenerPage'
import { TelegramPage } from '@/pages/TelegramPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5000 } },
})

// ── ElevenLabs: preload "Welcome, Trader." in Arnold's cinematic voice ──
const ELEVEN_KEY     = 'sk_4496a2282e5e190984516e5212242f2f86e72f32b242e508'
const ELEVEN_VOICE   = 'JBFqnCBsd6RMkjVDRZzb' // George — warm captivating storyteller, deepest narrator tone

async function fetchWelcomeAudio(): Promise<HTMLAudioElement | null> {
  try {
    const res = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${ELEVEN_VOICE}`,
      {
        method: 'POST',
        headers: {
          'xi-api-key': ELEVEN_KEY,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: 'Welcome.',
          model_id: 'eleven_multilingual_v2',
          voice_settings: {
            stability: 0.22,        // very low = maximum expressiveness/drama
            similarity_boost: 0.90, // lock to George's deep warm character
            style: 0.85,            // full cinematic authority
            use_speaker_boost: true,
          },
        }),
      },
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      console.error('[ElevenLabs] API error', res.status, err)
      return null
    }
    const blob  = await res.blob()
    const url   = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.preload = 'auto'
    audio.playbackRate = 0.8   // uniform 0.8x speed — slower without the mid-word gaps
    return audio
  } catch (e) {
    console.error('[ElevenLabs] fetch failed', e)
    return null
  }
}

// Fallback: Web Speech if ElevenLabs unavailable
function speakFallback() {
  try {
    if (!window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const fire = (voices: SpeechSynthesisVoice[]) => {
      const utt = new SpeechSynthesisUtterance('Welcome, Trader.')
      utt.pitch = 0.6; utt.rate = 0.82; utt.volume = 1.0
      const v = voices.find(v => /daniel|david|google uk english male|alex|fred/i.test(v.name))
             ?? voices.find(v => v.lang.startsWith('en'))
             ?? voices[0]
      if (v) utt.voice = v
      window.speechSynthesis.speak(utt)
    }
    const voices = window.speechSynthesis.getVoices()
    if (voices.length > 0) { fire(voices) }
    else { window.speechSynthesis.addEventListener('voiceschanged', () => fire(window.speechSynthesis.getVoices()), { once: true }) }
  } catch { /* ignore */ }
}

// ── Cinematic sound: deep bass boom + mid whoosh + high confirmation sting ──
function playCinematicSound() {
  try {
    type AC = typeof AudioContext
    const Ctx: AC = window.AudioContext || (window as Window & { webkitAudioContext?: AC }).webkitAudioContext!
    if (!Ctx) return
    const ac = new Ctx()
    const now = ac.currentTime

    // Master compressor for cohesion
    const comp = ac.createDynamicsCompressor()
    comp.threshold.value = -14
    comp.ratio.value = 6
    comp.connect(ac.destination)

    // ── 1. Sub-bass thud (40 Hz) ── cinematic deep hit
    const sub = ac.createOscillator()
    const subG = ac.createGain()
    sub.connect(subG); subG.connect(comp)
    sub.type = 'sine'
    sub.frequency.setValueAtTime(55, now)
    sub.frequency.exponentialRampToValueAtTime(28, now + 0.5)
    subG.gain.setValueAtTime(0, now)
    subG.gain.linearRampToValueAtTime(0.6, now + 0.025)
    subG.gain.exponentialRampToValueAtTime(0.001, now + 1.1)
    sub.start(now); sub.stop(now + 1.2)

    // ── 2. Mid boom body (110 Hz) ──
    const boom = ac.createOscillator()
    const boomG = ac.createGain()
    boom.connect(boomG); boomG.connect(comp)
    boom.type = 'triangle'
    boom.frequency.setValueAtTime(110, now)
    boom.frequency.exponentialRampToValueAtTime(55, now + 0.4)
    boomG.gain.setValueAtTime(0, now)
    boomG.gain.linearRampToValueAtTime(0.22, now + 0.02)
    boomG.gain.exponentialRampToValueAtTime(0.001, now + 0.9)
    boom.start(now); boom.stop(now + 1.0)

    // ── 3. Noise slam (white noise burst, low-pass filtered) ──
    const bufLen = Math.floor(ac.sampleRate * 0.18)
    const noiseBuf = ac.createBuffer(1, bufLen, ac.sampleRate)
    const nd = noiseBuf.getChannelData(0)
    for (let i = 0; i < bufLen; i++) nd[i] = Math.random() * 2 - 1
    const noiseSrc = ac.createBufferSource()
    noiseSrc.buffer = noiseBuf
    const lpf = ac.createBiquadFilter()
    lpf.type = 'lowpass'; lpf.frequency.value = 320
    const noiseG = ac.createGain()
    noiseSrc.connect(lpf); lpf.connect(noiseG); noiseG.connect(comp)
    noiseG.gain.setValueAtTime(0.35, now)
    noiseG.gain.exponentialRampToValueAtTime(0.001, now + 0.18)
    noiseSrc.start(now); noiseSrc.stop(now + 0.2)

    // ── 4. Rising whoosh (noise + highpass, 0.1→2.0 s) ──
    const wLen = Math.floor(ac.sampleRate * 2)
    const wBuf = ac.createBuffer(1, wLen, ac.sampleRate)
    const wd = wBuf.getChannelData(0)
    for (let i = 0; i < wLen; i++) wd[i] = Math.random() * 2 - 1
    const whoosh = ac.createBufferSource()
    whoosh.buffer = wBuf
    const hpf = ac.createBiquadFilter()
    hpf.type = 'bandpass'
    hpf.frequency.setValueAtTime(400, now + 0.1)
    hpf.frequency.exponentialRampToValueAtTime(6000, now + 1.8)
    hpf.Q.value = 0.8
    const wG = ac.createGain()
    whoosh.connect(hpf); hpf.connect(wG); wG.connect(comp)
    wG.gain.setValueAtTime(0, now + 0.1)
    wG.gain.linearRampToValueAtTime(0.07, now + 0.25)
    wG.gain.linearRampToValueAtTime(0.12, now + 1.3)
    wG.gain.exponentialRampToValueAtTime(0.001, now + 2.0)
    whoosh.start(now + 0.1); whoosh.stop(now + 2.1)

    // ── 5. High confirmation sting (880→1760 Hz) at t=1.5 s ──
    const sting = ac.createOscillator()
    const stingG = ac.createGain()
    sting.connect(stingG); stingG.connect(comp)
    sting.type = 'sine'
    sting.frequency.setValueAtTime(880, now + 1.5)
    sting.frequency.linearRampToValueAtTime(1760, now + 1.57)
    stingG.gain.setValueAtTime(0, now + 1.5)
    stingG.gain.linearRampToValueAtTime(0.16, now + 1.52)
    stingG.gain.exponentialRampToValueAtTime(0.001, now + 2.0)
    sting.start(now + 1.5); sting.stop(now + 2.1)

    // ── 6. Harmonic shimmer on sting ──
    const shim = ac.createOscillator()
    const shimG = ac.createGain()
    shim.connect(shimG); shimG.connect(comp)
    shim.type = 'sine'
    shim.frequency.setValueAtTime(1760, now + 1.5)
    shim.frequency.linearRampToValueAtTime(3520, now + 1.6)
    shimG.gain.setValueAtTime(0, now + 1.5)
    shimG.gain.linearRampToValueAtTime(0.06, now + 1.52)
    shimG.gain.exponentialRampToValueAtTime(0.001, now + 1.95)
    shim.start(now + 1.5); shim.stop(now + 2.0)
  } catch {
    // Audio unavailable
  }
}

// ── Entry gate: cinematic Market Cipher aesthetic ──
function EntryGate({ onEnter, audioRef }: { onEnter: () => void; audioRef: React.MutableRefObject<HTMLAudioElement | null> }) {
  const [stage, setStage] = useState(0) // 0=dark, 1=letterbox, 2=text, 3=ready

  useEffect(() => {
    const t1 = setTimeout(() => setStage(1), 120)
    const t2 = setTimeout(() => setStage(2), 600)
    const t3 = setTimeout(() => setStage(3), 1400)
    // Preload ElevenLabs audio in background while user reads the gate screen
    fetchWelcomeAudio().then(a => { audioRef.current = a })
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [audioRef])

  return (
    <div
      onClick={onEnter}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: '#000008',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer', userSelect: 'none', overflow: 'hidden',
      }}
    >
      {/* Scan lines overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 10,
        backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px)',
      }} />

      {/* Radial green glow behind center */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 60% 45% at 50% 50%, rgba(34,197,94,0.07) 0%, transparent 70%)',
        opacity: stage >= 1 ? 1 : 0, transition: 'opacity 1.2s ease',
      }} />

      {/* Letterbox — top bar */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        height: stage >= 1 ? 80 : 0,
        background: '#000008',
        transition: 'height 0.55s cubic-bezier(0.4,0,0.2,1)',
        borderBottom: stage >= 1 ? '1px solid rgba(34,197,94,0.12)' : 'none',
        zIndex: 5,
      }} />

      {/* Letterbox — bottom bar */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: stage >= 1 ? 80 : 0,
        background: '#000008',
        transition: 'height 0.55s cubic-bezier(0.4,0,0.2,1)',
        borderTop: stage >= 1 ? '1px solid rgba(34,197,94,0.12)' : 'none',
        zIndex: 5,
      }} />

      {/* Top bar content */}
      {stage >= 1 && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 80,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 40px', zIndex: 6,
          opacity: stage >= 2 ? 1 : 0, transition: 'opacity 0.5s ease 0.3s',
        }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.56rem', color: 'rgba(34,197,94,0.4)', letterSpacing: '0.2em' }}>
            TNFund // SYSTEM BOOT
          </span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.56rem', color: 'rgba(34,197,94,0.4)', letterSpacing: '0.2em' }}>
            {new Date().toISOString().split('T')[0]}
          </span>
        </div>
      )}

      {/* Bottom bar content */}
      {stage >= 1 && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 80,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 6,
          opacity: stage >= 3 ? 1 : 0, transition: 'opacity 0.5s ease',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            animation: stage >= 3 ? 'breathe 2.2s ease-in-out infinite' : 'none',
          }}>
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: '#22c55e',
              boxShadow: '0 0 8px #22c55e',
              animation: 'dotBlink 1.1s ease-in-out infinite',
            }} />
            <span style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: '0.62rem',
              color: 'rgba(255,255,255,0.35)', letterSpacing: '0.3em',
              textTransform: 'uppercase',
            }}>
              Click anywhere to enter
            </span>
          </div>
        </div>
      )}

      {/* Main center content */}
      <div style={{
        position: 'relative', zIndex: 7, textAlign: 'center',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0,
      }}>
        {/* WELCOME text */}
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: 'clamp(0.7rem, 2vw, 0.95rem)',
          fontWeight: 300,
          letterSpacing: '0.7em',
          color: 'rgba(34,197,94,0.7)',
          textTransform: 'uppercase',
          marginBottom: 10,
          opacity: stage >= 2 ? 1 : 0,
          transform: stage >= 2 ? 'translateY(0)' : 'translateY(-10px)',
          transition: 'opacity 0.7s ease 0.1s, transform 0.7s ease 0.1s',
        }}>
          Welcome
        </div>

        {/* TRADER — large glitch text */}
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: 'clamp(4rem, 11vw, 8rem)',
          fontWeight: 900,
          letterSpacing: '-0.04em',
          lineHeight: 1,
          color: '#f0f0f5',
          position: 'relative',
          opacity: stage >= 2 ? 1 : 0,
          transform: stage >= 2 ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.97)',
          transition: 'opacity 0.8s cubic-bezier(0.16,1,0.3,1) 0.2s, transform 0.8s cubic-bezier(0.16,1,0.3,1) 0.2s',
          animation: stage >= 3 ? 'glitchMain 5s ease-in-out infinite' : 'none',
        }}>
          {/* Glitch layer 1 (cyan tint) */}
          <span style={{
            position: 'absolute', inset: 0,
            color: '#22d3ee', opacity: 0,
            animation: stage >= 3 ? 'glitchA 5s ease-in-out infinite' : 'none',
            pointerEvents: 'none',
          }} aria-hidden="true">TRADER</span>
          {/* Glitch layer 2 (red tint) */}
          <span style={{
            position: 'absolute', inset: 0,
            color: '#ef4444', opacity: 0,
            animation: stage >= 3 ? 'glitchB 5s ease-in-out infinite' : 'none',
            pointerEvents: 'none',
          }} aria-hidden="true">TRADER</span>
          TRADER
        </div>

        {/* Divider line */}
        <div style={{
          width: stage >= 2 ? 180 : 0,
          height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(200,255,0,0.6), transparent)',
          margin: '18px 0',
          transition: 'width 0.8s cubic-bezier(0.4,0,0.2,1) 0.5s',
        }} />

        {/* TNFund sub-brand */}
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: 'clamp(1.1rem, 2.5vw, 1.6rem)',
          fontWeight: 900, letterSpacing: '-0.02em',
          opacity: stage >= 2 ? 1 : 0,
          transform: stage >= 2 ? 'translateY(0)' : 'translateY(10px)',
          transition: 'opacity 0.7s ease 0.5s, transform 0.7s ease 0.5s',
        }}>
          <span style={{ color: '#c8ff00' }}>TN</span>
          <span style={{ color: 'rgba(240,240,245,0.5)' }}>Fund</span>
        </div>

        {/* Tagline */}
        <div style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '0.65rem', color: 'rgba(139,139,158,0.6)',
          letterSpacing: '0.18em', marginTop: 12,
          opacity: stage >= 3 ? 1 : 0,
          transition: 'opacity 0.6s ease',
        }}>
          ALGORITHMIC TRADING INFRASTRUCTURE
        </div>
      </div>

      <style>{`
        @keyframes glitchMain {
          0%, 88%, 100% { transform: translate(0,0) skew(0deg); }
          89%  { transform: translate(-2px, 0) skew(-0.4deg); }
          90%  { transform: translate(2px, 0)  skew(0.4deg); }
          91%  { transform: translate(0, 0)    skew(0deg); }
          94%  { transform: translate(-1px, 0) skew(0deg); }
          95%  { transform: translate(1px, 0)  skew(0deg); }
        }
        @keyframes glitchA {
          0%, 88%, 100% { opacity: 0; transform: translate(0,0); }
          89%  { opacity: 0.5; transform: translate(-4px, 1px); clip-path: inset(10% 0 60% 0); }
          90%  { opacity: 0;   transform: translate(0,0); }
          94%  { opacity: 0.3; transform: translate(3px, -1px); clip-path: inset(50% 0 10% 0); }
          95%  { opacity: 0; }
        }
        @keyframes glitchB {
          0%, 88%, 100% { opacity: 0; transform: translate(0,0); }
          89%  { opacity: 0;   transform: translate(0,0); }
          90%  { opacity: 0.4; transform: translate(4px, -1px); clip-path: inset(30% 0 40% 0); }
          91%  { opacity: 0; }
          94%  { opacity: 0;  }
          95%  { opacity: 0.25; transform: translate(-3px, 1px); clip-path: inset(60% 0 5% 0); }
          96%  { opacity: 0; }
        }
        @keyframes dotBlink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }
        @keyframes breathe {
          0%, 100% { opacity: 0.7; }
          50%       { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ── Circle reveal: dark overlay iris-opens to expose the site ──
function CircleReveal({ onDone, audioRef }: { onDone: () => void; audioRef: React.MutableRefObject<HTMLAudioElement | null> }) {
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
    const maxR = Math.hypot(cx, cy) + 20

    const EXPAND_DUR = 1700
    const FADE_DUR   = 350

    const DOT_COUNT  = 14
    const DOT_ANGLES = Array.from({ length: DOT_COUNT }, (_, i) => (i / DOT_COUNT) * Math.PI * 2)
    const DOT_SIZES  = DOT_ANGLES.map((_, i) => (i % 3 === 0 ? 3 : 2))

    const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4)

    let startTs: number | null = null
    let rafId: number

    playCinematicSound()
    setTimeout(() => {
      if (audioRef.current) {
        audioRef.current.play().catch(() => speakFallback())
      } else {
        speakFallback()
      }
    }, 120)

    const frame = (ts: number) => {
      if (startTs === null) startTs = ts
      const elapsed = ts - startTs

      const expandT = Math.min(elapsed / EXPAND_DUR, 1)
      const fadeT   = elapsed > EXPAND_DUR ? Math.min((elapsed - EXPAND_DUR) / FADE_DUR, 1) : 0

      const eased  = easeOutQuart(expandT)
      const radius = eased * maxR

      canvas.style.opacity = fadeT > 0 ? String(1 - fadeT) : '1'

      if (textRef.current) {
        textRef.current.style.opacity = String(Math.max(0, 1 - expandT / 0.55))
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Dark overlay with circular iris hole
      ctx.save()
      ctx.fillStyle = '#000008'
      ctx.beginPath()
      ctx.rect(0, 0, canvas.width, canvas.height)
      if (radius > 1) ctx.arc(cx, cy, radius, 0, Math.PI * 2, false)
      ctx.fill('evenodd')
      ctx.restore()

      // Scan lines on overlay
      ctx.save()
      ctx.fillStyle = 'rgba(0,0,0,0.12)'
      for (let y = 0; y < canvas.height; y += 4) {
        ctx.fillRect(0, y, canvas.width, 2)
      }
      ctx.restore()

      // Green inner glow ring just inside the edge
      if (expandT > 0.02 && expandT < 0.99) {
        const innerGlowGrad = ctx.createRadialGradient(cx, cy, radius - 18, cx, cy, radius)
        innerGlowGrad.addColorStop(0, 'transparent')
        innerGlowGrad.addColorStop(1, `rgba(34,197,94,${0.18 * (1 - expandT * 0.7)})`)
        ctx.save()
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.fillStyle = innerGlowGrad
        ctx.fill()
        ctx.restore()
      }

      // Lime edge ring
      if (expandT > 0.01 && expandT < 0.99) {
        ctx.save()
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(200,255,0,${0.5 * (1 - expandT * 0.65)})`
        ctx.lineWidth = 1.5
        ctx.stroke()
        ctx.restore()
      }

      // White dots with glow
      if (expandT > 0.02 && expandT < 0.97) {
        DOT_ANGLES.forEach((angle, i) => {
          const x = cx + radius * Math.cos(angle)
          const y = cy + radius * Math.sin(angle)
          if (x < -12 || x > canvas.width + 12 || y < -12 || y > canvas.height + 12) return

          const grad = ctx.createRadialGradient(x, y, 0, x, y, 12)
          grad.addColorStop(0, 'rgba(200,255,0,0.45)')
          grad.addColorStop(1, 'rgba(200,255,0,0)')
          ctx.fillStyle = grad
          ctx.beginPath()
          ctx.arc(x, y, 12, 0, Math.PI * 2)
          ctx.fill()

          ctx.beginPath()
          ctx.arc(x, y, DOT_SIZES[i], 0, Math.PI * 2)
          ctx.fillStyle = 'rgba(255,255,255,0.95)'
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
      <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0 }} />
      <div
        ref={textRef}
        style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none', userSelect: 'none',
        }}
      >
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: 'clamp(3rem, 8vw, 5.5rem)',
          fontWeight: 900, letterSpacing: '-0.04em', color: '#f0f0f5', lineHeight: 1,
        }}>
          <span style={{ color: '#c8ff00' }}>TN</span>Fund
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const firstVisit = !sessionStorage.getItem('qos_welcomed')
  const [phase, setPhase] = useState<'gate' | 'reveal' | 'done'>(
    firstVisit ? 'gate' : 'done',
  )
  const audioRef = useRef<HTMLAudioElement | null>(null)

  return (
    <QueryClientProvider client={queryClient}>
      {phase === 'gate' && (
        <EntryGate audioRef={audioRef} onEnter={() => setPhase('reveal')} />
      )}
      {phase === 'reveal' && (
        <CircleReveal
          audioRef={audioRef}
          onDone={() => {
            sessionStorage.setItem('qos_welcomed', '1')
            setPhase('done')
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
            <Route path="/screener" element={<ScreenerPage />} />
            <Route path="/telegram" element={<TelegramPage />} />
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
