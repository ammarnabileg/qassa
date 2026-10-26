import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Service, type Staff as StaffT } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { useOrg } from './Org'

type Form = { id?: number; full_name_ar: string; full_name_en: string; phone: string; is_active: boolean; branch_ids: number[]; service_ids: number[] }

export default function Staff() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const org = useOrg()
  const staff = useQuery({ queryKey: ['staff'], queryFn: () => api<StaffT[]>('/staff') })
  const services = useQuery({ queryKey: ['services'], queryFn: () => api<Service[]>('/catalog/services'), enabled: can('catalog.view') })
  const [form, setForm] = useState<Form | null>(null)
  const { save, busy, error, reset } = useSave<StaffT>([['staff'], ['subscription']], () => { setForm(null); toast(t('common.saved')) })
  const lang = i18n.language
  const branchName = (id: number) => { const b = org.data?.branches.find((x) => x.id === id); return b ? nameOf(b, lang) : '' }
  const toggle = (k: 'branch_ids' | 'service_ids', id: number) =>
    setForm({ ...form!, [k]: form![k].includes(id) ? form![k].filter((x) => x !== id) : [...form![k], id] })
  const open = (s?: StaffT) => { reset(); setForm(s ? { ...s } : { full_name_ar: '', full_name_en: '', phone: '', is_active: true, branch_ids: [], service_ids: [] }) }
  const submit = () => { const { id, ...body } = form!; save({ path: id ? `/staff/${id}` : '/staff', method: id ? 'PATCH' : 'POST', body }) }

  if (staff.isError) return <ErrorText error={staff.error} />
  return (
    <>
      <Head title={t('nav.staff')} sub={t('staff.sub')}>
        {can('staff.manage') && <button className="btn primary" onClick={() => open()}><Icon name="plus" />{t('staff.add')}</button>}
      </Head>
      <div className="tw"><table><thead><tr><th>{t('staff.name')}</th><th>{t('acc.branch')}</th><th>{t('staff.skills')}</th><th>{t('org.phone')}</th><th>{t('org.status')}</th><th></th></tr></thead>
        <tbody>{staff.data?.map((s) => <tr key={s.id}>
          <td><b>{lang === 'en' && s.full_name_en ? s.full_name_en : s.full_name_ar}</b></td>
          <td>{s.branch_ids.map(branchName).join('، ') || '—'}</td>
          <td><bdi>{s.service_ids.length}</bdi> {t('staff.servicesCount')}</td>
          <td className="num">{s.phone || '—'}</td>
          <td>{s.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill mute">{t('common.inactive')}</span>}</td>
          <td>{can('staff.manage') && <button className="btn sm" onClick={() => open(s)}>{t('common.edit')}</button>}</td></tr>)}
          {staff.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('common.empty')}</td></tr>}
          {staff.isPending && <tr><td colSpan={6} className="empty">{t('common.loading')}</td></tr>}</tbody></table></div>

      <Dialog open={!!form} wide title={form?.id ? t('staff.edit') : t('staff.add')} onClose={() => setForm(null)} onSubmit={submit} busy={busy}>
        {form && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={form.full_name_ar} onChange={(e) => setForm({ ...form, full_name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={form.full_name_en} onChange={(e) => setForm({ ...form, full_name_en: e.target.value })} /></label>
          </div>
          <label className="field">{t('org.phone')}<input className="input" dir="ltr" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <div className="field">{t('staff.branches')}<div className="chips">
            {org.data?.branches.map((b) => <label key={b.id}><input type="checkbox" checked={form.branch_ids.includes(b.id)} onChange={() => toggle('branch_ids', b.id)} />{nameOf(b, lang)}</label>)}</div></div>
          <div className="field">{t('staff.skills')}<div className="chips">
            {services.data?.filter((s) => s.is_active).map((s) => <label key={s.id}><input type="checkbox" checked={form.service_ids.includes(s.id)} onChange={() => toggle('service_ids', s.id)} />{nameOf(s, lang)}</label>)}
            {services.data?.length === 0 && <span className="small muted">{t('staff.noServices')}</span>}</div></div>
          {form.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /></label>}
          <ErrorText error={error} />
        </>}
      </Dialog>
    </>
  )
}
