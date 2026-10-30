import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Category, type Price, type Service } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { useOrg } from './Org'
import { ART_KEYS, ServiceArt, SvcIcon } from '../components/ServiceArt'

type Biz = Category['business_type']
const today = () => new Date().toISOString().slice(0, 10)

function PriceDialog({ service, onClose }: { service: Service; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const org = useOrg()
  const prices = useQuery({ queryKey: ['prices', service.id], queryFn: () => api<Price[]>(`/catalog/services/${service.id}/prices`) })
  const [form, setForm] = useState({ price: '', branch_id: '', valid_from: today() })
  const [key, setKey] = useState(() => crypto.randomUUID())
  const { save, busy, error } = useSave<Price>([['prices', service.id], ['services']], () => {
    toast(t('common.saved')); setForm({ ...form, price: '' }); setKey(crypto.randomUUID())
  })
  const branchName = (id: number | null) => {
    const b = org.data?.branches.find((x) => x.id === id)
    return b ? nameOf(b, i18n.language) : t('svc.allBranches')
  }
  const submit = () => save({
    path: `/catalog/services/${service.id}/prices`, idempotencyKey: key,
    body: { price: form.price, branch_id: form.branch_id ? Number(form.branch_id) : null, valid_from: form.valid_from },
  })
  return (
    <Dialog open wide title={t('svc.pricesOf', { name: nameOf(service, i18n.language) })} onClose={onClose}
      onSubmit={can('catalog.price.change') ? submit : undefined} submitLabel={t('svc.setPrice')} busy={busy}>
      <div className="notice info"><Icon name="info" />{t('svc.priceRule')}</div>
      <div className="tw"><table><thead><tr><th>{t('acc.branch')}</th><th className="n">{t('svc.price')}</th><th>{t('svc.from')}</th><th>{t('svc.to')}</th></tr></thead>
        <tbody>{prices.data?.map((p) => <tr key={p.id}><td>{branchName(p.branch)}</td><td className="n money">{formatKWD(p.price, i18n.language as 'ar' | 'en')}</td>
          <td className="num">{p.valid_from}</td><td className="num">{p.valid_to ?? (p.valid_from > today() ? <span className="pill info">{t('svc.upcoming')}</span> : <span className="pill good">{t('svc.current')}</span>)}</td></tr>)}
          {prices.data?.length === 0 && <tr><td colSpan={4} className="empty">{t('svc.noPrice')}</td></tr>}</tbody></table></div>
      {can('catalog.price.change') && <>
        <h3>{t('svc.newPrice')}</h3>
        <div className="two">
          <label className="field">{t('svc.price')} (KWD)<input className="input" dir="ltr" inputMode="decimal" pattern="\d+(\.\d{1,3})?" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required /></label>
          <label className="field">{t('svc.from')}<input className="input" type="date" min={today()} value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} required /></label>
        </div>
        <label className="field">{t('acc.branch')}<select className="input" value={form.branch_id} onChange={(e) => setForm({ ...form, branch_id: e.target.value })}>
          <option value="">{t('svc.allBranches')}</option>
          {org.data?.branches.map((b) => <option key={b.id} value={b.id}>{nameOf(b, i18n.language)}</option>)}</select></label>
        <ErrorText error={error} />
      </>}
    </Dialog>
  )
}

