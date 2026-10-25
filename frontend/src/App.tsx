import { useTranslation } from 'react-i18next'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { LangToggle } from './components/ErrorText'
import JournalEntry from './pages/JournalEntry'
import Login from './pages/Login'
import Org from './pages/Org'
import TrialBalance from './pages/TrialBalance'

function TenantPicker() {
  const { t, i18n } = useTranslation()
  const { me, chooseTenant, logout } = useAuth()
  return (
    <div className="center"><div className="card grid" style={{ width: 'min(420px,100%)' }}>
      <h1>{t('tenant.choose')}</h1>
      {me!.memberships.length === 0 && <p className="muted">{t('tenant.none')}</p>}
      {me!.memberships.map((m) => <button key={m.tenant_id} className="btn" onClick={() => chooseTenant(m.tenant_id)}>
        {m.tenant_name} · <span className="muted small">{i18n.language === 'en' ? m.role_name.en : m.role_name.ar}</span></button>)}
      <button className="btn ghost" onClick={logout}>{t('common.logout')}</button>
    </div></div>
  )
}

export default function App() {
  const { t, i18n } = useTranslation()
  const { me, loading, membership, can, logout } = useAuth()
  if (loading) return <div className="center muted">{t('common.loading')}</div>
  if (!me) return <Login />
  if (!membership) return <TenantPicker />
  return (
    <div className="shell">
      <nav className="nav">
        <div style={{ padding: '4px 12px 14px' }}><b>{membership.tenant_name}</b><div className="small muted">{i18n.language === 'en' ? membership.role_name.en : membership.role_name.ar}</div></div>
        <NavLink to="/org">{t('nav.org')}</NavLink>
        {can('accounting.journal.post') && <NavLink to="/accounting/journal">{t('nav.journal')}</NavLink>}
        {can('accounting.view') && <NavLink to="/accounting/trial-balance">{t('nav.trialBalance')}</NavLink>}
        <div className="foot"><LangToggle /><button className="btn ghost" onClick={logout}>{t('common.logout')}</button></div>
      </nav>
      <main>
        <Routes>
          <Route path="/org" element={<Org />} />
          <Route path="/accounting/journal" element={<JournalEntry />} />
          <Route path="/accounting/trial-balance" element={<TrialBalance />} />
          <Route path="*" element={<Navigate to="/org" replace />} />
        </Routes>
      </main>
    </div>
  )
}
