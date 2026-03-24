import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const authenticated = useAuthStore((s) => s.authenticated)
  if (!authenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}
