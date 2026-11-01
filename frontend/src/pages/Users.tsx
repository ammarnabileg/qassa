import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Member } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { PermissionPicker } from '../components/PermissionPicker'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { useOrg } from './Org'

type Form = { id?: number; email: string; full_name: string; phone: string; role: string; all_branches: boolean; branch_ids: number[]; discount_limit_percent: string; is_active: boolean; how?: 'link' | 'password'; password?: string; permissions?: string[] }
type Delivery = { channel: 'email' | 'whatsapp' | 'manual' | 'existing_account' | 'password_set'; to?: string; link?: string; text?: string; phone?: string }

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
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => api<RolesData>('/roles') })
  const [tab, setTab] = useState<'users' | 'roles'>('users')
  const roleOf = (key: string) => roles.data?.roles.find((r) => r.key === key)
  const roleName = (key: string) => { const r = roleOf(key); return r ? (i18n.language === 'en' ? r.name_en : r.name_ar) : key }
  const branchName = (id: number) => { const b = org.data?.branches.find((x) => x.id === id); return b ? nameOf(b, i18n.language) : '' }
  const submit = () => {
    const { id, email, full_name, phone, how, password, ...rest } = form!
    save(id ? { path: `/users/${id}`, method: 'PATCH', body: { ...rest, ...(rest.role === 'owner' ? { permissions: undefined } : {}) } } : { path: '/users', body: { email, full_name, phone, ...rest, password: how === 'password' ? password : '' } })
  }
  return (
    <>
      <Head title={t('nav.users')} sub={t('usr.sub')}>
        <button className="btn primary" onClick={() => { reset(); setForm({ email: '', full_name: '', phone: '', role: 'cashier', all_branches: false, branch_ids: [], discount_limit_percent: '0', is_active: true }) }}><Icon name="user-plus" />{t('usr.invite')}</button>
      </Head>
      <div className="tabs"><button className={tab === 'users' ? 'on' : ''} onClick={() => setTab('users')}>{t('usr.tabUsers')}</button>
        <button className={tab === 'roles' ? 'on' : ''} onClick={() => setTab('roles')}>{t('usr.tabRoles')}</button></div>
      {tab === 'roles' && roles.data && <RolesTab data={roles.data} />}
      <ErrorText error={list.error} />
      {tab === 'users' && <div className="tw"><table><thead><tr><th>{t('staff.name')}</th><th>{t('auth.email')}</th><th>{t('usr.role')}</th><th>{t('org.branches')}</th><th>{t('org.status')}</th><th /></tr></thead>
        <tbody>{list.data?.map((m) => <tr key={m.id}>
          <td><b>{m.full_name || '—'}</b></td><td className="num" dir="ltr" style={{ textAlign: 'start' }}>{m.email}</td>
          <td><span className="pill info">{roleName(m.role)}</span>{(m.extra_permissions.length > 0 || m.denied_permissions.length > 0) && <> <span className="pill warn">{t('usr.custom')}</span></>}</td>
          <td className="small">{m.all_branches ? t('svc.allBranches') : m.branch_ids.map(branchName).join('، ')}</td>
          <td>{!m.is_active ? <span className="pill mute">{t('common.inactive')}</span> : m.has_password ? <span className="pill good">{t('common.active')}</span> : <span className="pill warn">{t('usr.invited')}</span>}</td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>
            {!m.has_password && <button className="btn sm" disabled={resend.busy} onClick={() => resend.save({ path: `/users/${m.id}/resend` })}>{t('usr.resend')}</button>}
            {m.user_id !== me?.id && <button className="btn sm" onClick={() => { reset(); setForm({ ...m }) }}>{t('common.edit')}</button>}</td></tr>)}</tbody></table></div>}

      <Dialog open={!!form} title={form?.id ? t('common.edit') : t('usr.invite')} onClose={() => setForm(null)} onSubmit={submit} busy={busy}>
        {form && <>
          {!form.id && <>
            <div className="two">
              <label className="field">{t('staff.name')}<input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required /></label>
              <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
            </div>
            <label className="field">{t('usr.phone')}<input className="input" dir="ltr" inputMode="tel" placeholder="5xxxxxxx" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
            <div className="seg"><button type="button" className={form.how !== 'password' ? 'on' : ''} onClick={() => setForm({ ...form, how: 'link' })}>{t('usr.howLink')}</button>
              <button type="button" className={form.how === 'password' ? 'on' : ''} onClick={() => setForm({ ...form, how: 'password' })}>{t('usr.howPassword')}</button></div>
            {form.how === 'password' ? <label className="field">{t('usr.password')}<input className="input" dir="ltr" type="text" autoComplete="new-password" value={form.password ?? ''} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={10} />
              <small className="muted">{t('usr.passwordHelp')}</small></label>
              : <div className="small muted">{t('usr.howLinkHelp')}</div>}
          </>}
          <label className="field">{t('usr.role')}<select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value, permissions: form.id ? roleOf(e.target.value)?.permissions : undefined })}>
            {(roles.data?.roles ?? []).map((r) => <option key={r.key} value={r.key}>{i18n.language === 'en' ? r.name_en : r.name_ar}</option>)}</select></label>
          <label className="chk">{t('svc.allBranches')}<input type="checkbox" className="sw" checked={form.all_branches} onChange={(e) => setForm({ ...form, all_branches: e.target.checked })} /></label>
          {!form.all_branches && <div className="chips">{org.data?.branches.map((b) => <label key={b.id}><input type="checkbox" checked={form.branch_ids.includes(b.id)}
            onChange={() => setForm({ ...form, branch_ids: form.branch_ids.includes(b.id) ? form.branch_ids.filter((x) => x !== b.id) : [...form.branch_ids, b.id] })} />{nameOf(b, i18n.language)}</label>)}</div>}
          <label className="field">{t('usr.discountLimit')}<input className="input" type="number" min={0} max={100} value={form.discount_limit_percent} onChange={(e) => setForm({ ...form, discount_limit_percent: e.target.value })} /></label>
          {form.id && roles.data && <>
            <h3 style={{ marginTop: 10 }}>{t('usr.permissions')}</h3>
            {form.role === 'owner' ? <div className="notice">{t('usr.ownerAll')}</div> : <>
              <div className="row sb"><span className="small muted">{t('usr.permsHelp')}</span>
                <button type="button" className="btn sm" onClick={() => setForm({ ...form, permissions: roleOf(form.role)?.permissions })}>{t('usr.resetToRole')}</button></div>
              <PermissionPicker catalog={roles.data.catalog} base={roleOf(form.role)?.permissions} value={form.permissions ?? []} onChange={(v) => setForm({ ...form, permissions: v })} />
            </>}
          </>}
          {form.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /></label>}
          <ErrorText error={error} />
        </>}
      </Dialog>

      <Dialog open={!!delivery} title={t('usr.inviteSent')} onClose={() => setDelivery(null)}>
        {delivery && <>
          {delivery.channel === 'email' && <div className="notice good">{t('usr.byEmail')}</div>}
          {delivery.channel === 'whatsapp' && <div className="notice good">{t('usr.byWhatsapp', { to: delivery.to })}</div>}
          {delivery.channel === 'existing_account' && <div className="notice info">{t('usr.existing')}</div>}
          {delivery.channel === 'password_set' && <div className="notice good">{t('usr.passwordSet')}</div>}
          {delivery.channel === 'manual' && <>
            <div className="notice">{t('usr.manual')}</div>
            <code className="code" style={{ wordBreak: 'break-all', letterSpacing: 0 }}>{delivery.link}</code>
            <div className="row" style={{ gap: 8 }}>
              <a className="btn primary" style={{ background: '#25D366', borderColor: '#25D366' }} target="_blank" rel="noreferrer"
                href={`https://wa.me/${delivery.phone ?? ''}?text=${encodeURIComponent(delivery.text ?? delivery.link ?? '')}`}><Icon name="whatsapp" />{t('usr.sendWa')}</a>
              <button className="btn" onClick={() => navigator.clipboard.writeText(delivery.link!).then(() => toast(t('usr.copied')))}><Icon name="copy" />{t('usr.copy')}</button>
            </div>
          </>}
        </>}
      </Dialog>
    </>
  )
}

