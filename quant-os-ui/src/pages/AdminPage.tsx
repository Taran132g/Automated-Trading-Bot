import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { adminService, configService, patternConfigService } from '@/services/api'

function ConfirmButton({ label, onConfirm, danger = false }: { label: string; onConfirm: () => void; danger?: boolean }) {
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')

  if (!confirming) {
    return (
      <button onClick={() => setConfirming(true)} style={{
        padding: '9px 18px', border: `1px solid ${danger ? '#EF4444' : '#1F2937'}`,
        background: danger ? 'rgba(239,68,68,0.1)' : '#1F2937', color: danger ? '#EF4444' : '#E2E8F0',
        borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600,
      }}>
        {label}
      </button>
    )
  }

  const needsType = danger
  const ready = !needsType || typed === 'CONFIRM'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'rgba(239,68,68,0.05)', border: '1px solid #EF4444', borderRadius: 8, padding: 12 }}>
      {needsType && (
        <>
          <div style={{ fontSize: '0.72rem', color: '#EF4444' }}>Type CONFIRM to proceed:</div>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="CONFIRM"
            style={{ background: '#0B0E14', border: '1px solid #EF4444', borderRadius: 6, padding: '6px 10px', color: '#F8FAFC', fontSize: '0.82rem', fontFamily: 'Roboto Mono', outline: 'none', width: 140 }} />
        </>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => { if (ready) { onConfirm(); setConfirming(false); setTyped('') } }}
          disabled={!ready} style={{
            padding: '7px 14px', background: ready ? '#EF4444' : '#374151', border: 'none', borderRadius: 6,
            color: ready ? '#fff' : '#64748B', cursor: ready ? 'pointer' : 'not-allowed', fontSize: '0.78rem', fontWeight: 600,
          }}>
          Execute
        </button>
        <button onClick={() => { setConfirming(false); setTyped('') }} style={{
          padding: '7px 14px', background: 'none', border: '1px solid #1F2937', borderRadius: 6,
          color: '#94A3B8', cursor: 'pointer', fontSize: '0.78rem',
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

  const { data: cfg } = useQuery({
    queryKey: ['config'],
    queryFn: () => configService.get().then((r) => r.data),
  })

  const { data: patternCfg } = useQuery({
    queryKey: ['config-pattern'],
    queryFn: () => patternConfigService.get().then((r) => r.data),
  })

  useEffect(() => {
    if (cfg && !configForm) setConfigForm(cfg as Record<string, string | number>)
  }, [cfg, configForm])

  useEffect(() => {
    if (patternCfg && !patternForm) setPatternForm(patternCfg as Record<string, string | number>)
  }, [patternCfg, patternForm])

  const startMut = useMutation({ mutationFn: adminService.start, onSuccess: () => { refetchStatus(); setActionResult('Backend started') } })
  const stopMut = useMutation({ mutationFn: adminService.stop, onSuccess: () => { refetchStatus(); setActionResult('Backend stopped') } })
  const flattenMut = useMutation({ mutationFn: adminService.flatten, onSuccess: (r) => setActionResult(r.data.results?.join('\n') ?? 'Done') })
  const shutdownMut = useMutation({ mutationFn: adminService.fullShutdown, onSuccess: () => setActionResult('Shutdown executed') })
  const authUrlMut = useMutation({ mutationFn: adminService.getSchwabAuthUrl, onSuccess: (r) => setAuthUrlData(r.data.authorization_url) })
  const saveTokensMut = useMutation({ mutationFn: (url: string) => adminService.saveSchwabTokens(url), onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-status-page'] }); setActionResult('Tokens saved') } })
  const configMut = useMutation({ mutationFn: (d: ConfigForm) => configService.update(d), onSuccess: () => setActionResult('Config saved') })
  const patternConfigMut = useMutation({ mutationFn: (d: ConfigForm) => patternConfigService.update(d), onSuccess: () => setActionResult('Pattern config saved') })

  const backendOnline = status?.loop_running || status?.trader_running

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.3px' }}>
        ADMIN CONTROLS
      </h2>

      {actionResult && (
        <div style={{ background: 'rgba(0,255,153,0.08)', border: '1px solid #00FF9933', borderRadius: 8, padding: '10px 16px', fontSize: '0.8rem', color: '#00FF99', whiteSpace: 'pre-wrap' }}>
          {actionResult}
          <button onClick={() => setActionResult(null)} style={{ marginLeft: 12, background: 'none', border: 'none', color: '#64748B', cursor: 'pointer', fontSize: '0.75rem' }}>✕</button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 16 }}>
        {/* Left column */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Backend status */}
          <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
            <SectionHeader>Backend Status</SectionHeader>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%',
                background: backendOnline ? '#00FF99' : '#EF4444',
                boxShadow: backendOnline ? '0 0 8px #00FF99' : 'none',
                display: 'inline-block',
              }} />
              <span style={{ fontSize: '0.85rem', color: '#E2E8F0', fontFamily: 'Roboto Mono' }}>
                {backendOnline ? 'RUNNING' : 'STOPPED'}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              {[
                { label: 'Loop', val: status?.loop_running },
                { label: 'Trader', val: status?.trader_running },
                { label: 'Grok', val: status?.grok_running },
                { label: 'Paper', val: status?.paper_running },
              ].map(({ label, val }) => (
                <div key={label} style={{ fontSize: '0.72rem', color: val ? '#00FF99' : '#64748B', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: val ? '#00FF99' : '#374151', display: 'inline-block' }} />
                  {label}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => startMut.mutate()} disabled={startMut.isPending} style={{
                padding: '8px 16px', background: 'rgba(0,255,153,0.1)', border: '1px solid #00FF9933',
                color: '#00FF99', borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600,
              }}>▶ Start</button>
              <button onClick={() => stopMut.mutate()} disabled={stopMut.isPending} style={{
                padding: '8px 16px', background: '#1F2937', border: '1px solid #374151',
                color: '#E2E8F0', borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem',
              }}>⏹ Stop</button>
            </div>
          </div>

          {/* Flatten */}
          <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
            <SectionHeader>Position Management</SectionHeader>
            <ConfirmButton label="🔴 Flatten All Positions" onConfirm={() => flattenMut.mutate()} danger />
          </div>
        </div>

        {/* Right column */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Nuclear option */}
          <div style={{ background: '#111827', border: '1px solid #EF444433', borderRadius: 8, padding: '16px 18px' }}>
            <SectionHeader>☢ Emergency Shutdown</SectionHeader>
            <div style={{ color: '#94A3B8', fontSize: '0.75rem', marginBottom: 12 }}>
              Flatten ALL positions AND kill backend.
            </div>
            <ConfirmButton label="Execute Full Shutdown" onConfirm={() => shutdownMut.mutate()} danger />
          </div>

          {/* Schwab tokens */}
          <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
            <SectionHeader>Schwab Token Management</SectionHeader>
            <div style={{ fontSize: '0.75rem', color: status?.token_file_exists ? '#00FF99' : '#EF4444', marginBottom: 12 }}>
              Token file: {status?.token_file_exists ? '✅ Present' : '❌ Missing'}
              {status?.token_file_mtime && (
                <span style={{ color: '#64748B', marginLeft: 8 }}>
                  Updated: {new Date(status.token_file_mtime * 1000).toLocaleString()}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button onClick={() => authUrlMut.mutate()} style={{
                padding: '7px 14px', background: '#1F2937', border: '1px solid #374151', borderRadius: 6,
                color: '#E2E8F0', cursor: 'pointer', fontSize: '0.78rem', textAlign: 'left',
              }}>
                Step 1: Generate Auth Link
              </button>
              {authUrlData && (
                <a href={authUrlData} target="_blank" rel="noopener noreferrer" style={{
                  display: 'block', padding: '7px 14px', background: 'rgba(0,255,153,0.08)',
                  border: '1px solid #00FF9933', borderRadius: 6, color: '#00FF99', fontSize: '0.75rem',
                  wordBreak: 'break-all', textDecoration: 'none',
                }}>
                  Open Auth URL ↗
                </a>
              )}
              <input value={callbackUrl} onChange={(e) => setCallbackUrl(e.target.value)} placeholder="Paste callback URL here..."
                style={{
                  background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6, padding: '8px 10px',
                  color: '#E2E8F0', fontSize: '0.75rem', fontFamily: 'Roboto Mono', outline: 'none',
                }} />
              <button onClick={() => saveTokensMut.mutate(callbackUrl)} disabled={!callbackUrl.trim()} style={{
                padding: '7px 14px', background: callbackUrl.trim() ? '#00FF99' : '#1F2937',
                border: 'none', borderRadius: 6, color: callbackUrl.trim() ? '#0B0E14' : '#64748B',
                cursor: callbackUrl.trim() ? 'pointer' : 'not-allowed', fontSize: '0.78rem', fontWeight: 600,
              }}>
                💾 Save Tokens
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Config form */}
      <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
        <SectionHeader>Configuration</SectionHeader>
        {configForm && (
          <>
            {/* Base config */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {[
                { key: 'live_symbols', label: 'Live Symbols', type: 'text' },
                { key: 'paper_symbols', label: 'Paper Symbols', type: 'text' },
                { key: 'live_position_size', label: 'Live Position Size', type: 'number' },
                { key: 'paper_position_size', label: 'Paper Position Size', type: 'number' },
                { key: 'live_max_trades_per_hour', label: 'Max Trades/Hour', type: 'number' },
                { key: 'account_stop_loss', label: 'Account Stop Loss ($)', type: 'number' },
              ].map(({ key, label, type }) => (
                <div key={key}>
                  <label style={{ fontSize: '0.7rem', color: '#94A3B8', display: 'block', marginBottom: 5 }}>{label}</label>
                  <input
                    type={type}
                    value={configForm[key] as string ?? ''}
                    onChange={(e) => setConfigForm({ ...configForm, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
                    style={{
                      width: '100%', background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6,
                      padding: '8px 10px', color: '#E2E8F0', fontSize: '0.82rem', fontFamily: 'Roboto Mono',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              ))}
            </div>

            {/* Kelly Criterion */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #1F2937' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Kelly Criterion Sizing
                </span>
                {/* Enable toggle */}
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <div
                    onClick={() => setConfigForm({ ...configForm, kelly_enabled: !configForm.kelly_enabled })}
                    style={{
                      width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer',
                      background: configForm.kelly_enabled ? '#00FF99' : '#374151',
                      transition: 'background 0.2s',
                    }}
                  >
                    <div style={{
                      position: 'absolute', top: 3, left: configForm.kelly_enabled ? 18 : 3,
                      width: 14, height: 14, borderRadius: '50%', background: '#0B0E14',
                      transition: 'left 0.2s',
                    }} />
                  </div>
                  <span style={{ fontSize: '0.72rem', color: configForm.kelly_enabled ? '#00FF99' : '#64748B' }}>
                    {configForm.kelly_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748B', marginBottom: 12 }}>
                Scales entry size by historical win rate and reward/risk per symbol. Falls back to global stats when per-symbol data is thin.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
                {[
                  { key: 'kelly_fraction',       label: 'Kelly Fraction',    min: 0.1, max: 1.0,   step: 0.05, hint: '0.5 = half-Kelly (recommended)' },
                  { key: 'kelly_min_trades',      label: 'Min Trades',        min: 5,   max: 200,   step: 5,    hint: 'Per-symbol trades needed before using symbol Kelly' },
                  { key: 'kelly_lookback_days',   label: 'Lookback Days',     min: 1,   max: 365,   step: 1,    hint: 'Days of history to include' },
                  { key: 'kelly_min_multiplier',  label: 'Min Multiplier',    min: 0.05,max: 1.0,   step: 0.05, hint: 'Floor size multiplier (e.g. 0.25 = 25% of base)' },
                  { key: 'kelly_max_multiplier',  label: 'Max Multiplier',    min: 1.0, max: 5.0,   step: 0.25, hint: 'Cap size multiplier (e.g. 2.0 = 2× base)' },
                ].map(({ key, label, min, max, step, hint }) => (
                  <div key={key}>
                    <label style={{ fontSize: '0.7rem', color: '#94A3B8', display: 'block', marginBottom: 5 }} title={hint}>{label}</label>
                    <input
                      type="number"
                      min={min} max={max} step={step}
                      value={configForm[key] as number ?? ''}
                      onChange={(e) => setConfigForm({ ...configForm, [key]: Number(e.target.value) })}
                      style={{
                        width: '100%', background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6,
                        padding: '8px 10px', color: '#E2E8F0', fontSize: '0.82rem', fontFamily: 'Roboto Mono',
                        outline: 'none', boxSizing: 'border-box',
                      }}
                    />
                    <div style={{ fontSize: '0.62rem', color: '#475569', marginTop: 3 }}>{hint}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
        {configForm && (
          <button onClick={() => configMut.mutate(configForm)} style={{
            marginTop: 16, padding: '9px 20px', background: '#00FF99', border: 'none', borderRadius: 6,
            color: '#0B0E14', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
          }}>
            💾 Save Configuration
          </button>
        )}
      </div>

      {/* Pattern Strategy config */}
      <div style={{ background: '#111827', border: '1px solid #1F2937', borderRadius: 8, padding: '16px 18px' }}>
        <SectionHeader>Pattern Strategy</SectionHeader>
        {patternForm && (
          <>
            {/* Base config */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {[
                { key: 'pattern_symbols', label: 'Pattern Symbols', type: 'text' },
                { key: 'pattern_live_position_size', label: 'Live Position Size', type: 'number' },
                { key: 'pattern_paper_position_size', label: 'Paper Position Size', type: 'number' },
              ].map(({ key, label, type }) => (
                <div key={key}>
                  <label style={{ fontSize: '0.7rem', color: '#94A3B8', display: 'block', marginBottom: 5 }}>{label}</label>
                  <input
                    type={type}
                    value={patternForm[key] as string ?? ''}
                    onChange={(e) => setPatternForm({ ...patternForm, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
                    style={{
                      width: '100%', background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6,
                      padding: '8px 10px', color: '#E2E8F0', fontSize: '0.82rem', fontFamily: 'Roboto Mono',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              ))}
            </div>

            {/* Pattern Kelly (no PI) */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #1F2937' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Kelly Criterion Sizing
                </span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <div
                    onClick={() => setPatternForm({ ...patternForm, pattern_kelly_enabled: !patternForm.pattern_kelly_enabled })}
                    style={{
                      width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer',
                      background: patternForm.pattern_kelly_enabled ? '#00FF99' : '#374151',
                      transition: 'background 0.2s',
                    }}
                  >
                    <div style={{
                      position: 'absolute', top: 3, left: patternForm.pattern_kelly_enabled ? 18 : 3,
                      width: 14, height: 14, borderRadius: '50%', background: '#0B0E14',
                      transition: 'left 0.2s',
                    }} />
                  </div>
                  <span style={{ fontSize: '0.72rem', color: patternForm.pattern_kelly_enabled ? '#00FF99' : '#64748B' }}>
                    {patternForm.pattern_kelly_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748B', marginBottom: 12 }}>
                Scales entry size by historical win rate and reward/risk. No PI adjustment — optimized independently from scalping.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
                {[
                  { key: 'pattern_kelly_fraction',      label: 'Kelly Fraction',   min: 0.1, max: 1.0,  step: 0.05, hint: '0.5 = half-Kelly (recommended)' },
                  { key: 'pattern_kelly_min_trades',    label: 'Min Trades',       min: 5,   max: 200,  step: 5,    hint: 'Per-symbol trades before using symbol Kelly' },
                  { key: 'pattern_kelly_lookback_days', label: 'Lookback Days',    min: 1,   max: 365,  step: 1,    hint: 'Days of history to include' },
                  { key: 'pattern_kelly_min_multiplier',label: 'Min Multiplier',   min: 0.05,max: 1.0,  step: 0.05, hint: 'Floor size multiplier' },
                  { key: 'pattern_kelly_max_multiplier',label: 'Max Multiplier',   min: 1.0, max: 5.0,  step: 0.25, hint: 'Cap size multiplier' },
                ].map(({ key, label, min, max, step, hint }) => (
                  <div key={key}>
                    <label style={{ fontSize: '0.7rem', color: '#94A3B8', display: 'block', marginBottom: 5 }} title={hint}>{label}</label>
                    <input
                      type="number"
                      min={min} max={max} step={step}
                      value={patternForm[key] as number ?? ''}
                      onChange={(e) => setPatternForm({ ...patternForm, [key]: Number(e.target.value) })}
                      style={{
                        width: '100%', background: '#0B0E14', border: '1px solid #1F2937', borderRadius: 6,
                        padding: '8px 10px', color: '#E2E8F0', fontSize: '0.82rem', fontFamily: 'Roboto Mono',
                        outline: 'none', boxSizing: 'border-box',
                      }}
                    />
                    <div style={{ fontSize: '0.62rem', color: '#475569', marginTop: 3 }}>{hint}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
        {patternForm && (
          <button onClick={() => patternConfigMut.mutate(patternForm)} style={{
            marginTop: 16, padding: '9px 20px', background: '#00FF99', border: 'none', borderRadius: 6,
            color: '#0B0E14', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 700,
          }}>
            💾 Save Pattern Config
          </button>
        )}
      </div>
    </div>
  )
}
