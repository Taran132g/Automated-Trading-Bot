import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { adminService, configService, patternConfigService } from '@/services/api'

const CARD = '#12121c'
const BORDER = 'rgba(255,255,255,0.06)'
const ACCENT = '#c8ff00'
const GREEN = '#22c55e'
const RED = '#ef4444'
const TEXT = '#f0f0f5'
const SEC = '#8b8b9e'
const DIM = '#55556a'
const INPUT_BG = '#0a0a12'

function ConfirmButton({ label, onConfirm, danger = false }: { label: string; onConfirm: () => void; danger?: boolean }) {
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')

  if (!confirming) {
    return (
      <button onClick={() => setConfirming(true)} style={{
        padding: '10px 20px', border: `1px solid ${danger ? 'rgba(239,68,68,0.2)' : BORDER}`,
        background: danger ? 'rgba(239,68,68,0.06)' : '#191925', color: danger ? RED : TEXT,
        borderRadius: 8, cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600,
        transition: 'all 0.15s',
      }}>
        {label}
      </button>
    )
  }

  const needsType = danger
  const ready = !needsType || typed === 'CONFIRM'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'rgba(239,68,68,0.04)', border: `1px solid rgba(239,68,68,0.15)`, borderRadius: 10, padding: 14 }}>
      {needsType && (
        <>
          <div style={{ fontSize: '0.72rem', color: RED }}>Type CONFIRM to proceed:</div>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="CONFIRM"
            style={{ background: INPUT_BG, border: `1px solid rgba(239,68,68,0.2)`, borderRadius: 8, padding: '7px 12px', color: TEXT, fontSize: '0.82rem', fontFamily: 'JetBrains Mono, monospace', outline: 'none', width: 140 }} />
        </>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => { if (ready) { onConfirm(); setConfirming(false); setTyped('') } }}
          disabled={!ready} style={{
            padding: '8px 16px', background: ready ? RED : '#191925', border: 'none', borderRadius: 8,
            color: ready ? '#fff' : DIM, cursor: ready ? 'pointer' : 'not-allowed', fontSize: '0.78rem', fontWeight: 600,
            transition: 'all 0.15s',
          }}>
          Execute
        </button>
        <button onClick={() => { setConfirming(false); setTyped('') }} style={{
          padding: '8px 16px', background: 'none', border: `1px solid ${BORDER}`, borderRadius: 8,
          color: SEC, cursor: 'pointer', fontSize: '0.78rem',
          transition: 'all 0.15s',
        }}>
          Cancel
        </button>
      </div>
    </div>
  )
}

type ConfigForm = Record<string, string | number | boolean>

