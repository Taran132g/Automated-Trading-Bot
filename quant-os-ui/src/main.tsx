import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { DEMO, installDemoEnv } from './services/demo'

installDemoEnv()

function DemoBanner() {
  if (!DEMO) return null
  return (
    <div
      style={{
        position: 'fixed', bottom: 14, right: 14, zIndex: 9999,
        background: 'rgba(200,255,0,0.10)', border: '1px solid rgba(200,255,0,0.30)',
        color: '#c8ff00', borderRadius: 8, padding: '7px 13px',
        fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.08em',
        fontFamily: 'JetBrains Mono, monospace', backdropFilter: 'blur(6px)',
        pointerEvents: 'none',
      }}
    >
      DEMO · SAMPLE DATA
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <DemoBanner />
  </StrictMode>,
)
