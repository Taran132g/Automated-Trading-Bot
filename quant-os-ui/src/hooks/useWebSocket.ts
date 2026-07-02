import { useEffect, useRef, useCallback } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage: (data: unknown) => void
  enabled?: boolean
}

export function useWebSocket({ url, onMessage, enabled = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const backoffRef = useRef(1000)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return

    // In prod, WS must hit the Oracle box (via Tailscale Funnel), not the Vercel
    // origin. VITE_WS_URL is the wss base (e.g. wss://quant-os.<tailnet>.ts.net);
    // fall back to same-origin for local dev / API-served builds.
    const wsBase =
      (import.meta.env.VITE_WS_URL as string | undefined) ||
      `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
    const wsUrl = `${wsBase}${url}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data))
      } catch {
        // ignore parse errors
      }
    }

    ws.onopen = () => {
      backoffRef.current = 1000
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      const delay = Math.min(backoffRef.current, 30000)
      backoffRef.current = Math.min(backoffRef.current * 2, 30000)
      setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [url, onMessage, enabled])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()
    return () => {
      mountedRef.current = false
      wsRef.current?.close()
    }
  }, [connect, enabled])
}
