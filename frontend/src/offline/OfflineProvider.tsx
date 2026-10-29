import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth'
import { getDevice, pending, syncNow, type Device } from './engine'

type State = { online: boolean; device: Device | null; pendingCount: number; lastSync: { review: number; conflict: number; rejected: number } | null
  setDevice: (d: Device | null) => void; refresh: () => Promise<void>; sync: () => Promise<void> }
const Ctx = createContext<State | null>(null)

/** Tracks the connection, counts unsent offline receipts, and sends them as soon as the connection returns. */
export function OfflineProvider({ children }: { children: ReactNode }) {
  const { membership } = useAuth()
  const tenant = membership?.tenant_id ?? 0
  const [online, setOnline] = useState(navigator.onLine)
  const [device, setDevice] = useState<Device | null>(null)
  const [pendingCount, setPending] = useState(0)
  const [lastSync, setLastSync] = useState<State['lastSync']>(null)
  const busy = useRef(false)

  const refresh = useCallback(async () => {
    if (!tenant) return
    setDevice((await getDevice(tenant)) ?? null)
    setPending((await pending(tenant)).length)
  }, [tenant])

  const sync = useCallback(async () => {
    if (!tenant || busy.current) return
    busy.current = true
    try {
      const r = await syncNow(tenant)
      if (r.sent || r.rejected) setLastSync({ review: r.review, conflict: r.conflict, rejected: r.rejected })
      setOnline(true)
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) setOnline(false)
    } finally {
      busy.current = false
      await refresh()
    }
  }, [tenant, refresh])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    const up = () => { setOnline(true); sync() }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    const net = (e: Event) => setOnline((e as CustomEvent<boolean>).detail)
    window.addEventListener('qassa:network', net)
    // Wi-Fi can be up while the internet is down: check the server itself every 20 seconds.
    const ping = window.setInterval(() => { api('/version').catch(() => undefined) }, 20000)
    const timer = window.setInterval(() => { if (navigator.onLine) sync() }, 30000)
    return () => {
      window.removeEventListener('online', up); window.removeEventListener('offline', down); window.removeEventListener('qassa:network', net)
      window.clearInterval(timer); window.clearInterval(ping)
    }
  }, [sync])
  useEffect(() => { if (online && pendingCount > 0) sync() }, [online, pendingCount, sync])

  return <Ctx.Provider value={{ online, device, pendingCount, lastSync, setDevice, refresh, sync }}>{children}</Ctx.Provider>
}

export function useOffline() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useOffline outside OfflineProvider')
  return c
}
