import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Beneficiary, type Customer } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, useToast } from '../components/ui'

type CForm = { id?: number; full_name: string; phone: string; email: string; preferred_language: 'ar' | 'en'; whatsapp_opt_in: boolean; marketing_opt_in: boolean; notes: string; add_self: boolean }
type BForm = { id?: number; full_name: string; relation: Beneficiary['relation']; birth_date: string; gender: Beneficiary['gender']; notes: string }

const age = (d: string | null) => {
  if (!d) return null
  const b = new Date(d), n = new Date()
  return n.getFullYear() - b.getFullYear() - (n < new Date(n.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0)
}
const display = (phone: string) => phone.startsWith('965') && phone.length === 11 ? `+965 ${phone.slice(3, 7)} ${phone.slice(7)}` : `+${phone}`

export default function Customers() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const [q, setQ] = useState('')
  const list = useQuery({ queryKey: ['customers', q], queryFn: () => api<Customer[]>(`/customers?q=${encodeURIComponent(q)}`) })
  const [cForm, setCForm] = useState<CForm | null>(null)
  const [profile, setProfile] = useState<number | null>(null)
  const [bForm, setBForm] = useState<BForm | null>(null)
  const current = useQuery({ queryKey: ['customer', profile], enabled: !!profile, queryFn: () => api<Customer>(`/customers/${profile}`) })
  const cSave = useSave<Customer>([['customers'], ['customer']], (c) => { setCForm(null); toast(t('common.saved')); if (!cForm?.id) setProfile(c.id) })
  const bSave = useSave<Beneficiary>([['customers'], ['customer']], () => { setBForm(null); toast(t('common.saved')) })
  const manage = can('customers.manage')

  const openNew = () => { cSave.reset(); setCForm({ full_name: '', phone: '', email: '', preferred_language: 'ar', whatsapp_opt_in: true, marketing_opt_in: false, notes: '', add_self: true }) }
  const submitC = () => { const { id, ...body } = cForm!; cSave.save({ path: id ? `/customers/${id}` : '/customers', method: id ? 'PATCH' : 'POST', body }) }
  const submitB = () => {
    const { id, ...rest } = bForm!
    const body = { ...rest, birth_date: rest.birth_date || null }
    bSave.save({ path: id ? `/beneficiaries/${id}` : `/customers/${profile}/beneficiaries`, method: id ? 'PATCH' : 'POST', body })
  }
  const c = current.data

  return (
    <>
      <Head title={t('nav.customers')} sub={t('cust.sub')}>
        <input className="input" placeholder={t('cust.search')} style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />
        {manage && <button className="btn primary" onClick={openNew}><Icon name="plus" />{t('cust.add')}</button>}
      </Head>
      <ErrorText error={list.error} />
      <div className="tw"><table><thead><tr><th>{t('cust.name')}</th><th>{t('org.phone')}</th><th>{t('cust.beneficiaries')}</th><th>{t('cust.whatsapp')}</th><th></th></tr></thead>
        <tbody>{list.data?.map((x) => <tr key={x.id} className="click" onClick={() => setProfile(x.id)}>
          <td><b>{x.full_name}</b>{x.notes && <> <span className="pill info">{t('cust.note')}</span></>}</td>
          <td className="num" dir="ltr" style={{ textAlign: 'start' }}>{display(x.phone)}</td>
          <td>{x.beneficiaries.filter((b) => b.relation !== 'self').map((b) => b.full_name).join('، ') || '—'}</td>
          <td>{x.whatsapp_opt_in ? <span className="pill good">{t('common.yes')}</span> : <span className="pill mute">{t('common.no')}</span>}</td>
          <td><Icon name="chevron-left" /></td></tr>)}
          {list.data?.length === 0 && <tr><td colSpan={5} className="empty">{q ? t('cust.noMatch') : t('common.empty')}</td></tr>}
          {list.isPending && <tr><td colSpan={5} className="empty">{t('common.loading')}</td></tr>}</tbody></table></div>

      <Dialog open={!!cForm} title={cForm?.id ? t('cust.edit') : t('cust.add')} onClose={() => setCForm(null)} onSubmit={submitC} busy={cSave.busy}>
        {cForm && <>
          <div className="two">
            <label className="field">{t('cust.name')}<input className="input" value={cForm.full_name} onChange={(e) => setCForm({ ...cForm, full_name: e.target.value })} required /></label>
            <label className="field">{t('org.phone')}<input className="input" dir="ltr" inputMode="tel" placeholder="5555 1234" value={cForm.phone} onChange={(e) => setCForm({ ...cForm, phone: e.target.value })} required /></label>
          </div>
          <div className="two">
            <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" value={cForm.email} onChange={(e) => setCForm({ ...cForm, email: e.target.value })} /></label>
            <label className="field">{t('cust.lang')}<select className="input" value={cForm.preferred_language} onChange={(e) => setCForm({ ...cForm, preferred_language: e.target.value as 'ar' | 'en' })}>
              <option value="ar">العربية</option><option value="en">English</option></select></label>
          </div>
          <label className="field">{t('cust.notes')}<textarea className="input" value={cForm.notes} onChange={(e) => setCForm({ ...cForm, notes: e.target.value })} /></label>
          <label className="chk"><span>{t('cust.whatsapp')}<small>{t('cust.whatsappHelp')}</small></span><input type="checkbox" className="sw" checked={cForm.whatsapp_opt_in} onChange={(e) => setCForm({ ...cForm, whatsapp_opt_in: e.target.checked })} /></label>
          <label className="chk"><span>{t('cust.marketing')}<small>{t('cust.marketingHelp')}</small></span><input type="checkbox" className="sw" checked={cForm.marketing_opt_in} onChange={(e) => setCForm({ ...cForm, marketing_opt_in: e.target.checked })} /></label>
          {!cForm.id && <label className="chk"><span>{t('cust.addSelf')}<small>{t('cust.addSelfHelp')}</small></span><input type="checkbox" className="sw" checked={cForm.add_self} onChange={(e) => setCForm({ ...cForm, add_self: e.target.checked })} /></label>}
          <ErrorText error={cSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!profile && !cForm} wide title={c ? c.full_name : t('common.loading')} onClose={() => setProfile(null)}>
        {c && <>
          <div className="row sb">
            <div className="row"><bdi className="num" dir="ltr">{display(c.phone)}</bdi>
              <a className="btn sm" href={`https://wa.me/${c.phone}`} target="_blank" rel="noreferrer"><Icon name="whatsapp" />{t('cust.message')}</a></div>
            {manage && <button className="btn sm" onClick={() => { cSave.reset(); setCForm({ ...c, add_self: false }) }}><Icon name="edit" />{t('common.edit')}</button>}
          </div>
          {c.notes && <div className="notice"><Icon name="alert" />{c.notes}</div>}
          <div className="row sb"><h3>{t('cust.beneficiaries')}</h3>
            {manage && <button className="btn sm primary" onClick={() => { bSave.reset(); setBForm({ full_name: '', relation: 'child', birth_date: '', gender: '', notes: '' }) }}><Icon name="plus" />{t('cust.addBeneficiary')}</button>}</div>
          <div className="list">{c.beneficiaries.map((b) => <div className="li" key={b.id}>
            <span className="av">{b.full_name[0]}</span>
            <div className="grow"><b>{b.full_name}</b> <span className="pill mute">{t(`cust.rel.${b.relation}`)}</span>
              <div className="cap muted">{[age(b.birth_date) !== null ? `${age(b.birth_date)} ${t('cust.years')}` : '', b.notes].filter(Boolean).join(' · ')}</div></div>
            {manage && <button className="btn sm" onClick={() => { bSave.reset(); setBForm({ id: b.id, full_name: b.full_name, relation: b.relation, birth_date: b.birth_date ?? '', gender: b.gender, notes: b.notes }) }}>{t('common.edit')}</button>}
          </div>)}</div>
        </>}
      </Dialog>

      <Dialog open={!!bForm} title={bForm?.id ? t('cust.editBeneficiary') : t('cust.addBeneficiary')} onClose={() => setBForm(null)} onSubmit={submitB} busy={bSave.busy}>
        {bForm && <>
          <div className="two">
            <label className="field">{t('cust.name')}<input className="input" value={bForm.full_name} onChange={(e) => setBForm({ ...bForm, full_name: e.target.value })} required /></label>
            <label className="field">{t('cust.relation')}<select className="input" value={bForm.relation} onChange={(e) => setBForm({ ...bForm, relation: e.target.value as Beneficiary['relation'] })}>
              {(['child', 'self', 'other'] as const).map((r) => <option key={r} value={r}>{t(`cust.rel.${r}`)}</option>)}</select></label>
          </div>
          <div className="two">
            <label className="field">{t('cust.birthDate')}<input className="input" type="date" value={bForm.birth_date} onChange={(e) => setBForm({ ...bForm, birth_date: e.target.value })} /></label>
            <label className="field">{t('cust.gender')}<select className="input" value={bForm.gender} onChange={(e) => setBForm({ ...bForm, gender: e.target.value as Beneficiary['gender'] })}>
              <option value="">—</option><option value="m">{t('cust.male')}</option><option value="f">{t('cust.female')}</option></select></label>
          </div>
          <label className="field">{t('cust.bNotes')}<textarea className="input" value={bForm.notes} onChange={(e) => setBForm({ ...bForm, notes: e.target.value })} /></label>
          <ErrorText error={bSave.error} />
        </>}
      </Dialog>
    </>
  )
}
