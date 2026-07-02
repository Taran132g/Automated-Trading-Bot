import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { installDemoEnv } from './services/demo'

installDemoEnv()

// Live (non-demo) showcase: seed a token so the client-side ProtectedRoute does
// not gate the public read-only dashboard. Read endpoints need no auth; write
// endpoints are blocked server-side on the public box.
if (import.meta.env.VITE_DEMO !== '1' && !localStorage.getItem('quant_token')) {
  localStorage.setItem('quant_token', 'public')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
