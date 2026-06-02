/**
 * Demo mode — lets the dashboard run as a public portfolio piece with no backend.
 *
 * Enabled at build time with VITE_DEMO=1. When on:
 *   • the axios `api` instance is served from in-memory fixtures (see demoAdapter)
 *   • window.WebSocket is shimmed so the live Terminal / Signals / Telegram feeds animate
 *   • a fake auth token is seeded so ProtectedRoute lets you in
 *
 * The numbers below are REAL — drawn from the live run (Feb 27 – Mar 16 2026) recorded
 * in penny_basing.db / STRATEGY_ANALYSIS.md and the Schwab trade exports: the actual
 * flip-only L2 order-book imbalance scalper traded on AAL, F, BBAI, RIG, SOXS, OPEN.
 * Account values are rounded; nothing here connects to a live brokerage account.
 */
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

export const DEMO = import.meta.env.VITE_DEMO === '1'

// ─────────────────────────────── Fixtures ───────────────────────────────

// Real account scale (~$26K leveraged). "Today" reconstructs Mar 13 — the best
// recent session: 59 trades, 69.5% win rate, +$35.98.
const ACCOUNT = {
  liquidation_value: 26012.4,
  cash_balance: 25180.55,
  day_pnl: 35.98,
  buying_power: 43480.2,
}
const DAY_PNL = 35.98
const DAY_WIN_RATE = 69.5

interface DemoTrade {
  id: number
  timestamp: number
  symbol: string
  side: string
  qty: number
  price: number
  pnl: number
  datetime_est: string
}

// Representative fills from the Mar 13 session — real symbols, real price levels,
// flip-only long (BUY/SELL) and short (SHORT/COVER) round trips on a $26K book.
const TRADES: DemoTrade[] = [
  { symbol: 'F',    side: 'COVER', qty: 600,  price: 13.226, pnl: 8.40,  t: '15:41:08' },
  { symbol: 'F',    side: 'SHORT', qty: 600,  price: 13.240, pnl: 0,     t: '15:33:52' },
  { symbol: 'AAL',  side: 'SELL',  qty: 500,  price: 12.531, pnl: 9.50,  t: '15:18:44' },
  { symbol: 'AAL',  side: 'BUY',   qty: 500,  price: 12.512, pnl: 0,     t: '15:09:21' },
  { symbol: 'BBAI', side: 'SELL',  qty: 1000, price: 3.901,  pnl: -7.00, t: '14:46:55' },
  { symbol: 'BBAI', side: 'BUY',   qty: 1000, price: 3.908,  pnl: 0,     t: '14:38:13' },
  { symbol: 'RIG',  side: 'COVER', qty: 400,  price: 6.292,  pnl: 5.20,  t: '13:52:30' },
  { symbol: 'RIG',  side: 'SHORT', qty: 400,  price: 6.305,  pnl: 0,     t: '13:44:02' },
  { symbol: 'F',    side: 'SELL',  qty: 800,  price: 13.224, pnl: 15.20, t: '12:31:19' },
  { symbol: 'F',    side: 'BUY',   qty: 800,  price: 13.205, pnl: 0,     t: '12:22:41' },
  { symbol: 'AAL',  side: 'COVER', qty: 500,  price: 12.486, pnl: 6.00,  t: '11:18:07' },
  { symbol: 'AAL',  side: 'SHORT', qty: 500,  price: 12.498, pnl: 0,     t: '11:09:33' },
].map((r, i) => ({
  id: 1000 - i,
  timestamp: Date.now() / 1000 - i * 240,
  symbol: r.symbol,
  side: r.side,
  qty: r.qty,
  price: r.price,
  pnl: r.pnl,
  datetime_est: r.t,
}))

// One open long carried into the close (AAL 500).
const OPEN_POSITIONS: Record<string, number> = { AAL: 500 }

// Mar 13 intraday cumulative P&L → +$35.98.
const EQUITY_TODAY = [
  ['09:32', 0], ['09:50', 8], ['10:10', -4], ['10:40', 6], ['11:18', 14],
  ['12:31', 29], ['13:00', 24], ['13:52', 29], ['14:47', 22], ['15:18', 31],
  ['15:41', 40], ['15:58', 35.98],
].map(([label, value], i) => ({
  timestamp: Date.now() / 1000 - (12 - i) * 300,
  value: value as number,
  datetime_est: label as string,
}))

