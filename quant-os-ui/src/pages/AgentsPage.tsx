import { useState, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { SectionHeader } from '@/components/ui/SectionHeader'
import { Badge } from '@/components/ui/Badge'
import { agentService } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const CARD = '#0a2e2e'
const BORDER = 'rgba(171,255,2,0.08)'
const LIME = '#abff02'
const GREEN = '#00ff88'
const TEXT = '#e4f0e4'
const SEC = '#7a9a8a'
const DIM = '#4a6a5a'

const AGENT_TYPES = ['all', 'post_market', 'alert_quality', 'risk_monitor', 'optimizer'] as const
type AgentType = typeof AGENT_TYPES[number]

interface Report {
  rowid: number
  timestamp: number
  agent_name: string
  report_markdown: string
  report_data?: Record<string, unknown>
}

export function AgentsPage() {
  const authenticated = useAuthStore((s) => s.authenticated)
  const navigate = useNavigate()
  const [agentFilter, setAgentFilter] = useState<AgentType>('all')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const { data, refetch } = useQuery({
    queryKey: ['agent-reports', agentFilter],
    queryFn: () => agentService.getReports(agentFilter).then((r) => r.data.reports),
    refetchInterval: 30000,
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => agentService.uploadPostMarket(file).then((r) => r.data),
    onSuccess: (data) => { setUploadResult(data); refetch() },
  })

  const handleFile = (file: File) => uploadMut.mutate(file)

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  const fmtDate = (ts: number) =>
    new Date(ts * 1000).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true })

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: TEXT, letterSpacing: '-0.3px' }}>
        AGENT REPORTS
      </h2>

      {/* Upload zone */}
      <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, padding: '16px 18px' }}>
        <SectionHeader>Upload Post-Market Trade Activity</SectionHeader>
        {!authenticated ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            gap: 12, padding: '28px', border: `2px dashed ${BORDER}`, borderRadius: 8,
          }}>
            <Lock size={20} color={DIM} />
            <div style={{ color: DIM, fontSize: '0.82rem', textAlign: 'center' }}>
              Admin login required to upload reports
            </div>
            <button onClick={() => navigate('/login')} style={{
              padding: '7px 20px', borderRadius: 6, cursor: 'pointer',
              background: 'rgba(171,255,2,0.06)', border: `1px solid rgba(171,255,2,0.2)`,
              color: LIME, fontSize: '0.78rem', fontFamily: 'Inter',
            }}>
              Login
            </button>
          </div>
        ) : (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
              onClick={() => fileRef.current?.click()}
              style={{
                border: `2px dashed ${dragging ? LIME : BORDER}`,
                borderRadius: 8, padding: '28px', textAlign: 'center', cursor: 'pointer',
                background: dragging ? 'rgba(171,255,2,0.03)' : 'transparent',
                transition: 'all 0.15s',
              }}
            >
              <div style={{ color: DIM, fontSize: '0.82rem' }}>
                Drop Schwab HTML/CSV export here, or click to browse
              </div>
              <div style={{ color: SEC, fontSize: '0.68rem', marginTop: 6 }}>
                Filename must contain date (YYYY-MM-DD)
              </div>
            </div>
            <input ref={fileRef} type="file" accept=".html,.csv" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
            {uploadMut.isPending && <div style={{ color: SEC, fontSize: '0.78rem', marginTop: 10 }}>Generating report...</div>}
            {uploadResult && (
              <div style={{ marginTop: 12, background: '#052424', border: `1px solid ${BORDER}`, borderRadius: 6, padding: '10px 14px', fontSize: '0.75rem', color: GREEN }}>
                Report generated successfully
              </div>
            )}
          </>
        )}
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {AGENT_TYPES.map((t) => (
          <button key={t} onClick={() => setAgentFilter(t)} style={{
            padding: '5px 14px', borderRadius: 20, cursor: 'pointer', fontSize: '0.72rem', fontFamily: 'Inter',
            border: `1px solid ${agentFilter === t ? 'rgba(171,255,2,0.2)' : BORDER}`,
            background: agentFilter === t ? 'rgba(171,255,2,0.06)' : 'transparent',
            color: agentFilter === t ? LIME : DIM,
          }}>
            {t === 'all' ? 'All' : t.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          </button>
        ))}
      </div>

      {/* Reports */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(!data || data.length === 0) && (
          <div style={{ color: DIM, fontSize: '0.82rem', textAlign: 'center', padding: 24 }}>
            No reports found
          </div>
        )}
        {(data as Report[] | undefined)?.map((report) => (
          <div key={report.rowid} style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 8, overflow: 'hidden' }}>
            <div onClick={() => toggleExpand(report.rowid)} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 18px', cursor: 'pointer',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Badge type={report.agent_name} label={report.agent_name.replace('_', ' ')} />
                <span style={{ color: SEC, fontSize: '0.75rem' }}>{fmtDate(report.timestamp)}</span>
              </div>
              <span style={{ color: DIM, fontSize: '0.78rem' }}>
                {expanded.has(report.rowid) ? '\u25b2' : '\u25bc'}
              </span>
            </div>

            {expanded.has(report.rowid) && (
              <div style={{ borderTop: `1px solid ${BORDER}`, padding: '16px 18px' }}>
                <div style={{ fontSize: '0.8rem', lineHeight: 1.7, color: TEXT, maxHeight: 600, overflowY: 'auto' }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => <h1 style={{ fontSize: '1rem', color: TEXT, margin: '12px 0 6px' }}>{children}</h1>,
                      h2: ({ children }) => <h2 style={{ fontSize: '0.9rem', color: TEXT, margin: '10px 0 5px' }}>{children}</h2>,
                      h3: ({ children }) => <h3 style={{ fontSize: '0.85rem', color: SEC, margin: '8px 0 4px' }}>{children}</h3>,
                      table: ({ children }) => <table style={{ margin: '8px 0' }}>{children}</table>,
                      strong: ({ children }) => <strong style={{ color: TEXT }}>{children}</strong>,
                      code: ({ children }) => <code style={{ background: '#052424', padding: '2px 6px', borderRadius: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#c084fc' }}>{children}</code>,
                      blockquote: ({ children }) => <blockquote style={{ borderLeft: `3px solid ${BORDER}`, paddingLeft: 12, color: SEC, margin: '8px 0' }}>{children}</blockquote>,
                    }}
                  >
                    {report.report_markdown ?? ''}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