export default function Services() {
  const { t, i18n } = useTranslation()
  const { can, membership } = useAuth()
  const toast = useToast()
  const [biz, setBiz] = useState<Biz>(membership!.tenant_business_type)
  const [q, setQ] = useState('')
  const cats = useQuery({ queryKey: ['categories'], queryFn: () => api<Category[]>('/catalog/categories') })
  const services = useQuery({ queryKey: ['services'], queryFn: () => api<Service[]>('/catalog/services') })
  const [svcForm, setSvcForm] = useState<{ id?: number; category: string; name_ar: string; name_en: string; duration_minutes: string; home_visit: boolean; art: string; is_active: boolean; price: string } | null>(null)
  const [catForm, setCatForm] = useState<{ name_ar: string; name_en: string } | null>(null)
  const [pricesFor, setPricesFor] = useState<Service | null>(null)
  const svcSave = useSave<Service>([['services']], () => { setSvcForm(null); toast(t('common.saved')) })
  const catSave = useSave<Category>([['categories']], () => { setCatForm(null); toast(t('common.saved')) })

  const myCats = (cats.data ?? []).filter((c) => c.business_type === biz)
  const rows = (services.data ?? []).filter((s) => s.business_type === biz &&
    (!q || s.name_ar.includes(q) || s.name_en.toLowerCase().includes(q.toLowerCase())))
  const catName = (id: number) => { const c = cats.data?.find((x) => x.id === id); return c ? nameOf(c, i18n.language) : '' }

  const openSvc = (s?: Service) => {
    svcSave.reset()
    setSvcForm(s ? { id: s.id, category: String(s.category), name_ar: s.name_ar, name_en: s.name_en, duration_minutes: String(s.duration_minutes), home_visit: s.home_visit, art: s.art ?? '', is_active: s.is_active, price: '' }
      : { category: myCats[0] ? String(myCats[0].id) : '', name_ar: '', name_en: '', duration_minutes: '30', home_visit: false, art: '', is_active: true, price: '' })
  }
  const submitSvc = () => {
    const { id, price, ...rest } = svcForm!
    const body: Record<string, unknown> = { ...rest, category: Number(rest.category), duration_minutes: Number(rest.duration_minutes) }
    if (!id && price) body.price = price
    svcSave.save({ path: id ? `/catalog/services/${id}` : '/catalog/services', method: id ? 'PATCH' : 'POST', body })
  }

  if (services.isError) return <ErrorText error={services.error} />
  return (
    <>
      <Head title={t('nav.services')} sub={t('svc.sub')}>
        <input className="input" placeholder={t('svc.search')} style={{ width: 200 }} value={q} onChange={(e) => setQ(e.target.value)} />
        {can('catalog.manage') && <button className="btn" onClick={() => { catSave.reset(); setCatForm({ name_ar: '', name_en: '' }) }}><Icon name="plus" />{t('svc.addCategory')}</button>}
        {can('catalog.manage') && <button className="btn primary" disabled={!myCats.length} onClick={() => openSvc()}><Icon name="plus" />{t('svc.add')}</button>}
      </Head>
      <div className="seg" style={{ marginBottom: 14 }}>
        {(['kids', 'men', 'women'] as const).map((b) => <button key={b} className={biz === b ? 'on' : ''} onClick={() => setBiz(b)}>{t(`biz.${b}`)}</button>)}
      </div>
      {!myCats.length && !cats.isPending && <div className="notice"><Icon name="info" />{t('svc.noCategories')}</div>}
      <div className="tw"><table><thead><tr><th>{t('svc.service')}</th><th>{t('svc.category')}</th><th>{t('svc.duration')}</th><th className="n">{t('svc.price')}</th><th>{t('org.status')}</th><th></th></tr></thead>
        <tbody>{rows.map((s) => <tr key={s.id}>
          <td><div className="row" style={{ flexWrap: 'nowrap' }}><SvcIcon s={s} size={34} /><b>{nameOf(s, i18n.language)}</b>{s.home_visit && <span className="pill info">{t('svc.homeVisit')}</span>}</div></td>
          <td>{catName(s.category)}</td><td><bdi>{s.duration_minutes}</bdi> {t('svc.min')}</td>
          <td className="n money">{s.current_price ? formatKWD(s.current_price, i18n.language as 'ar' | 'en') : <span className="pill warn">{t('svc.noPrice')}</span>}</td>
          <td>{s.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill mute">{t('common.inactive')}</span>}</td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>
            <button className="btn sm" onClick={() => setPricesFor(s)}>{t('svc.prices')}</button>
            {can('catalog.manage') && <button className="btn sm" onClick={() => openSvc(s)}>{t('common.edit')}</button>}</td></tr>)}
          {rows.length === 0 && <tr><td colSpan={6} className="empty">{services.isPending ? t('common.loading') : t('common.empty')}</td></tr>}</tbody></table></div>

      <Dialog open={!!svcForm} title={svcForm?.id ? t('svc.edit') : t('svc.add')} onClose={() => setSvcForm(null)} onSubmit={submitSvc} busy={svcSave.busy}>
        {svcForm && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={svcForm.name_ar} onChange={(e) => setSvcForm({ ...svcForm, name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={svcForm.name_en} onChange={(e) => setSvcForm({ ...svcForm, name_en: e.target.value })} /></label>
          </div>
          <div className="two">
            <label className="field">{t('svc.category')}<select className="input" value={svcForm.category} onChange={(e) => setSvcForm({ ...svcForm, category: e.target.value })}>
              {myCats.map((c) => <option key={c.id} value={c.id}>{nameOf(c, i18n.language)}</option>)}</select></label>
            <label className="field">{t('svc.duration')} ({t('svc.min')})<input className="input" type="number" min={5} max={600} step={5} value={svcForm.duration_minutes} onChange={(e) => setSvcForm({ ...svcForm, duration_minutes: e.target.value })} required /></label>
          </div>
          {!svcForm.id && can('catalog.price.change') && <label className="field">{t('svc.price')} (KWD)<input className="input" dir="ltr" inputMode="decimal" pattern="\d+(\.\d{1,3})?" value={svcForm.price} onChange={(e) => setSvcForm({ ...svcForm, price: e.target.value })} /></label>}
          {svcForm.id && <div className="small muted">{t('svc.priceViaHistory')}</div>}
          <div className="field">{t('svc.art')}<div className="row" style={{ gap: 6 }}>
            <button type="button" className={`btn sm${svcForm.art === '' ? ' primary' : ''}`} onClick={() => setSvcForm({ ...svcForm, art: '' })}>{t('svc.artAuto')}</button>
            {ART_KEYS.map((k) => <button type="button" key={k} title={k} aria-pressed={svcForm.art === k} onClick={() => setSvcForm({ ...svcForm, art: k })}
              style={{ padding: 2, borderRadius: 12, border: `2px solid ${svcForm.art === k ? 'var(--brand)' : 'transparent'}`, background: 'none', cursor: 'pointer' }}><ServiceArt art={k} size={36} /></button>)}
          </div></div>
          <label className="chk"><span>{t('svc.homeVisit')}<small>{t('svc.homeVisitHelp')}</small></span><input type="checkbox" className="sw" checked={svcForm.home_visit} onChange={(e) => setSvcForm({ ...svcForm, home_visit: e.target.checked })} /></label>
          {svcForm.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={svcForm.is_active} onChange={(e) => setSvcForm({ ...svcForm, is_active: e.target.checked })} /></label>}
          <ErrorText error={svcSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!catForm} title={t('svc.addCategory')} onClose={() => setCatForm(null)} busy={catSave.busy}
        onSubmit={() => catSave.save({ path: '/catalog/categories', body: { ...catForm, business_type: biz, sort: myCats.length } })}>
        {catForm && <>
          <div className="small muted">{t('svc.categoryFor', { biz: t(`biz.${biz}`) })}</div>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={catForm.name_ar} onChange={(e) => setCatForm({ ...catForm, name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={catForm.name_en} onChange={(e) => setCatForm({ ...catForm, name_en: e.target.value })} /></label>
          </div>
          <ErrorText error={catSave.error} />
        </>}
      </Dialog>

      {pricesFor && <PriceDialog service={pricesFor} onClose={() => setPricesFor(null)} />}
    </>
  )
}