// Real daily closes Feb 27 – Mar 13 (from STRATEGY_ANALYSIS.md). Peak +$438, the
// Mar 6 BBAI blowup (−$466.85), choppy recovery to net ≈ −$16.
const DAILY_BARS = [
  { date: '02-27', daily_pnl: -7.0,    trade_count: 44 },
  { date: '03-02', daily_pnl: 423.45,  trade_count: 32 },
  { date: '03-03', daily_pnl: -1.65,   trade_count: 25 },
  { date: '03-04', daily_pnl: -30.75,  trade_count: 14 },
  { date: '03-05', daily_pnl: 54.3,    trade_count: 17 },
  { date: '03-06', daily_pnl: -466.85, trade_count: 18 },
  { date: '03-09', daily_pnl: -30.84,  trade_count: 58 },
  { date: '03-10', daily_pnl: 17.88,   trade_count: 146 },
  { date: '03-11', daily_pnl: -9.7,    trade_count: 83 },
  { date: '03-12', daily_pnl: 3.92,    trade_count: 39 },
  { date: '03-13', daily_pnl: 35.98,   trade_count: 59 },
]

// Cumulative day-close equity (matches DAILY_BARS).
const EQUITY_ALLTIME = (() => {
  let acc = 0
  return DAILY_BARS.map((b) => {
    acc = Math.round((acc + b.daily_pnl) * 100) / 100
    return { timestamp: Date.now() / 1000, value: acc, datetime_est: b.date }
  })
})()

// Real aggregate over 591 closing trades.
const SCALP_STATS = {
  total_pnl: -16.08,
  win_rate: 54.7,
  pnl_per_share: -0.0003,
  avg_pnl_per_trade: -0.027,
  profit_factor: 0.99,
  avg_win: 4.85,
  avg_loss: -5.91,
  max_consec_loss: 6,
  total_trades: 591,
}

// Cumulative-by-trade curve tracing the real arc: ramp to the +$510 peak, the
// Mar 6 crash, then chop back toward breakeven.
const SCALP_CURVE = [
  0, 55, 140, 235, 360, 438, 472, 510, 498, 470, 360, 120,
  -28, -52, -38, -60, -44, -58, -47, -36, -51, -40, -27, -16,
].map((value, i) => ({ label: `#${i + 1}`, value }))

// Real per-symbol breakdown (Verdict column from the analysis).
const SYMBOL_BREAKDOWN = [
  { symbol: 'AAL',  win_rate: 56.3, total_pnl: 7.24,   trades: 128, pnl_per_share: 0.0006 },
  { symbol: 'F',    win_rate: 58.3, total_pnl: 3.77,   trades: 24,  pnl_per_share: 0.0021 },
  { symbol: 'OPEN', win_rate: 58.7, total_pnl: -5.7,   trades: 196, pnl_per_share: -0.0004 },
  { symbol: 'RIG',  win_rate: 47.1, total_pnl: -3.61,  trades: 17,  pnl_per_share: -0.0021 },
  { symbol: 'BBAI', win_rate: 50.4, total_pnl: -17.79, trades: 226, pnl_per_share: -0.0008 },
]

const MARKET_QUOTES = {
  top: [
    { symbol: 'SOXS', price: 7.81,  change_pct: 3.4 },
    { symbol: 'AAL',  price: 12.53, change_pct: 1.8 },
    { symbol: 'F',    price: 13.22, change_pct: 1.1 },
  ],
  bottom: [
    { symbol: 'BBAI', price: 3.9,  change_pct: -2.1 },
    { symbol: 'OPEN', price: 1.42, change_pct: -1.4 },
    { symbol: 'RIG',  price: 6.28, change_pct: -0.9 },
  ],
}

