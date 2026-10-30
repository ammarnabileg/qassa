import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { BranchProvider, useBranch } from './branch'
import { LangToggle } from './components/ErrorText'
import { Icon, Logo, useBizTheme, type Biz } from './components/ui'
import Bookings from './pages/Bookings'
import Cash from './pages/Cash'
import Customers from './pages/Customers'
import Invoices from './pages/Invoices'
import POS from './pages/POS'
import OfflinePOS from './pages/OfflinePOS'
import OfflineReceipts from './pages/OfflineReceipts'
import { OfflineProvider, useOffline } from './offline/OfflineProvider'
import { OfflineBanner } from './offline/OfflineSetup'
import JournalEntry from './pages/JournalEntry'
import Login from './pages/Login'
import Org from './pages/Org'
import { PlatformPlans, PlatformTenants } from './pages/Platform'
import { PlatformBilling, PlatformHome, PlatformLeads, PlatformSettingsPage, PlatformSupport } from './pages/PlatformConsole'
import Landing from './pages/Landing'
import Reports, { CompanyHome, Home } from './pages/Reports'
import Settings from './pages/Settings'
import Support from './pages/Support'
import { api, type Appointment } from './api/client'
import Services from './pages/Services'
import Staff from './pages/Staff'
import Subscription from './pages/Subscription'
import TrialBalance from './pages/TrialBalance'
import WhatsApp from './pages/WhatsApp'
import Inventory from './pages/Inventory'
import Loyalty from './pages/Loyalty'
import Marketing from './pages/Marketing'
import Commissions from './pages/Commissions'
import Users from './pages/Users'
import SetPassword from './pages/SetPassword'
import XbrlReport from './pages/XbrlReport'
import { Assets, Expenses, Periods, Settlements, Statements } from './pages/Finance'

const ellipsis = { display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } as const

type NavItem = { path: string; label: string; icon: string; show: boolean; badge?: number }

