import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Member } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { useOrg } from './Org'

const ROLES = ['operations_manager', 'branch_manager', 'cashier', 'service_provider', 'inventory_officer', 'accountant', 'finance_manager', 'auditor', 'owner']
type Form = { id?: number; email: string; full_name: string; phone: string; role: string; all_branches: boolean; branch_ids: number[]; discount_limit_percent: string; is_active: boolean }
type Delivery = { channel: 'email' | 'whatsapp' | 'manual' | 'existing_account'; to?: string; link?: string }

export default function Users() {
  const { t, i18n } = useTranslation()
  const { me } = useAuth()
  const toast = useToast()
  const org = useOrg()
  const list = useQuery({ queryKey: ['users'], queryFn: () => api<Member[]>('/users') })
  const [form, setForm] = useState<Form | null>(null)
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  const { save, busy, error, reset } = useSave<Member & { delivery?: Delivery }>([['users']], (r) => {
    setForm(null)
    if (r.delivery) setDelivery(r.delivery); else toast(t('common.saved'))
  })
  const resend = useSave<{ delivery: Delivery }>([['users']], (r) => setDelivery(r.delivery))
  const branchName = (id: number) => { const b = org.data?.branches.find((x) => x.id === id); return b ? nameOf(b, i18n.language) : '' }
  const submit = () => {
    const { id, email, full_name, phone, ...rest } = form!
    save(id ? { path: `/users/${id}`, method: 'PATCH', body: rest } : { path: '/users', body: { email, full_name, phone, ...rest } })
  }
  return (
    <>
      <Head title={t('nav.users')} sub={t('usr.sub')}>
        <button className="btn primary" onClick={() => { reset(); setForm({ email: '', full_name: '', phone: '', role: 'cashier', all_branches: false, branch_ids: [], discount_limit_percent: '0', is_active: true }) }}><Icon name="user-plus" />{t('usr.invite')}</button>
      </Head>
      <ErrorText error={list.error} />
      <div className="tw"><table><thead><tr><th>{t('staff.name')}</th><th>{t('auth.email')}</th><th>{t('usr.role')}</th><th>{t('org.branches')}</th><th>{t('org.status')}</th><th /></tr></thead>
        <tbody>{list.data?.map((m) => <tr key={m.id}>
          <td><b>{m.full_name || '—'}</b></td><td className="num" dir="ltr" style={{ textAlign: 'start' }}>{m.email}</td>
          <td><span className="pill info">{i18n.language === 'en' ? m.role_name.en : m.role_name.ar}</span></td>
          <td className="small">{m.all_branches ? t('svc.allBranches') : m.branch_ids.map(branchName).join('، ')}</td>
          <td>{!m.is_active ? <span className="pill mute">{t('common.inactive')}</span> : m.has_password ? <span className="pill good">{t('common.active')}</span> : <span className="pill warn">{t('usr.invited')}</span>}</td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>
            {!m.has_password && <button className="btn sm" disabled={resend.busy} onClick={() => resend.save({ path: `/users/${m.id}/resend` })}>{t('usr.resend')}</button>}
            {m.user_id !== me?.id && <button className="btn sm" onClick={() => { reset(); setForm({ ...m }) }}>{t('common.edit')}</button>}</td></tr>)}</tbody></table></div>

      <Dialog open={!!form} title={form?.id ? t('common.edit') : t('usr.invite')} onClose={() => setForm(null)} onSubmit={submit} busy={busy}>
        {form && <>
          {!form.id && <>
            <div className="two">
              <label className="field">{t('staff.name')}<input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></label>
              <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
            </div>
            <label className="field">{t('usr.phone')}<input className="input" dir="ltr" inputMode="tel" placeholder="5xxxxxxx" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          </>}
          <label className="field">{t('usr.role')}<select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map((r) => <option key={r} value={r}>{t(`usr.r.${r}`)}</option>)}</select></label>
          <label className="chk">{t('svc.allBranches')}<input type="checkbox" className="sw" checked={form.all_branches} onChange={(e) => setForm({ ...form, all_branches: e.target.checked })} /></label>
          {!form.all_branches && <div className="chips">{org.data?.branches.map((b) => <label key={b.id}><input type="checkbox" checked={form.branch_ids.includes(b.id)}
            onChange={() => setForm({ ...form, branch_ids: form.branch_ids.includes(b.id) ? form.branch_ids.filter((x) => x !== b.id) : [...form.branch_ids, b.id] })} />{nameOf(b, i18n.language)}</label>)}</div>}
          <label className="field">{t('usr.discountLimit')}<input className="input" type="number" min={0} max={100} value={form.discount_limit_percent} onChange={(e) => setForm({ ...form, discount_limit_percent: e.target.value })} /></label>
          {form.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /></label>}
          <ErrorText error={error} />
        </>}
      </Dialog>

      <Dialog open={!!delivery} title={t('usr.inviteSent')} onClose={() => setDelivery(null)}>
        {delivery && <>
          {delivery.channel === 'email' && <div className="notice good">{t('usr.byEmail')}</div>}
          {delivery.channel === 'whatsapp' && <div className="notice good">{t('usr.byWhatsapp', { to: delivery.to })}</div>}
          {delivery.channel === 'existing_account' && <div className="notice info">{t('usr.existing')}</div>}
          {delivery.channel === 'manual' && <>
            <div className="notice">{t('usr.manual')}</div>
            <code className="code" style={{ wordBreak: 'break-all', letterSpacing: 0 }}>{delivery.link}</code>
            <button className="btn" onClick={() => navigator.clipboard.writeText(delivery.link!).then(() => toast(t('usr.copied')))}><Icon name="copy" />{t('usr.copy')}</button>
          </>}
        </>}
      </Dialog>
    </>
  )
}