// L2 imbalance event tape — real symbols, real price levels, ratio = bid/ask depth.
const LOGS = [
  { ts: '2026-03-13 15:41:08', level: 'INFO', event: 'ALERT',     symbol: 'F',    direction: 'bearish', price: 13.226, ratio: 3.18, message: 'Ask-side imbalance — cover short (+$8.40)' },
  { ts: '2026-03-13 15:40:55', level: 'INFO', event: 'IMBALANCE', symbol: 'F',    price: 13.226, ratio: 3.18, message: 'L2 bid/ask depth ratio crossed 3.0' },
  { ts: '2026-03-13 15:33:00', level: 'INFO', event: 'HEARTBEAT', message: 'stream alive · AAL F BBAI RIG SOXS · 0 reconnects' },
  { ts: '2026-03-13 15:18:44', level: 'INFO', event: 'ALERT',     symbol: 'AAL',  direction: 'bullish', price: 12.531, ratio: 2.41, message: 'Exit long on tape exhaustion (+$9.50)' },
  { ts: '2026-03-13 14:46:55', level: 'WARN', event: 'ALERT',     symbol: 'BBAI', direction: 'bullish', price: 3.901,  ratio: 1.88, message: 'Stop-out long (-$7.00)' },
  { ts: '2026-03-13 12:31:19', level: 'INFO', event: 'ALERT',     symbol: 'F',    direction: 'bullish', price: 13.224, ratio: 2.77, message: 'Exit long — target (+$15.20)' },
  { ts: '2026-03-13 11:18:07', level: 'INFO', event: 'ALERT',     symbol: 'AAL',  direction: 'bearish', price: 12.486, ratio: 2.95, message: 'Cover short — bid wall (+$6.00)' },
  { ts: '2026-03-13 09:30:00', level: 'INFO', event: 'SYSTEM',    message: 'Market open — scalper armed · long-only bias (shorts gated post-analysis)' },
]

// Dollar-break screener — independent sub-$1 universe basing under the $1.00 break.
const WATCHLIST = [
  { symbol: 'OPEN', price: 0.97, score: 88, distance: 0.6, ts: '2026-03-13 15:40:40' },
  { symbol: 'SNTI', price: 0.94, score: 81, distance: 1.3, ts: '2026-03-13 15:38:12' },
  { symbol: 'GNS',  price: 0.91, score: 73, distance: 2.1, ts: '2026-03-13 15:35:55' },
  { symbol: 'NVNI', price: 0.86, score: 67, distance: 3.0, ts: '2026-03-13 15:31:01' },
]

const SCREENER_ALERTS = [
  { id: 5, symbol: 'OPEN', alert_type: 'BREAK',       price: 1.01, score: 88, ts: '2026-03-13 15:40:41' },
  { id: 4, symbol: 'SNTI', alert_type: 'APPROACHING', price: 0.95, score: 81, ts: '2026-03-13 15:38:13' },
  { id: 3, symbol: 'GNS',  alert_type: 'APPROACHING', price: 0.92, score: 73, ts: '2026-03-13 15:35:56' },
]

const SCREENER_HISTORY = Array.from({ length: 30 }, (_, i) => ({
  ts: `2026-03-13 ${String(10 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10).padStart(2, '0')}`,
  price: Math.round((0.92 + Math.sin(i / 4) * 0.05 + i * 0.002) * 100) / 100,
}))

const PAPER_ROWS = SYMBOL_BREAKDOWN.map((r) => ({
  symbol: r.symbol,
  total_pnl: r.total_pnl,
  win_rate: r.win_rate,
  trades: r.trades,
  today_pi: Math.round(r.pnl_per_share * 1.4 * 10000) / 10000,
  alltime_pi: r.pnl_per_share,
  today_win_rate: r.win_rate,
}))

