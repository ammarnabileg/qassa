import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Branch, type LegalEntity } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'

export type OrgData = { legal_entities: LegalEntity[]; branches: Branch[] }
export const useOrg = () => useQuery({ queryKey: ['org'], queryFn: () => api<OrgData>('/org') })

type Form = { id?: number; legal_entity: number; name_ar: string; name_en: string; code: string; business_type: Branch['business_type']; address: string; phone: string; is_active: boolean }

export default function Org() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const q = useOrg()
  const [form, setForm] = useState<Form | null>(null)
  const { save, busy, error, reset } = useSave<Branch>([['org'], ['subscription']], () => { setForm(null); toast(t('common.saved')) })
  if (q.isPending) return <p className="muted">{t('common.loading')}</p>
  if (q.isError) return <><ErrorText error={q.error} /><button className="btn" onClick={() => q.refetch()}>{t('common.retry')}</button></>
  const entity = q.data.legal_entities[0]
  const open = (b?: Branch) => { reset(); setForm(b ? { ...b } : { legal_entity: entity.id, name_ar: '', name_en: '', code: '', business_type: 'kids', address: '', phone: '', is_active: true }) }
  const submit = () => {
    const { id, ...body } = form!
    save({ path: id ? `/org/branches/${id}` : '/org/branches', method: id ? 'PATCH' : 'POST', body })
  }
  const set = (k: keyof Form, v: unknown) => setForm({ ...form!, [k]: v })
  return (
    <>
      <Head title={t('nav.org')} sub={t('org.sub')}>
        {can('org.manage') && <button className="btn primary" onClick={() => open()}><Icon name="plus" />{t('org.addBranch')}</button>}
      </Head>
      <div className="grid">
        <div className="tw"><table><thead><tr><th>{t('acc.entity')}</th><th>{t('org.cr')}</th><th>{t('org.currency')}</th></tr></thead>
          <tbody>{q.data.legal_entities.map((e) => <tr key={e.id}><td><b>{nameOf(e, i18n.language)}</b></td><td className="num">{e.commercial_registration || '—'}</td><td>{e.base_currency}</td></tr>)}</tbody></table></div>
        <div className="tw"><table><thead><tr><th>{t('org.code')}</th><th>{t('acc.branch')}</th><th>{t('org.type')}</th><th>{t('org.phone')}</th><th>{t('org.status')}</th><th></th></tr></thead>
          <tbody>{q.data.branches.map((b) => <tr key={b.id}><td className="num">{b.code}</td><td><b>{nameOf(b, i18n.language)}</b><div className="cap muted">{b.address}</div></td>
            <td><span className="pill info">{t(`biz.${b.business_type}`)}</span></td><td className="num">{b.phone || '—'}</td>
            <td>{b.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill mute">{t('common.inactive')}</span>}</td>
            <td>{can('org.manage') && <button className="btn sm" onClick={() => open(b)}>{t('common.edit')}</button>}</td></tr>)}</tbody></table></div>
      </div>
      <Dialog open={!!form} title={form?.id ? t('org.editBranch') : t('org.addBranch')} onClose={() => setForm(null)} onSubmit={submit} busy={busy}>
        {form && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={form.name_ar} onChange={(e) => set('name_ar', e.target.value)} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={form.name_en} onChange={(e) => set('name_en', e.target.value)} /></label>
          </div>
          <div className="two">
            <label className="field">{t('org.code')}<input className="input" dir="ltr" value={form.code} onChange={(e) => set('code', e.target.value.toUpperCase())} pattern="[A-Za-z0-9_-]+" required /></label>
            <label className="field">{t('org.type')}<select className="input" value={form.business_type} onChange={(e) => set('business_type', e.target.value)}>
              {(['kids', 'men', 'women'] as const).map((x) => <option key={x} value={x}>{t(`biz.${x}`)}</option>)}</select></label>
          </div>
          <div className="two">
            <label className="field">{t('org.phone')}<input className="input" dir="ltr" inputMode="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} /></label>
            <label className="field">{t('org.address')}<input className="input" value={form.address} onChange={(e) => set('address', e.target.value)} /></label>
          </div>
          {form.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} /></label>}
          <ErrorText error={error} />
        </>}
      </Dialog>
    </>
  )
}