type RoleRow = { id: number; key: string; name_ar: string; name_en: string; permissions: string[]; is_system: boolean; editable: boolean; members: number }
type RolesData = { roles: RoleRow[]; catalog: string[] }

/** Edit what each role can do, or add a custom role. The owner role always has everything. */
function RolesTab({ data }: { data: RolesData }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const [edit, setEdit] = useState<{ id?: number; name_ar: string; name_en: string; permissions: string[]; is_system?: boolean } | null>(null)
  const { save, busy, error, reset } = useSave<RoleRow>([['roles'], ['users']], () => { setEdit(null); toast(t('common.saved')) })
  const del = useSave<unknown>([['roles']], () => { setEdit(null); toast(t('common.saved')) })
  return <>
    <div className="row sb" style={{ margin: '10px 0' }}><span className="small muted">{t('usr.rolesHelp')}</span>
      <button className="btn" onClick={() => { reset(); setEdit({ name_ar: '', name_en: '', permissions: [] }) }}><Icon name="plus" />{t('usr.newRole')}</button></div>
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 12 }}>
      {data.roles.map((r) => <div className="card" key={r.id}>
        <div className="row sb"><b>{i18n.language === 'en' ? r.name_en : r.name_ar}</b>{!r.is_system && <span className="pill info">{t('usr.custom')}</span>}</div>
        <div className="cap muted" style={{ margin: '4px 0 8px' }}>{t('usr.members', { n: r.members })} · {r.key === 'owner' ? t('usr.ownerAll') : `${r.permissions.length} / ${data.catalog.length}`}</div>
        {r.editable && <button className="btn sm" onClick={() => { reset(); setEdit({ id: r.id, name_ar: r.name_ar, name_en: r.name_en, permissions: r.permissions, is_system: r.is_system }) }}>{t('usr.editRole')}</button>}
      </div>)}
    </div>
    <Dialog open={!!edit} wide title={edit?.id ? t('usr.editRole') : t('usr.newRole')} onClose={() => setEdit(null)} busy={busy}
      onSubmit={() => { const { id, is_system, ...body } = edit!; void is_system; save(id ? { path: `/roles/${id}`, method: 'PATCH', body } : { path: '/roles', body }) }}>
      {edit && <>
        <div className="two">
          <label className="field">{t('usr.roleName')}<input className="input" value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} required /></label>
          <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /></label>
        </div>
        {!edit.id && <label className="field">{t('usr.copyFrom')}<select className="input" value="" onChange={(e) => { const r = data.roles.find((x) => x.key === e.target.value); if (r) setEdit({ ...edit, permissions: r.key === 'owner' ? data.catalog : r.permissions }) }}>
          <option value="">—</option>{data.roles.map((r) => <option key={r.key} value={r.key}>{i18n.language === 'en' ? r.name_en : r.name_ar}</option>)}</select></label>}
        <PermissionPicker catalog={data.catalog} value={edit.permissions} onChange={(v) => setEdit({ ...edit, permissions: v })} />
        <ErrorText error={error ?? del.error} />
        {edit.id && !edit.is_system && <button type="button" className="btn danger" disabled={del.busy} onClick={() => del.save({ path: `/roles/${edit.id}`, method: 'DELETE' })}>{t('usr.deleteRole')}</button>}
      </>}
    </Dialog>
  </>
}