const REPORTS = [
  {
    rowid: 2,
    timestamp: Date.now() / 1000 - 3600,
    agent_name: 'scalper_analyst',
    report_markdown:
      `## Scalper — Daily Round-Trip Review (Mar 13)\n\n**Net +$35.98 across 59 round trips · 69.5% win rate** — best recent session.\n\n| Symbol | Net | Read |\n|---|---|---|\n| F | +$23.60 | clean longs into 1pm/3pm windows |\n| AAL | +$15.50 | both sides worked |\n| RIG | +$5.20 | one short |\n| BBAI | -$7.00 | single stop-out, size kept small |\n\n**Edge confirmation:** longs continue to carry the book. Short entries stayed gated after the long/short asymmetry finding — the L2 signal reads bid pressure cleaner than ask.`,
  },
  {
    rowid: 1,
    timestamp: Date.now() / 1000 - 4 * 86400,
    agent_name: 'weekly_review',
    report_markdown:
      `## Strategy Review — 17-Day Live Run\n\n591 closing trades, **54.7% win rate**, net **−$16.08** (breakeven). Peak equity +$510, max drawdown −$576.\n\n**The system isn't a loser — it has two fixable leaks:**\n\n1. **Short side bleeds.** SELL (close longs) ran **+$407 @ +$1.89/trade**; COVER (close shorts) ran **−$423 @ −$1.13/trade**. A $3.02/trade gap — the imbalance signal reads ask pressure worse than bid.\n2. **Position sizing on BBAI.** A single 1,000-share BBAI cover on Mar 6 lost **−$434.90** and erased the entire +$450 the system had built. Without Mar 6, the run is **+$450**.\n\n**Actions:** gate shorts (long-bias), hard-cap BBAI notional, avoid the 11am trap window (−$3.19/trade), lean into 1pm + 3pm (+$0.86 / +$2.75).`,
  },
]

// ─────────────────────────── REST route table ───────────────────────────

function route(url: string): unknown {
  const path = url.split('?')[0].replace(/\/$/, '')

  if (path.startsWith('/screener/history/')) return { points: SCREENER_HISTORY }

  switch (path) {
    case '/auth/verify':          return { valid: true }
    case '/auth/login':           return { token: 'demo', expires_at: new Date(Date.now() + 864e5).toISOString() }
    case '/admin/status':         return { loop_running: true, trader_running: true, grok_running: true, paper_running: true, token_file_exists: true, token_file_mtime: new Date().toISOString() }
    case '/terminal/state':       return { account_details: ACCOUNT, daily_pnl: DAY_PNL, win_rate: DAY_WIN_RATE }
    case '/terminal/trades':      return { trades: TRADES }
    case '/terminal/equity-curve':return { points: EQUITY_TODAY }
    case '/terminal/positions':   return { positions: OPEN_POSITIONS }
    case '/terminal/alerts':      return { alerts: [] }
    case '/analytics/summary':    return { profit_factor: 0.99, win_rate: 54.7, risk_reward: 0.82, total_round_trips: 591 }
    case '/analytics/daily-pnl':  return { bars: DAILY_BARS }
    case '/analytics/win-loss':   return { wins: 323, losses: 268 }
    case '/analytics/parse-history': return { error: 'Paste-parsing is disabled in the public demo.' }
    case '/paper/state':          return { positions: {}, daily_pnl: 35.98, total_pnl: -16.08, win_rate: 54.7, trades_today: 59 }
    case '/paper/equity-curve':   return { points: EQUITY_ALLTIME }
    case '/paper/performance':    return { rows: PAPER_ROWS }
    case '/comparison/stats':     return { scalp_stats: SCALP_STATS, scalp_curve: SCALP_CURVE, scalp_symbol_breakdown: SYMBOL_BREAKDOWN }
    case '/logs/tail':            return { logs: LOGS }
    case '/market/quotes':        return MARKET_QUOTES
    case '/agents/reports':       return { reports: REPORTS }
    case '/telegram/channels':    return { channels: ['Dr Profit VIP'] }
    case '/screener/status':      return { running: true, universe_size: 312 }
    case '/screener/watchlist':   return { rows: WATCHLIST }
    case '/screener/alerts':      return { alerts: SCREENER_ALERTS }
    case '/config':               return { risk_pct: 2.0, max_position_usd: 4000, kelly_fraction: 0.5, daily_stop_loss_pct: 2.0, order_executor: 'schwab', short_entries_enabled: false }
    default:                      return {}
  }
}

export const demoAdapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
  const data = route(config.url ?? '')
  const response: AxiosResponse = {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  }
  return Promise.resolve(response)
}

// ─────────────────────── WebSocket shim (live feeds) ─────────────────────

