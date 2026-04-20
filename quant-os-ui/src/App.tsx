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

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
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
