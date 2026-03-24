import { create } from 'zustand'

export interface Trade {
  id: number
  timestamp: number
  symbol: string
  side: string
  qty: number
  price: number
  pnl: number
  datetime_est: string
}

export interface TerminalState {
  positions: Record<string, number>
  account_details: {
    liquidation_value?: number
    cash_balance?: number
    day_pnl?: number
    buying_power?: number
  }
  daily_pnl: number
  win_rate: number
  rolling_pi_per_share: number
  max_drawdown: number
  cooldowns: {
    loss_cooldown_until: number
    pi_cooldown_until: number
    loss_cooldown_syms: string[]
  }
  trades: Trade[]
  lastUpdate: number
}

interface TerminalStoreState extends TerminalState {
  setState: (data: Partial<TerminalState>) => void
  appendTrades: (trades: Trade[]) => void
  reset: () => void
}

const defaultState: TerminalState = {
  positions: {},
  account_details: {},
  daily_pnl: 0,
  win_rate: 0,
  rolling_pi_per_share: 0,
  max_drawdown: 0,
  cooldowns: { loss_cooldown_until: 0, pi_cooldown_until: 0, loss_cooldown_syms: [] },
  trades: [],
  lastUpdate: 0,
}

export const useTerminalStore = create<TerminalStoreState>((set) => ({
  ...defaultState,
  setState: (data) => set((s) => ({ ...s, ...data, lastUpdate: Date.now() })),
  appendTrades: (newTrades) =>
    set((s) => {
      const existing = new Set(s.trades.map((t) => t.id))
      const fresh = newTrades.filter((t) => !existing.has(t.id))
      if (!fresh.length) return s
      return { trades: [...fresh, ...s.trades].slice(0, 500) }
    }),
  reset: () => set(defaultState),
}))
