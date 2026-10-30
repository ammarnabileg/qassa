import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, getTenant, ApiError, type Branch, type LegalEntity } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { useNavigate } from 'react-router-dom'
import { useBranch } from '../branch'
import { formatKWD } from '../money'

export type OrgData = { legal_entities: LegalEntity[]; branches: Branch[] }
/** Company and branches. The last copy is kept per company so the till still knows its branch offline (D-013). */
export const useOrg = () => useQuery({
  queryKey: ['org', getTenant()],
  queryFn: async () => {
    const key = `qassa.org.${getTenant()}`
    try {
      const d = await api<OrgData>('/org')
      try { localStorage.setItem(key, JSON.stringify(d)) } catch { /* storage unavailable */ }
      return d
    } catch (e) {
      const cached = e instanceof ApiError && e.status === 0 ? localStorage.getItem(key) : null
      if (cached) return JSON.parse(cached) as OrgData
      throw e
    }
  },
})

type Form = { id?: number; legal_entity: number; name_ar: string; name_en: string; code: string; business_type: Branch['business_type']; address: string; phone: string; latitude: string; longitude: string; opens_at: string; closes_at: string; online_booking: boolean; is_active: boolean }

export default function Org() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const q = useOrg()
  const { membership } = useAuth()
  const { setBranchId, setCompany } = useBranch()
  const nav = useNavigate()
  const month = useQuery({ enabled: can('pos.invoices.view'), queryKey: ['rep-branches'], queryFn: () => api<{ branch_id: number; month: string }[]>('/reports/branches') })
  const [form, setForm] = useState<Form | null>(null)
  const { save, busy, error, reset } = useSave<Branch>([['org'], ['subscription']], () => { setForm(null); toast(t('common.saved')) })
  if (q.isPending) return <p className="muted">{t('common.loading')}</p>
  if (q.isError) return <><ErrorText error={q.error} /><button className="btn" onClick={() => q.refetch()}>{t('common.retry')}</button></>
  const entity = q.data.legal_entities[0]
  const open = (b?: Branch) => { reset(); setForm(b ? { ...b, latitude: b.latitude ?? '', longitude: b.longitude ?? '', opens_at: b.opens_at.slice(0, 5), closes_at: b.closes_at.slice(0, 5) } : { legal_entity: entity.id, name_ar: '', name_en: '', code: '', business_type: 'kids', address: '', phone: '', latitude: '', longitude: '', opens_at: '10:00', closes_at: '22:00', online_booking: true, is_active: true }) }
  const submit = () => {
    const { id, ...rest } = form!
    const body = { ...rest, latitude: rest.latitude || null, longitude: rest.longitude || null }
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
        {/* branch cards like the reference (c-branches) */}
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 12 }}>
          {q.data.branches.map((b) => { const m = month.data?.find((x) => x.branch_id === b.id)
            return <div className="card" key={b.id} style={{ display: 'grid', gap: 6 }}>
              <div className="row sb"><span style={{ fontSize: 22 }}>📍</span>{b.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill mute">{t('common.inactive')}</span>}</div>
              <h3>{t('nav.branchSub', { name: nameOf(b, i18n.language) })} <span className="cap muted num">{b.code}</span></h3>
              {b.address && <div className="small muted">{b.address}</div>}
              <div className="small"><span className="pill info">{t(`biz.${b.business_type}`)}</span> {b.phone && <bdi className="num">☎ {b.phone}</bdi>}</div>
              {m && <div className="row sb small"><span className="muted">{t('home.salesMonth')}</span><b className="money">{formatKWD(m.month, i18n.language as 'ar' | 'en')}</b></div>}
              <div className="row" style={{ marginTop: 4 }}>
                {membership?.all_branches && b.is_active && <button className="btn sm primary" onClick={() => { setBranchId(b.id); setCompany(false); nav('/home') }}>{t('home.enterBranch')}</button>}
                {can('org.manage') && <button className="btn sm" onClick={() => open(b)}>{t('common.edit')}</button>}
                {b.phone && <a className="btn sm ghost" style={{ color: '#25D366' }} href={`https://wa.me/${b.phone.replace(/\D/g, '')}`} target="_blank" rel="noreferrer" aria-label="WhatsApp"><Icon name="whatsapp" /></a>}
              </div></div> })}
        </div>
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
          <div className="two">
            <label className="field">{t('org.opens')}<input className="input" type="time" value={form.opens_at} onChange={(e) => set('opens_at', e.target.value)} /></label>
            <label className="field">{t('org.closes')}<input className="input" type="time" value={form.closes_at} onChange={(e) => set('closes_at', e.target.value)} /></label>
          </div>
          <div className="two">
            <label className="field">{t('org.lat')}<input className="input" dir="ltr" inputMode="decimal" placeholder="29.3375" value={form.latitude} onChange={(e) => set('latitude', e.target.value)} /></label>
            <label className="field">{t('org.lng')}<input className="input" dir="ltr" inputMode="decimal" placeholder="48.0281" value={form.longitude} onChange={(e) => set('longitude', e.target.value)} /></label>
          </div>
          <div className="small muted">{t('org.locationHelp')}</div>
          <label className="chk"><span>{t('org.online')}<small>{t('org.onlineHelp')}</small></span><input type="checkbox" className="sw" checked={form.online_booking} onChange={(e) => set('online_booking', e.target.checked)} /></label>
          {form.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} /></label>}
          <ErrorText error={error} />
        </>}
      </Dialog>
    </>
  )
}
