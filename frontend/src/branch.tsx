/** The branch the user is working in (POS, bookings, drawer). Chosen in the sidebar, like the approved design. */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useOrg } from './pages/Org'
import type { Branch } from './api/client'

const Ctx = createContext<{ branch: Branch | null; branches: Branch[]; setBranchId: (id: number) => void }>({ branch: null, branches: [], setBranchId: () => undefined })
const KEY = 'qassa.branch'

export function BranchProvider({ children }: { children: ReactNode }) {
  const org = useOrg()
  const branches = (org.data?.branches ?? []).filter((b) => b.is_active)
  const [id, setId] = useState<number | null>(() => { try { return Number(sessionStorage.getItem(KEY)) || null } catch { return null } })
  const branch = branches.find((b) => b.id === id) ?? branches[0] ?? null
  useEffect(() => { if (branch) try { sessionStorage.setItem(KEY, String(branch.id)) } catch { /* private mode */ } }, [branch])
  return <Ctx.Provider value={{ branch, branches, setBranchId: setId }}>{children}</Ctx.Provider>
}

export const useBranch = () => useContext(Ctx)
