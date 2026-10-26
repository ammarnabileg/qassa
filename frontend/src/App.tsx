import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { LangToggle } from './components/ErrorText'
import { Icon, Logo, useBizTheme, type Biz } from './components/ui'
import Customers from './pages/Customers'
import JournalEntry from './pages/JournalEntry'
import Login from './pages/Login'
import Org from './pages/Org'
import { PlatformPlans, PlatformTenants } from './pages/Platform'
import Services from './pages/Services'
import Staff from './pages/Staff'
import Subscription from './pages/Subscription'
import TrialBalance from './pages/TrialBalance'

const ellipsis = { display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } as const

type NavItem = { path: string; label: string; icon: string; show: boolean }

function Shell({ biz, plat, title, sub, groups, children }: {
  biz: Biz; plat?: boolean; title: string; sub: string; groups: [string, NavItem[]][]; children: React.ReactNode
}) {
  const { t, i18n } = useTranslation()
  const { me, membership, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useBizTheme(biz)
  const role = membership ? (i18n.language === 'en' ? membership.role_name.en : membership.role_name.ar) : t('platform.staff')
  return (
    <div className="app">
      <aside className={`nav${plat ? ' plat' : ''}${open ? ' open' : ''}`}>
        <Logo biz={biz} title={title} sub={sub} />
        {groups.map(([g, items]) => {
          const vis = items.filter((x) => x.show)
          return vis.length ? <div key={g}>
            <div className="grp">{g}</div>
            {vis.map((x) => <button key={x.path} className={loc.pathname.startsWith(x.path) ? 'on' : ''}
              onClick={() => { nav(x.path); setOpen(false) }}><Icon name={x.icon} /><span>{x.label}</span></button>)}
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
        <main>{children}</main>
      </div>
    </div>
  )
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
  if (!me) return <Login />

  if (me.is_platform_staff && me.memberships.length === 0) {
    return (
      <Shell biz="" plat title={t('app.name')} sub={t('platform.sub')} groups={[[t('platform.group'), [
        { path: '/platform/tenants', label: t('platform.tenants'), icon: 'store', show: true },
        { path: '/platform/plans', label: t('platform.plans'), icon: 'layers', show: true },
      ]]]}>
        <Routes>
          <Route path="/platform/tenants" element={<PlatformTenants />} />
          <Route path="/platform/plans" element={<PlatformPlans />} />
          <Route path="*" element={<Navigate to="/platform/tenants" replace />} />
        </Routes>
      </Shell>
    )
  }

  if (!membership) return <TenantPicker />
  const groups: [string, NavItem[]][] = [
    [t('nav.setup'), [
      { path: '/org', label: t('nav.org'), icon: 'store', show: true },
      { path: '/services', label: t('nav.services'), icon: 'tag', show: can('catalog.view') },
      { path: '/staff', label: t('nav.staff'), icon: 'users', show: can('staff.view') },
      { path: '/customers', label: t('nav.customers'), icon: 'user', show: can('customers.view') },
    ]],
    [t('nav.accounting'), [
      { path: '/accounting/journal', label: t('nav.journal'), icon: 'book', show: can('accounting.journal.post') },
      { path: '/accounting/trial-balance', label: t('nav.trialBalance'), icon: 'chart', show: can('accounting.view') },
    ]],
    [t('nav.account'), [
      { path: '/subscription', label: t('nav.subscription'), icon: 'wallet', show: can('org.manage') },
    ]],
  ]
  return (
    <Shell biz={membership.tenant_business_type} title={membership.tenant_name} sub={t(`biz.${membership.tenant_business_type}`)} groups={groups}>
      <Routes>
        <Route path="/org" element={<Org />} />
        <Route path="/services" element={<Services />} />
        <Route path="/staff" element={<Staff />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/subscription" element={<Subscription />} />
        <Route path="/accounting/journal" element={<JournalEntry />} />
        <Route path="/accounting/trial-balance" element={<TrialBalance />} />
        <Route path="*" element={<Navigate to="/org" replace />} />
      </Routes>
    </Shell>
  )
}
