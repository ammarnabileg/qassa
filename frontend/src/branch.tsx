/** The branch the user is working in (POS, bookings, drawer). Chosen in the sidebar, like the approved design. */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useOrg } from './pages/Org'
import type { Branch } from './api/client'

type Scope = { branch: Branch | null; branches: Branch[]; setBranchId: (id: number) => void; company: boolean; setCompany: (on: boolean) => void }
const Ctx = createContext<Scope>({ branch: null, branches: [], setBranchId: () => undefined, company: false, setCompany: () => undefined })
const KEY = 'qassa.branch'
const SCOPE = 'qassa.scope'

/** `canCompany`: members over all branches start in company view (the reference's "🏢 كل الفروع"); others always work in a branch. */
export function BranchProvider({ children, canCompany = false }: { children: ReactNode; canCompany?: boolean }) {
  const org = useOrg()
  const branches = (org.data?.branches ?? []).filter((b) => b.is_active)
  const [id, setId] = useState<number | null>(() => { try { return Number(sessionStorage.getItem(KEY)) || null } catch { return null } })
  const branch = branches.find((b) => b.id === id) ?? branches[0] ?? null
  useEffect(() => { if (branch) try { sessionStorage.setItem(KEY, String(branch.id)) } catch { /* private mode */ } }, [branch])
  const [co, setCo] = useState<boolean>(() => { try { return sessionStorage.getItem(SCOPE) !== 'branch' } catch { return true } })
  const company = canCompany && co
  const setCompany = (on: boolean) => { setCo(on); try { sessionStorage.setItem(SCOPE, on ? 'company' : 'branch') } catch { /* private mode */ } }
  return <Ctx.Provider value={{ branch, branches, setBranchId: setId, company, setCompany }}>{children}</Ctx.Provider>
}

export const useBranch = () => useContext(Ctx)
