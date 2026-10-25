import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setTenant, type Me, type Membership } from './api/client'

type AuthState = {
  me: Me | null
  loading: boolean
  membership: Membership | null
  setMe: (m: Me | null) => void
  chooseTenant: (id: number) => void
  can: (perm: string) => boolean
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState | null>(null)
const TENANT_KEY = 'qassa.tenant'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [tenantId, setTenantId] = useState<number | null>(null)

  const setMe = useCallback((m: Me | null) => {
    setMeState(m)
    if (!m) { setTenantId(null); setTenant(null); return }
    const saved = Number(sessionStorage.getItem(TENANT_KEY))
    const pick = m.memberships.find((x) => x.tenant_id === saved) ?? (m.memberships.length === 1 ? m.memberships[0] : undefined)
    setTenantId(pick?.tenant_id ?? null)
    setTenant(pick?.tenant_id ?? null)
  }, [])

  useEffect(() => {
    api<Me>('/auth/me').then(setMe).catch(() => setMe(null)).finally(() => setLoading(false))
  }, [setMe])

  const chooseTenant = (id: number) => {
    sessionStorage.setItem(TENANT_KEY, String(id))
    setTenantId(id)
    setTenant(id)
  }
  const membership = me?.memberships.find((x) => x.tenant_id === tenantId) ?? null
  const can = (perm: string) => !!membership?.permissions.includes(perm)  // UI hint only; the server enforces
  const logout = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => undefined); sessionStorage.removeItem(TENANT_KEY); setMe(null) }

  return <Ctx.Provider value={{ me, loading, membership, setMe, chooseTenant, can, logout }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}
