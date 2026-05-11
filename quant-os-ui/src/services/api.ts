import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('quant_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('quant_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const authService = {
  login: (totp_code: string) =>
    api.post<{ token: string; expires_at: string }>('/auth/login', { totp_code }),
  logout: () => api.post('/auth/logout'),
  verify: () => api.get('/auth/verify'),
}

export const terminalService = {
  getState: () => api.get('/terminal/state'),
  getTrades: (date = 'today') => api.get(`/terminal/trades?date=${date}`),
  getEquityCurve: (range = 'today') => api.get(`/terminal/equity-curve?range=${range}`),
  getAlerts: (limit = 50) => api.get(`/terminal/alerts?limit=${limit}`),
  getPositions: () => api.get('/terminal/positions'),
}

export const analyticsService = {
  getSummary: () => api.get('/analytics/summary'),
  getDailyPnL: () => api.get('/analytics/daily-pnl'),
  getWinLoss: () => api.get('/analytics/win-loss'),
  parseHistory: (raw_text: string) => api.post('/analytics/parse-history', { raw_text }),
}

export const paperService = {
  getState: () => api.get('/paper/state'),
  getTrades: (range = 'today') => api.get(`/paper/trades?range=${range}`),
  getEquityCurve: (range = 'today') => api.get(`/paper/equity-curve?range=${range}`),
  getPerformance: () => api.get('/paper/performance'),
}

export const comparisonService = {
  getStats: (range = 'all') => api.get(`/comparison/stats?range=${range}`),
}

export const logsService = {
  tail: (lines = 1000, symbol = '', levels = 'INFO,WARNING,ERROR') =>
    api.get(`/logs/tail?lines=${lines}&symbol=${encodeURIComponent(symbol)}&levels=${encodeURIComponent(levels)}`),
}

export const adminService = {
  getStatus: () => api.get('/admin/status'),
  start: () => api.post('/admin/start'),
  stop: () => api.post('/admin/stop'),
  flatten: () => api.post('/admin/flatten'),
  fullShutdown: () => api.post('/admin/full-shutdown'),
  getSchwabAuthUrl: () => api.get('/admin/schwab/auth-url'),
  saveSchwabTokens: (callback_url: string) =>
    api.post('/admin/schwab/save-tokens', { callback_url }),
}

export const configService = {
  get: () => api.get('/config'),
  update: (cfg: Record<string, unknown>) => api.put('/config', cfg),
}

export const agentService = {
  getReports: (agent = 'all', limit = 50) =>
    api.get(`/agents/reports?agent=${agent}&limit=${limit}`),
  uploadPostMarket: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/agents/upload-post-market', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  runAgent: (agentName: string, totpCode: string) => {
    const fd = new FormData()
    fd.append('agent_name', agentName)
    fd.append('totp_code', totpCode)
    return api.post<{ success: boolean; agent: string; message: string }>(
      '/agents/run-agent', fd, { headers: { 'Content-Type': 'multipart/form-data' } }
    )
  },
}

export interface QuoteItem {
  symbol: string
  price: number
  change_pct: number
}

export const marketService = {
  getQuotes: () => api.get<{ top: QuoteItem[]; bottom: QuoteItem[] }>('/market/quotes'),
}

export const telegramService = {
  getChannels: () => api.get('/telegram/channels'),
  getMessages: (limit = 100, channel = 'all', afterId = 0) =>
    api.get(`/telegram/messages?limit=${limit}&channel=${encodeURIComponent(channel)}&after_id=${afterId}`),
}

export const screenerService = {
  getStatus: () => api.get('/screener/status'),
  getWatchlist: (minScore = 0, minPrice = 0.80, maxPrice = 1.15) =>
    api.get(`/screener/watchlist?min_score=${minScore}&min_price=${minPrice}&max_price=${maxPrice}&limit=100`),
  getAlerts: (alertType = 'all', limit = 50) =>
    api.get(`/screener/alerts?alert_type=${alertType}&limit=${limit}`),
  getHistory: (symbol: string, minutes = 30) =>
    api.get(`/screener/history/${symbol}?minutes=${minutes}`),
}
