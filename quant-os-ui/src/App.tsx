import { useState, useEffect } from 'react'
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

function WelcomeSplash({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3100)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: '#06060b',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      zIndex: 9999,
      animation: 'splashOut 0.7s ease-in-out 2.4s both',
      pointerEvents: 'none',
    }}>
      <div style={{ textAlign: 'center', animation: 'splashIn 0.9s cubic-bezier(0.16,1,0.3,1) both' }}>
        <div style={{
          fontSize: '0.62rem',
          letterSpacing: '0.55em',
          color: '#55556a',
          textTransform: 'uppercase',
          marginBottom: 22,
          animation: 'splashFadeIn 0.7s ease 0.4s both',
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
          fontSize: '0.76rem',
          color: '#55556a',
          marginTop: 16,
          letterSpacing: '0.06em',
          animation: 'splashFadeIn 0.7s ease 0.7s both',
        }}>
          Algorithmic Trading Infrastructure
        </div>
        <div style={{
          width: 0,
          height: 1,
          background: 'rgba(200,255,0,0.5)',
          margin: '22px auto 0',
          animation: 'splashLine 0.6s cubic-bezier(0.4,0,0.2,1) 1s both',
        }} />
      </div>
      <style>{`
        @keyframes splashIn {
          from { opacity: 0; transform: translateY(24px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
        @keyframes splashFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes splashLine {
          from { width: 0;    opacity: 0; }
          to   { width: 48px; opacity: 1; }
        }
        @keyframes splashOut {
          from { opacity: 1; }
          to   { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

export default function App() {
  const [showSplash, setShowSplash] = useState(
    () => !sessionStorage.getItem('qos_welcomed'),
  )

  const handleSplashDone = () => {
    sessionStorage.setItem('qos_welcomed', '1')
    setShowSplash(false)
  }

  return (
    <QueryClientProvider client={queryClient}>
      {showSplash && <WelcomeSplash onDone={handleSplashDone} />}
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