function Shell({ biz, plat, title, sub, groups, children }: {
  biz: Biz; plat?: boolean; title: string; sub: string; groups: [string, NavItem[]][]; children: React.ReactNode
}) {
  const { t, i18n } = useTranslation()
  const { me, membership, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useBizTheme(biz)
  const { company, branch, setCompany } = useBranch()
  const ownerInBranch = !!membership?.all_branches && !membership.support && !company && !!branch
  const role = membership ? (i18n.language === 'en' ? membership.role_name.en : membership.role_name.ar) : t('platform.staff')
  return (
    <div className="app">
      <aside className={`nav${plat ? ' plat' : ''}${open ? ' open' : ''}`}>
        <Logo biz={biz} title={title} sub={sub} />
        {!plat && <BranchSelect />}
        {groups.map(([g, items]) => {
          const vis = items.filter((x) => x.show)
          return vis.length ? <div key={g}>
            <div className="grp">{g}</div>
            {vis.map((x) => <button key={x.path} className={loc.pathname.startsWith(x.path) ? 'on' : ''}
              onClick={() => { nav(x.path); setOpen(false) }}><Icon name={x.icon} /><span>{x.label}</span>{!!x.badge && <span className="badge">{x.badge}</span>}</button>)}
          </div> : null
        })}
        <div className="me">
          <span className="av">{(me!.full_name || me!.email)[0].toUpperCase()}</span>
          <div style={{ flex: 1, lineHeight: 1.4, minWidth: 0, overflow: 'hidden' }}><b className="small" style={ellipsis}>{me!.full_name || me!.email}</b><div className="cap muted" style={ellipsis}>{role}</div></div>
          <LangToggle className="btn sm ghost" short />
          <button className="btn sm ghost" onClick={logout} title={t('common.logout')} aria-label={t('common.logout')} style={{ color: 'inherit' }}><Icon name="logout" /></button>
        </div>
      </aside>
      <div>
        <div className="topbar"><Logo biz={biz} title={title} sub={sub} />
          <button className="btn sm" onClick={() => setOpen(!open)} aria-label={t('common.menu')}><Icon name="menu" /></button></div>
        {ownerInBranch && <div className="imp" style={{ background: 'var(--brand-900)' }}><span><Icon name="store" /> <Trans i18nKey="nav.ownerIn" values={{ name: bName(branch!, i18n.language) }} components={{ b: <b /> }} /></span>
          <button className="btn sm" onClick={() => { setCompany(true); nav('/company') }}>{t('nav.backCompany')}</button></div>}
        {membership?.support && <SupportBanner />}
        {membership && !membership.support && <OfflineBanner />}
        <main>{children}</main>
      </div>
    </div>
  )
}

/** The till switches to offline selling by itself when the connection drops (D-013). */
function TillRoute() {
  const { online } = useOffline()
  return online ? <POS /> : <OfflinePOS />
}

function SupportBanner() {
  const { t } = useTranslation()
  const { membership } = useAuth()
  const end = async () => {
    await api(`/platform/tenants/${membership!.tenant_id}/support`, { method: 'DELETE' }).catch(() => undefined)
    sessionStorage.removeItem('qassa.tenant')
    window.location.assign('/platform/tenants')
  }
  return <div className="notice bad" style={{ margin: '12px 16px 0' }}><Icon name="shield" />
    <span className="grow">{t('pc.supportBanner', { name: membership!.tenant_name, until: new Date(membership!.expires_at!).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuwait' }) })}</span>
    <button className="btn sm" onClick={end}>{t('pc.endSupport')}</button></div>
}

const bName = (b: { name_ar: string; name_en?: string }, lang: string) => (lang === 'en' && b.name_en ? b.name_en : b.name_ar)

/** Reference: "🏢 كل الفروع" switches an all-branches member to the company view; picking a branch enters it. */
function BranchSelect() {
  const { t, i18n } = useTranslation()
  const { membership } = useAuth()
  const { branch, branches, setBranchId, company, setCompany } = useBranch()
  const nav = useNavigate()
  const canCo = !!membership?.all_branches
  if (branches.length < 2 && !canCo) return null
  return <select className="input" style={{ margin: '0 4px 6px', width: 'auto' }} aria-label={t('nav.branch')} value={company ? 'all' : branch?.id ?? ''}
    onChange={(e) => {
      if (e.target.value === 'all') { setCompany(true); nav('/company'); return }
      setBranchId(Number(e.target.value)); if (company) { setCompany(false); nav('/home') }
    }}>
    {canCo && <option value="all">{t('nav.allBranches')}</option>}
    {branches.map((b) => <option key={b.id} value={b.id}>{t('nav.branchOf', { name: bName(b, i18n.language) })}</option>)}
  </select>
}

function TenantPicker() {
  const { t, i18n } = useTranslation()
  const { me, chooseTenant, logout } = useAuth()
  useBizTheme('')
  return (
    <div className="login"><div className="card">
      <Logo biz="kids" title={t('app.name')} sub={t('app.tagline')} />
      <h1>{t('tenant.choose')}</h1>
      {me!.memberships.length === 0 && <p className="muted">{t('tenant.none')}</p>}
      <div className="list">{me!.memberships.map((m) => <button key={m.tenant_id} className="btn" style={{ justifyContent: 'space-between' }} onClick={() => chooseTenant(m.tenant_id)}>
        <span>{m.tenant_name}</span><span className="muted small">{i18n.language === 'en' ? m.role_name.en : m.role_name.ar}</span></button>)}</div>
      <button className="btn ghost" onClick={logout}>{t('common.logout')}</button>
    </div></div>
  )
}

export default function App() {
  const { t } = useTranslation()
  const { me, loading, membership, can } = useAuth()
  if (loading) return <div className="center muted">{t('common.loading')}</div>
  if (window.location.pathname === '/set-password') return <SetPassword />
  if (!me) return window.location.pathname === '/login' ? <Login /> : <Landing />

  if (me.is_platform_staff && !membership?.support) {
    return (
      <Shell biz="" plat title={t('app.name')} sub={t('platform.sub')} groups={[[t('platform.group'), [
        { path: '/platform/home', label: t('pc.home'), icon: 'home', show: true },
        { path: '/platform/tenants', label: t('platform.tenants'), icon: 'store', show: true },
        { path: '/platform/billing', label: t('pc.billing'), icon: 'receipt', show: true },
        { path: '/platform/support', label: t('pc.support'), icon: 'support', show: true },
        { path: '/platform/leads', label: t('pc.leads'), icon: 'user-plus', show: true },
        { path: '/platform/plans', label: t('platform.plans'), icon: 'layers', show: true },
        { path: '/platform/settings', label: t('pc.settings'), icon: 'settings', show: true },
      ]]]}>
        <Routes>
          <Route path="/platform/home" element={<PlatformHome />} />
          <Route path="/platform/tenants" element={<PlatformTenants />} />
          <Route path="/platform/billing" element={<PlatformBilling />} />
          <Route path="/platform/support" element={<PlatformSupport />} />
          <Route path="/platform/leads" element={<PlatformLeads />} />
          <Route path="/platform/plans" element={<PlatformPlans />} />
          <Route path="/platform/settings" element={<PlatformSettingsPage />} />
          <Route path="*" element={<Navigate to="/platform/home" replace />} />
        </Routes>
      </Shell>
    )
  }

  if (!membership) return <TenantPicker />
  return <BranchProvider canCompany={!!membership.all_branches && can('pos.invoices.view')}><OfflineProvider><TenantApp /></OfflineProvider></BranchProvider>
}

function TenantApp() {
  const { t, i18n } = useTranslation()
  const { membership: m, can } = useAuth()
  const membership = m!
  const { company, branch } = useBranch()
  const canCo = !!membership.all_branches && can('pos.invoices.view')
  const today = new Date(Date.now() - 4 * 3600e3).toLocaleDateString('en-CA', { timeZone: 'Asia/Kuwait' })
  const appts = useQuery({ enabled: !company && !!branch && can('booking.view'), queryKey: ['appointments', branch?.id, today], refetchInterval: 30000,
    queryFn: () => api<Appointment[]>(`/booking/appointments?branch_id=${branch!.id}&date=${today}`) })
  const waiting = (appts.data ?? []).filter((a) => a.status === 'booked' || a.status === 'arrived' || a.status === 'in_service').length
  const acc = (all: boolean): NavItem[] => [
    { path: '/accounting/statements', label: t('nav.statements'), icon: 'chart', show: can('accounting.view') && all },
    { path: '/accounting/expenses', label: t('nav.expenses'), icon: 'wallet', show: can('accounting.view') },
    { path: '/accounting/assets', label: t('nav.assets'), icon: 'box', show: can('accounting.view') },
    { path: '/accounting/settlements', label: t('nav.settlements'), icon: 'bank', show: can('accounting.view') },
    { path: '/accounting/journal', label: t('nav.journal'), icon: 'book', show: can('accounting.journal.post') },
    { path: '/accounting/trial-balance', label: t('nav.trialBalance'), icon: 'chart', show: can('accounting.view') },
    { path: '/accounting/periods', label: t('nav.periods'), icon: 'calendar', show: can('accounting.view') },
    { path: '/accounting/xbrl', label: t('nav.xbrl'), icon: 'file', show: can('accounting.view') && all },
  ]
  const system: NavItem[] = [
    { path: '/settings', label: t('nav.settingsSub'), icon: 'settings', show: can('org.manage') || can('data.export') },
    { path: '/subscription', label: t('nav.subscription'), icon: 'award', show: can('org.manage') },
    { path: '/whatsapp', label: t('nav.whatsapp'), icon: 'whatsapp', show: can('org.manage') },
    { path: '/support', label: t('nav.support'), icon: 'support', show: can('org.manage') && !membership.support },
  ]
  // Same menus as the reference (js/core/auth-nav.js CPAGES / PAGES), plus the accounting screens it doesn't have.
  const groups: [string, NavItem[]][] = company ? [
    [t('nav.g.company'), [
      { path: '/company', label: t('nav.overview'), icon: 'chart', show: true },
      { path: '/org', label: t('nav.branchesNav'), icon: 'store', show: true },
      { path: '/reports', label: t('nav.branchReports'), icon: 'trend', show: true },
    ]],
    [t('nav.g.central'), [
      { path: '/services', label: t('nav.services'), icon: 'sparkle', show: can('catalog.view') },
      { path: '/marketing', label: t('nav.offers'), icon: 'tag', show: can('catalog.view') },
      { path: '/loyalty', label: t('nav.loyalty'), icon: 'award', show: can('customers.view') },
      { path: '/customers', label: t('nav.customers'), icon: 'users', show: can('customers.view') },
      { path: '/staff', label: t('nav.staff'), icon: 'user', show: can('staff.view') },
      { path: '/commissions', label: t('nav.commissions'), icon: 'percent', show: can('commission.view.all') },
      { path: '/users', label: t('nav.users'), icon: 'user-plus', show: can('org.manage') },
    ]],
    [t('nav.accounting'), acc(true)],
    [t('nav.g.system'), system],
  ] : [
    [t('nav.g.main'), [
      { path: '/home', label: t('nav.home'), icon: 'home', show: true },
      { path: '/pos', label: t('nav.pos'), icon: 'cart', show: can('pos.sell') },
      { path: '/bookings', label: t('nav.bookingsShort'), icon: 'calendar', show: can('booking.view'), badge: waiting },
      { path: '/invoices', label: t('nav.invoices'), icon: 'receipt', show: can('pos.invoices.view') },
      { path: '/offline-receipts', label: t('nav.offline'), icon: 'refresh', show: can('pos.invoices.view') },
    ]],
    [t('nav.g.customers'), [
      { path: '/customers', label: t('nav.customers'), icon: 'users', show: can('customers.view') },
      { path: '/loyalty', label: t('nav.loyalty'), icon: 'award', show: can('customers.view') },
      { path: '/marketing', label: t('nav.marketing'), icon: 'tag', show: can('catalog.view') && !canCo },
    ]],
    [t('nav.g.services'), [
      { path: '/services', label: t('nav.services'), icon: 'sparkle', show: can('catalog.view') && !canCo },
      { path: '/inventory', label: t('nav.inventory'), icon: 'box', show: can('inventory.view') },
    ]],
    [t('nav.g.accounts'), [
      { path: '/staff', label: t('nav.staff'), icon: 'user', show: can('staff.view') },
      { path: '/accounting/expenses', label: t('nav.expenses'), icon: 'wallet', show: can('accounting.view') },
      { path: '/cash', label: t('nav.cashShort'), icon: 'bank', show: can('cash.session.open') },
      { path: '/reports', label: t('nav.reports'), icon: 'chart', show: can('pos.invoices.view') },
      { path: '/commissions', label: t('nav.commissions'), icon: 'percent', show: can('commission.view.all') && !canCo },
    ]],
    ...(canCo ? [] : [
      [t('nav.accounting'), acc(false).filter((x) => x.path !== '/accounting/expenses')],
      [t('nav.g.system'), [{ path: '/org', label: t('nav.org'), icon: 'store', show: true },
        { path: '/users', label: t('nav.users'), icon: 'user-plus', show: can('org.manage') }, ...system]],
    ] as [string, NavItem[]][]),
  ]
  const home = company ? '/company' : '/home'
  const sub = company || !branch ? t('nav.allBranchesSub') : t('nav.branchSub', { name: bName(branch, i18n.language) })
  return (
    <Shell biz={membership.tenant_business_type} title={membership.tenant_name} sub={sub} groups={groups}>
      <Routes>
        <Route path="/pos" element={<TillRoute />} />
        <Route path="/offline-receipts" element={<OfflineReceipts />} />
        <Route path="/bookings" element={<Bookings />} />
        <Route path="/invoices" element={<Invoices />} />
        <Route path="/cash" element={<Cash />} />
        <Route path="/org" element={<Org />} />
        <Route path="/services" element={<Services />} />
        <Route path="/staff" element={<Staff />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/marketing" element={<Marketing />} />
        <Route path="/loyalty" element={<Loyalty />} />
        <Route path="/commissions" element={<Commissions />} />
        <Route path="/users" element={<Users />} />
        <Route path="/support" element={<Support />} />
        <Route path="/home" element={<Home />} />
        <Route path="/company" element={<CompanyHome />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/whatsapp" element={<WhatsApp />} />
        <Route path="/subscription" element={<Subscription />} />
        <Route path="/accounting/journal" element={<JournalEntry />} />
        <Route path="/accounting/trial-balance" element={<TrialBalance />} />
        <Route path="/accounting/xbrl" element={<XbrlReport />} />
        <Route path="/accounting/statements" element={<Statements />} />
        <Route path="/accounting/expenses" element={<Expenses />} />
        <Route path="/accounting/assets" element={<Assets />} />
        <Route path="/accounting/settlements" element={<Settlements />} />
        <Route path="/accounting/periods" element={<Periods />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Shell>
  )
}