export function AdminPage() {
  const qc = useQueryClient()
  const [authUrlData, setAuthUrlData] = useState<string | null>(null)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [configForm, setConfigForm] = useState<ConfigForm | null>(null)
  const [patternForm, setPatternForm] = useState<ConfigForm | null>(null)
  const [actionResult, setActionResult] = useState<string | null>(null)

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['admin-status-page'],
    queryFn: () => adminService.getStatus().then((r) => r.data),
    refetchInterval: 8000,
  })

  const { data: cfg } = useQuery({ queryKey: ['config'], queryFn: () => configService.get().then((r) => r.data) })
  const { data: patternCfg } = useQuery({ queryKey: ['config-pattern'], queryFn: () => patternConfigService.get().then((r) => r.data) })

  useEffect(() => { if (cfg && !configForm) setConfigForm(cfg as Record<string, string | number>) }, [cfg, configForm])
  useEffect(() => { if (patternCfg && !patternForm) setPatternForm(patternCfg as Record<string, string | number>) }, [patternCfg, patternForm])

  const startMut = useMutation({ mutationFn: adminService.start, onSuccess: () => { refetchStatus(); setActionResult('Backend started') } })
  const stopMut = useMutation({ mutationFn: adminService.stop, onSuccess: () => { refetchStatus(); setActionResult('Backend stopped') } })
  const flattenMut = useMutation({ mutationFn: adminService.flatten, onSuccess: (r) => setActionResult(r.data.results?.join('\n') ?? 'Done') })
  const shutdownMut = useMutation({ mutationFn: adminService.fullShutdown, onSuccess: () => setActionResult('Shutdown executed') })
  const authUrlMut = useMutation({ mutationFn: adminService.getSchwabAuthUrl, onSuccess: (r) => setAuthUrlData(r.data.authorization_url) })
  const saveTokensMut = useMutation({ mutationFn: (url: string) => adminService.saveSchwabTokens(url), onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-status-page'] }); setActionResult('Tokens saved') } })
  const configMut = useMutation({ mutationFn: (d: ConfigForm) => configService.update(d), onSuccess: () => setActionResult('Config saved') })
  const patternConfigMut = useMutation({ mutationFn: (d: ConfigForm) => patternConfigService.update(d), onSuccess: () => setActionResult('Pattern config saved') })

  const backendOnline = status?.loop_running || status?.trader_running

  const inputStyle = {
    width: '100%', background: INPUT_BG, border: `1px solid ${BORDER}`, borderRadius: 8,
    padding: '9px 12px', color: TEXT, fontSize: '0.82rem', fontFamily: 'JetBrains Mono, monospace',
    outline: 'none', boxSizing: 'border-box' as const,
    transition: 'border-color 0.15s',
  }

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: TEXT, letterSpacing: '-0.02em' }}>
        ADMIN CONTROLS
      </h2>

      {actionResult && (
        <div style={{ background: 'rgba(34,197,94,0.04)', border: `1px solid rgba(34,197,94,0.15)`, borderRadius: 10, padding: '12px 18px', fontSize: '0.8rem', color: GREEN, whiteSpace: 'pre-wrap' }}>
          {actionResult}
          <button onClick={() => setActionResult(null)} style={{ marginLeft: 12, background: 'none', border: 'none', color: DIM, cursor: 'pointer', fontSize: '0.75rem' }}>&times;</button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Backend status */}
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
            <SectionHeader>Backend Status</SectionHeader>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: backendOnline ? GREEN : RED,
                boxShadow: backendOnline ? `0 0 8px ${GREEN}` : 'none',
                display: 'inline-block',
              }} />
              <span style={{ fontSize: '0.85rem', color: TEXT, fontFamily: 'JetBrains Mono, monospace' }}>
                {backendOnline ? 'RUNNING' : 'STOPPED'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              {[
                { label: 'Loop', val: status?.loop_running },
                { label: 'Trader', val: status?.trader_running },
                { label: 'Grok', val: status?.grok_running },
                { label: 'Paper', val: status?.paper_running },
              ].map(({ label, val }) => (
                <div key={label} style={{ fontSize: '0.72rem', color: val ? GREEN : DIM, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 5, height: 5, borderRadius: '50%', background: val ? GREEN : '#191925', display: 'inline-block' }} />
                  {label}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => startMut.mutate()} disabled={startMut.isPending} style={{
                padding: '9px 18px', background: 'rgba(200,255,0,0.06)', border: `1px solid rgba(200,255,0,0.15)`,
                color: ACCENT, borderRadius: 8, cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600,
                transition: 'all 0.15s',
              }}>Start</button>
              <button onClick={() => stopMut.mutate()} disabled={stopMut.isPending} style={{
                padding: '9px 18px', background: '#191925', border: `1px solid ${BORDER}`,
                color: TEXT, borderRadius: 8, cursor: 'pointer', fontSize: '0.78rem',
                transition: 'all 0.15s',
              }}>Stop</button>
            </div>
          </div>

          {/* Flatten */}
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
            <SectionHeader>Position Management</SectionHeader>
            <ConfirmButton label="Flatten All Positions" onConfirm={() => flattenMut.mutate()} danger />
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Emergency */}
          <div style={{ background: CARD, border: `1px solid rgba(239,68,68,0.12)`, borderRadius: 10, padding: '18px 20px' }}>
            <SectionHeader>Emergency Shutdown</SectionHeader>
            <div style={{ color: SEC, fontSize: '0.75rem', marginBottom: 12 }}>
              Flatten ALL positions AND kill backend.
            </div>
            <ConfirmButton label="Execute Full Shutdown" onConfirm={() => shutdownMut.mutate()} danger />
          </div>

          {/* Schwab tokens */}
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
            <SectionHeader>Schwab Token Management</SectionHeader>
            <div style={{ fontSize: '0.75rem', color: status?.token_file_exists ? GREEN : RED, marginBottom: 12 }}>
              Token file: {status?.token_file_exists ? 'Present' : 'Missing'}
              {status?.token_file_mtime && (
                <span style={{ color: DIM, marginLeft: 8 }}>
                  Updated: {new Date(status.token_file_mtime * 1000).toLocaleString()}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button onClick={() => authUrlMut.mutate()} style={{
                padding: '8px 16px', background: '#191925', border: `1px solid ${BORDER}`, borderRadius: 8,
                color: TEXT, cursor: 'pointer', fontSize: '0.78rem', textAlign: 'left',
                transition: 'all 0.15s',
              }}>
                Step 1: Generate Auth Link
              </button>
              {authUrlData && (
                <a href={authUrlData} target="_blank" rel="noopener noreferrer" style={{
                  display: 'block', padding: '8px 16px', background: 'rgba(200,255,0,0.04)',
                  border: `1px solid rgba(200,255,0,0.15)`, borderRadius: 8, color: ACCENT, fontSize: '0.75rem',
                  wordBreak: 'break-all', textDecoration: 'none',
                }}>
                  Open Auth URL
                </a>
              )}
              <input value={callbackUrl} onChange={(e) => setCallbackUrl(e.target.value)} placeholder="Paste callback URL here..."
                style={{ ...inputStyle }} />
              <button onClick={() => saveTokensMut.mutate(callbackUrl)} disabled={!callbackUrl.trim()} style={{
                padding: '8px 16px', background: callbackUrl.trim() ? ACCENT : '#191925',
                border: 'none', borderRadius: 8, color: callbackUrl.trim() ? '#06060b' : DIM,
                cursor: callbackUrl.trim() ? 'pointer' : 'not-allowed', fontSize: '0.78rem', fontWeight: 600,
                transition: 'all 0.15s',
              }}>
                Save Tokens
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Config form */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
        <SectionHeader>Configuration</SectionHeader>
        {configForm && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { key: 'live_symbols', label: 'Live Symbols', type: 'text' },
                { key: 'paper_symbols', label: 'Paper Symbols', type: 'text' },
                { key: 'live_position_size', label: 'Live Position Size', type: 'number' },
                { key: 'paper_position_size', label: 'Paper Position Size', type: 'number' },
                { key: 'live_max_trades_per_hour', label: 'Max Trades/Hour', type: 'number' },
                { key: 'account_stop_loss', label: 'Account Stop Loss ($)', type: 'number' },
              ].map(({ key, label, type }) => (
                <div key={key}>
                  <label style={{ fontSize: '0.7rem', color: SEC, display: 'block', marginBottom: 6 }}>{label}</label>
                  <input type={type} value={configForm[key] as string ?? ''} onChange={(e) => setConfigForm({ ...configForm, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
                    style={inputStyle} />
                </div>
              ))}
            </div>

            {/* Kelly */}
            <div style={{ marginTop: 24, paddingTop: 18, borderTop: `1px solid ${BORDER}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: SEC, textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Kelly Criterion Sizing
                </span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <div onClick={() => setConfigForm({ ...configForm, kelly_enabled: !configForm.kelly_enabled })}
                    style={{ width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer', background: configForm.kelly_enabled ? ACCENT : '#191925', transition: 'background 0.2s' }}>
                    <div style={{ position: 'absolute', top: 3, left: configForm.kelly_enabled ? 18 : 3, width: 14, height: 14, borderRadius: '50%', background: configForm.kelly_enabled ? '#06060b' : '#33334a', transition: 'left 0.2s' }} />
                  </div>
                  <span style={{ fontSize: '0.72rem', color: configForm.kelly_enabled ? ACCENT : DIM }}>
                    {configForm.kelly_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>
              <div style={{ fontSize: '0.7rem', color: DIM, marginBottom: 14 }}>
                Scales entry size by historical win rate and reward/risk per symbol.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14 }}>
                {[
                  { key: 'kelly_fraction', label: 'Kelly Fraction', min: 0.1, max: 1.0, step: 0.05, hint: '0.5 = half-Kelly' },
                  { key: 'kelly_min_trades', label: 'Min Trades', min: 5, max: 200, step: 5, hint: 'Per-symbol trades needed' },
                  { key: 'kelly_lookback_days', label: 'Lookback Days', min: 1, max: 365, step: 1, hint: 'Days of history' },
                  { key: 'kelly_min_multiplier', label: 'Min Multiplier', min: 0.05, max: 1.0, step: 0.05, hint: 'Floor size multiplier' },
                  { key: 'kelly_max_multiplier', label: 'Max Multiplier', min: 1.0, max: 5.0, step: 0.25, hint: 'Cap size multiplier' },
                ].map(({ key, label, min, max, step, hint }) => (
                  <div key={key}>
                    <label style={{ fontSize: '0.7rem', color: SEC, display: 'block', marginBottom: 6 }} title={hint}>{label}</label>
                    <input type="number" min={min} max={max} step={step} value={configForm[key] as number ?? ''} onChange={(e) => setConfigForm({ ...configForm, [key]: Number(e.target.value) })}
                      style={inputStyle} />
                    <div style={{ fontSize: '0.6rem', color: DIM, marginTop: 4 }}>{hint}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
        {configForm && (
          <button onClick={() => configMut.mutate(configForm)} style={{
            marginTop: 18, padding: '10px 22px', background: ACCENT, border: 'none', borderRadius: 8,
            color: '#06060b', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
            transition: 'all 0.15s',
          }}>
            Save Configuration
          </button>
        )}
      </div>

      {/* Pattern config */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: '18px 20px' }}>
        <SectionHeader>Pattern Strategy</SectionHeader>
        {patternForm && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { key: 'pattern_symbols', label: 'Pattern Symbols', type: 'text' },
                { key: 'pattern_live_position_size', label: 'Live Position Size', type: 'number' },
                { key: 'pattern_paper_position_size', label: 'Paper Position Size', type: 'number' },
              ].map(({ key, label, type }) => (
                <div key={key}>
                  <label style={{ fontSize: '0.7rem', color: SEC, display: 'block', marginBottom: 6 }}>{label}</label>
                  <input type={type} value={patternForm[key] as string ?? ''} onChange={(e) => setPatternForm({ ...patternForm, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
                    style={inputStyle} />
                </div>
              ))}
            </div>

            <div style={{ marginTop: 24, paddingTop: 18, borderTop: `1px solid ${BORDER}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: SEC, textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Kelly Criterion Sizing
                </span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <div onClick={() => setPatternForm({ ...patternForm, pattern_kelly_enabled: !patternForm.pattern_kelly_enabled })}
                    style={{ width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer', background: patternForm.pattern_kelly_enabled ? ACCENT : '#191925', transition: 'background 0.2s' }}>
                    <div style={{ position: 'absolute', top: 3, left: patternForm.pattern_kelly_enabled ? 18 : 3, width: 14, height: 14, borderRadius: '50%', background: patternForm.pattern_kelly_enabled ? '#06060b' : '#33334a', transition: 'left 0.2s' }} />
                  </div>
                  <span style={{ fontSize: '0.72rem', color: patternForm.pattern_kelly_enabled ? ACCENT : DIM }}>
                    {patternForm.pattern_kelly_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>
              <div style={{ fontSize: '0.7rem', color: DIM, marginBottom: 14 }}>
                Scales entry size by historical win rate and reward/risk. Optimized independently from scalping.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14 }}>
                {[
                  { key: 'pattern_kelly_fraction', label: 'Kelly Fraction', min: 0.1, max: 1.0, step: 0.05, hint: '0.5 = half-Kelly' },
                  { key: 'pattern_kelly_min_trades', label: 'Min Trades', min: 5, max: 200, step: 5, hint: 'Per-symbol trades needed' },
                  { key: 'pattern_kelly_lookback_days', label: 'Lookback Days', min: 1, max: 365, step: 1, hint: 'Days of history' },
                  { key: 'pattern_kelly_min_multiplier', label: 'Min Multiplier', min: 0.05, max: 1.0, step: 0.05, hint: 'Floor size multiplier' },
                  { key: 'pattern_kelly_max_multiplier', label: 'Max Multiplier', min: 1.0, max: 5.0, step: 0.25, hint: 'Cap size multiplier' },
                ].map(({ key, label, min, max, step, hint }) => (
                  <div key={key}>
                    <label style={{ fontSize: '0.7rem', color: SEC, display: 'block', marginBottom: 6 }} title={hint}>{label}</label>
                    <input type="number" min={min} max={max} step={step} value={patternForm[key] as number ?? ''} onChange={(e) => setPatternForm({ ...patternForm, [key]: Number(e.target.value) })}
                      style={inputStyle} />
                    <div style={{ fontSize: '0.6rem', color: DIM, marginTop: 4 }}>{hint}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
        {patternForm && (
          <button onClick={() => patternConfigMut.mutate(patternForm)} style={{
            marginTop: 18, padding: '10px 22px', background: ACCENT, border: 'none', borderRadius: 8,
            color: '#06060b', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
            transition: 'all 0.15s',
          }}>
            Save Pattern Config
          </button>
        )}
      </div>
    </div>
  )
}