// Telegram signal advisor mirrors the Dr Profit VIP crypto channel and appends
// a 2%-risk sizing footer when a message contains an entry + stop.
const SIGNALS = [
  { id: 3, created_at: '2026-03-13 15:09:40', channel: 'Dr Profit VIP', raw_text: 'LONG BTC entry 64200 SL 62800 TP 66000 68500 71000', image_path: null, entry: 64200, sl: 62800, sl_distance_pct: 2.18, tp_levels: [66000, 68500, 71000], quantity: 0.0089, position_size_usdt: 571.8, risk_amount_usdt: 49, risk_pct: 2, balance_usdt: 2450, has_sizing: 1 },
  { id: 2, created_at: '2026-03-13 13:22:11', channel: 'Dr Profit VIP', raw_text: 'SHORT ETH 3180 stop 3265 targets 3050 2950', image_path: null, entry: 3180, sl: 3265, sl_distance_pct: 2.67, tp_levels: [3050, 2950], quantity: 0.577, position_size_usdt: 1834, risk_amount_usdt: 49, risk_pct: 2, balance_usdt: 2450, has_sizing: 1 },
  { id: 1, created_at: '2026-03-13 11:05:02', channel: 'Dr Profit VIP', raw_text: 'Watching SOL for a reclaim of 145 before adding', image_path: null, entry: null, sl: null, sl_distance_pct: null, tp_levels: [], quantity: null, position_size_usdt: null, risk_amount_usdt: null, risk_pct: null, balance_usdt: null, has_sizing: 0 },
]

const MESSAGES = [
  { id: 3, created_at: '2026-03-13 15:09:40', channel: 'Dr Profit VIP', raw_text: 'LONG BTC entry 64200 SL 62800 TP 66000 68500 71000', image_path: null, has_sizing: 1, entry: 64200, sl: 62800, tp_levels: [66000, 68500, 71000] },
  { id: 2, created_at: '2026-03-13 13:22:11', channel: 'Dr Profit VIP', raw_text: 'SHORT ETH 3180 stop 3265 targets 3050 2950', image_path: null, has_sizing: 1, entry: 3180, sl: 3265, tp_levels: [3050, 2950] },
  { id: 1, created_at: '2026-03-13 11:05:02', channel: 'Dr Profit VIP', raw_text: 'Watching SOL for a reclaim of 145 before adding', image_path: null, has_sizing: 0, entry: null, sl: null, tp_levels: [] },
]

type Listener = ((ev: { data: string }) => void) | null

/** Minimal WebSocket-compatible shim that replays demo feeds based on the URL. */
class DemoSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  readonly OPEN = 1
  readyState = DemoSocket.OPEN
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: Listener = null
  url: string
  private timers: ReturnType<typeof setInterval>[] = []

  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.onopen?.()
      this.start()
    }, 60)
  }

  private emit(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) })
  }

  private start() {
    if (this.url.includes('/terminal/ws')) {
      const base = ACCOUNT.liquidation_value - DAY_PNL
      const state = (pnl: number) => ({
        type: 'state_update',
        data: {
          account_details: { ...ACCOUNT, liquidation_value: Math.round((base + pnl) * 100) / 100, day_pnl: pnl },
          daily_pnl: pnl,
          win_rate: DAY_WIN_RATE,
          rolling_pi_per_share: 0.0021,
          max_drawdown: 1.42,
          positions: OPEN_POSITIONS,
          cooldowns: { loss_cooldown_until: 0, pi_cooldown_until: 0, loss_cooldown_syms: [] },
        },
      })
      this.emit({ ...state(DAY_PNL), data: { ...state(DAY_PNL).data, new_trades: TRADES } })
      let p = DAY_PNL
      this.timers.push(setInterval(() => {
        p = Math.round((p + (Math.random() - 0.4) * 3) * 100) / 100
        this.emit(state(p))
      }, 4000))
    } else if (this.url.includes('/signals/ws')) {
      this.emit({ type: 'init', signals: SIGNALS })
    } else if (this.url.includes('/telegram/ws')) {
      this.emit({ type: 'init', messages: MESSAGES, channels: ['Dr Profit VIP'] })
    }
  }

  send() {}
  close() {
    this.readyState = DemoSocket.CLOSED
    this.timers.forEach(clearInterval)
    this.onclose?.()
  }
  addEventListener() {}
  removeEventListener() {}
}

/** Seed a fake token + install the WebSocket shim. Call once before render. */
export function installDemoEnv() {
  if (!DEMO) return
  if (!localStorage.getItem('quant_token')) localStorage.setItem('quant_token', 'demo')
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).WebSocket = DemoSocket as any
}
