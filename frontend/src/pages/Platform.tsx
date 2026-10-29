import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Domain, type Plan, type TenantRow } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { SupportAccessDialog } from './PlatformConsole'

type BizT = 'kids' | 'men' | 'women'
const STATUS_PILL: Record<string, string> = { trial: 'info', active: 'good', past_due: 'warn', read_only: 'warn', suspended: 'bad' }
const usePlans = () => useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/platform/plans') })

function OnboardDialog({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const plans = usePlans()
  const [key] = useState(() => crypto.randomUUID())
  const [f, setF] = useState({ tenant_name: '', legal_name_ar: '', legal_name_en: '', commercial_registration: '', owner_name: '', owner_email: '', business_type: 'kids' as BizT, plan_code: 'basic' })
  const [branches, setBranches] = useState([{ name_ar: '', name_en: '', code: 'MAIN', business_type: 'kids' as BizT }])
  const { save, busy, error } = useSave<{ id: number; slug: string }>([['tenants']], (r) => { toast(t('platform.created', { slug: r.slug })); onClose() })
  const plan = plans.data?.find((p) => p.code === f.plan_code)
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v })
  const setB = (i: number, k: string, v: string) => setBranches(branches.map((b, j) => (j === i ? { ...b, [k]: v } : b)))
  return (
    <Dialog open wide title={t('platform.onboard')} onClose={onClose} busy={busy} submitLabel={t('platform.create')}
      onSubmit={() => save({ path: '/platform/tenants', idempotencyKey: key, body: { ...f, branches } })}>
      <h3>{t('platform.company')}</h3>
      <div className="two">
        <label className="field">{t('platform.tenantName')}<input className="input" value={f.tenant_name} onChange={(e) => set('tenant_name', e.target.value)} required /></label>
        <label className="field">{t('platform.plan')}<select className="input" value={f.plan_code} onChange={(e) => set('plan_code', e.target.value)}>
          {plans.data?.map((p) => <option key={p.code} value={p.code}>{nameOf(p, i18n.language)} — {formatKWD(p.monthly_price, i18n.language as 'ar' | 'en')}</option>)}</select></label>
      </div>
      <div className="two">
        <label className="field">{t('platform.legalAr')}<input className="input" value={f.legal_name_ar} onChange={(e) => set('legal_name_ar', e.target.value)} required /></label>
        <label className="field">{t('platform.legalEn')}<input className="input" dir="ltr" value={f.legal_name_en} onChange={(e) => set('legal_name_en', e.target.value)} /></label>
      </div>
      <div className="two">
        <label className="field">{t('org.cr')}<input className="input" dir="ltr" value={f.commercial_registration} onChange={(e) => set('commercial_registration', e.target.value)} /></label>
        <label className="field">{t('platform.mainType')}<select className="input" value={f.business_type} onChange={(e) => set('business_type', e.target.value)}>
          {(['kids', 'men', 'women'] as const).map((x) => <option key={x} value={x}>{t(`biz.${x}`)}</option>)}</select></label>
      </div>
      <h3>{t('platform.owner')}</h3>
      <div className="two">
        <label className="field">{t('platform.ownerName')}<input className="input" value={f.owner_name} onChange={(e) => set('owner_name', e.target.value)} required /></label>
        <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" value={f.owner_email} onChange={(e) => set('owner_email', e.target.value)} required /></label>
      </div>
      <div className="row sb"><h3>{t('org.branches')}</h3>
        <button type="button" className="btn sm" disabled={!!plan && branches.length >= plan.max_branches}
          onClick={() => setBranches([...branches, { name_ar: '', name_en: '', code: `B${branches.length + 1}`, business_type: f.business_type }])}><Icon name="plus" />{t('org.addBranch')}</button></div>
      {plan && <div className="small muted">{t('platform.planAllows', { n: plan.max_branches >= 99 ? t('plan.unlimited') : plan.max_branches })}</div>}
      {branches.map((b, i) => <div className="row" key={i} style={{ flexWrap: 'nowrap' }}>
        <input className="input" placeholder={t('common.nameAr')} value={b.name_ar} onChange={(e) => setB(i, 'name_ar', e.target.value)} required />
        <input className="input" dir="ltr" style={{ width: 110 }} placeholder={t('org.code')} value={b.code} onChange={(e) => setB(i, 'code', e.target.value.toUpperCase())} required />
        <select className="input" style={{ width: 120 }} value={b.business_type} onChange={(e) => setB(i, 'business_type', e.target.value)}>
          {(['kids', 'men', 'women'] as const).map((x) => <option key={x} value={x}>{t(`biz.${x}`)}</option>)}</select>
        {branches.length > 1 && <button type="button" className="btn sm ghost" aria-label={t('common.remove')} onClick={() => setBranches(branches.filter((_, j) => j !== i))}><Icon name="trash" /></button>}
      </div>)}
      <div className="notice"><Icon name="info" />{t('platform.ownerInviteNote')}</div>
      <ErrorText error={error} />
    </Dialog>
  )
}

function ManageDialog({ tenant, onClose }: { tenant: TenantRow; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const plans = usePlans()
  const domains = useQuery({ queryKey: ['domains', tenant.id], queryFn: () => api<Domain[]>(`/platform/tenants/${tenant.id}/domains`) })
  const [f, setF] = useState({ status: tenant.status, plan_code: tenant.plan ?? 'basic', owner_phone: tenant.owner_phone ? tenant.owner_phone.replace(/^965/, '') : '', reason: '' })
  const [host, setHost] = useState('')
  const change = useSave<TenantRow>([['tenants']], () => { toast(t('common.saved')); onClose() })
  const addDomain = useSave<Domain>([['domains', tenant.id]], () => { setHost(''); toast(t('common.saved')) })
  const toggle = useSave<Domain>([['domains', tenant.id], ['tenants']], () => toast(t('common.saved')))
  const plan = plans.data?.find((p) => p.code === f.plan_code)
  return (
    <Dialog open wide title={tenant.name} onClose={onClose} busy={change.busy}
      onSubmit={() => change.save({ path: `/platform/tenants/${tenant.id}`, method: 'PATCH', body: f })}>
      <div className="two">
        <label className="field">{t('platform.status')}<select className="input" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
          {Object.keys(STATUS_PILL).map((s) => <option key={s} value={s}>{t(`platform.st.${s}`)}</option>)}</select></label>
        <label className="field">{t('platform.plan')}<select className="input" value={f.plan_code} onChange={(e) => setF({ ...f, plan_code: e.target.value })}>
          {plans.data?.map((p) => <option key={p.code} value={p.code}>{nameOf(p, i18n.language)}</option>)}</select></label>
      </div>
      <label className="field">{t('platform.ownerPhone')}<input className="input" dir="ltr" inputMode="tel" placeholder="5xxxxxxx" value={f.owner_phone} onChange={(e) => setF({ ...f, owner_phone: e.target.value })} /></label>
      <div className="small muted">{t('platform.ownerPhoneHelp')}</div>
      <label className="field">{t('platform.reason')}<input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} required /></label>
      <ErrorText error={change.error} />
      <h3>{t('platform.domains')}</h3>
      <div className="small muted">{t('platform.domainsHelp')}</div>
      <div className="list">{domains.data?.map((d) => <div className="li" key={d.id}>
        <Icon name="link" /><div className="grow"><span className="code">{d.host}</span> <span className="pill mute">{t(`platform.kind.${d.kind}`)}</span></div>
        {d.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill warn">{t('platform.pending')}</span>}
        <button type="button" className="btn sm" disabled={toggle.busy || !f.reason}
          onClick={() => toggle.save({ path: `/platform/domains/${d.id}`, method: 'PATCH', body: { is_active: !d.is_active, reason: f.reason } })}>
          {d.is_active ? t('platform.deactivate') : t('platform.activate')}</button>
      </div>)}</div>
      <ErrorText error={toggle.error} />
      {plan?.custom_domain ? <div className="row" style={{ flexWrap: 'nowrap' }}>
        <input className="input" dir="ltr" placeholder="book.salon.com" value={host} onChange={(e) => setHost(e.target.value)} />
        <button type="button" className="btn" disabled={!host || addDomain.busy} onClick={() => addDomain.save({ path: `/platform/tenants/${tenant.id}/domains`, body: { host } })}><Icon name="plus" />{t('platform.addDomain')}</button>
      </div> : <div className="notice"><Icon name="info" />{t('platform.noCustomDomain')}</div>}
      <ErrorText error={addDomain.error} />
    </Dialog>
  )
}

export function PlatformTenants() {
  const { t, i18n } = useTranslation()
  const q = useQuery({ queryKey: ['tenants'], queryFn: () => api<TenantRow[]>('/platform/tenants') })
  const [onboard, setOnboard] = useState(false)
  const [manage, setManage] = useState<TenantRow | null>(null)
  const [support, setSupport] = useState<TenantRow | null>(null)
  const rows = q.data ?? []
  const plans = usePlans()
  const planName = (code: string | null) => { const p = plans.data?.find((x) => x.code === code); return p ? nameOf(p, i18n.language) : code ?? '—' }
  return (
    <>
      <Head title={t('platform.tenants')} sub={t('platform.tenantsSub')}>
        <button className="btn primary" onClick={() => setOnboard(true)}><Icon name="plus" />{t('platform.onboard')}</button>
      </Head>
      <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('platform.total')} value={<bdi>{rows.length}</bdi>} />
        <Stat label={t('platform.st.active')} value={<bdi>{rows.filter((r) => r.status === 'active').length}</bdi>} />
        <Stat label={t('platform.st.trial')} value={<bdi>{rows.filter((r) => r.status === 'trial').length}</bdi>} />
        <Stat label={t('platform.branchesTotal')} value={<bdi>{rows.reduce((a, r) => a + r.branches, 0)}</bdi>} />
      </div>
      <ErrorText error={q.error} />
      <div className="tw"><table><thead><tr><th>{t('platform.company')}</th><th>{t('org.type')}</th><th>{t('platform.plan')}</th><th>{t('org.branches')}</th><th>{t('platform.appLink')}</th><th>{t('platform.status')}</th><th></th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}>
          <td><b>{r.name}</b><div className="cap muted code">{r.slug}</div></td>
          <td><span className="pill info">{t(`biz.${r.default_business_type}`)}</span></td>
          <td>{planName(r.plan)}</td><td><bdi>{r.branches}</bdi></td>
          <td>{r.hosts.map((h) => <div key={h}><a className="small" href={`https://${h}`} target="_blank" rel="noreferrer" dir="ltr">{h}</a></div>)}</td>
          <td><span className={`pill ${STATUS_PILL[r.status]}`}>{t(`platform.st.${r.status}`)}</span></td>
          <td className="row" style={{ flexWrap: 'nowrap' }}><button className="btn sm" onClick={() => setManage(r)}>{t('platform.manage')}</button>
            <button className="btn sm ghost" onClick={() => setSupport(r)}><Icon name="eye" />{t('pc.viewAs')}</button></td></tr>)}
          {q.isPending && <tr><td colSpan={7} className="empty">{t('common.loading')}</td></tr>}</tbody></table></div>
      {onboard && <OnboardDialog onClose={() => setOnboard(false)} />}
      {manage && <ManageDialog tenant={manage} onClose={() => setManage(null)} />}
      <SupportAccessDialog tenant={support} onClose={() => setSupport(null)} />
    </>
  )
}

export function PlatformPlans() {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const plans = usePlans()
  const [edit, setEdit] = useState<Plan | null>(null)
  const { save, busy, error, reset } = useSave<Plan>([['plans']], () => { setEdit(null); toast(t('common.saved')) })
  const lang = i18n.language as 'ar' | 'en'
  return (
    <>
      <Head title={t('platform.plans')} sub={t('platform.plansSub')} />
      <div className="cards">{plans.data?.map((p) => <div key={p.id} className="plan">
        <div className="row sb"><b>{nameOf(p, lang)}</b><button className="btn sm" onClick={() => { reset(); setEdit({ ...p }) }}>{t('common.edit')}</button></div>
        <div className="price">{formatKWD(p.monthly_price, lang)}<span className="small muted"> / {t('plan.month')}</span></div>
        <ul>
          <li><Icon name="store" />{t('plan.branches', { n: p.max_branches >= 99 ? t('plan.unlimited') : p.max_branches })}</li>
          <li><Icon name="users" />{t('plan.staff', { n: p.max_staff >= 99 ? t('plan.unlimited') : p.max_staff })}</li>
          <li><Icon name="link" />{p.custom_domain ? t('plan.customDomain') : t('plan.subdomain')}</li>
        </ul>
      </div>)}</div>
      <Dialog open={!!edit} title={t('platform.editPlan')} onClose={() => setEdit(null)} busy={busy}
        onSubmit={() => { const { id, code, ...body } = edit!; void code; save({ path: `/platform/plans/${id}`, method: 'PATCH', body: { ...body, features_ar: body.features_ar?.map((x) => x.trim()).filter(Boolean), features_en: body.features_en?.map((x) => x.trim()).filter(Boolean) } }) }}>
        {edit && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} required /></label>
          </div>
          <label className="field">{t('platform.monthly')} (KWD)<input className="input" dir="ltr" inputMode="decimal" pattern="\d+(\.\d{1,3})?" value={edit.monthly_price} onChange={(e) => setEdit({ ...edit, monthly_price: e.target.value })} required /></label>
          <div className="two">
            <label className="field">{t('platform.maxBranches')}<input className="input" type="number" min={1} value={edit.max_branches} onChange={(e) => setEdit({ ...edit, max_branches: Number(e.target.value) })} /></label>
            <label className="field">{t('platform.maxStaff')}<input className="input" type="number" min={1} value={edit.max_staff} onChange={(e) => setEdit({ ...edit, max_staff: Number(e.target.value) })} /></label>
          </div>
          <label className="chk">{t('plan.customDomain')}<input type="checkbox" className="sw" checked={edit.custom_domain} onChange={(e) => setEdit({ ...edit, custom_domain: e.target.checked })} /></label>
          <label className="chk">{t('site.popular')}<input type="checkbox" className="sw" checked={!!edit.highlight} onChange={(e) => setEdit({ ...edit, highlight: e.target.checked })} /></label>
          <div className="two">
            <label className="field">{t('pc.featuresAr')}<textarea className="input" rows={5} value={(edit.features_ar ?? []).join('\n')} onChange={(e) => setEdit({ ...edit, features_ar: e.target.value.split('\n') })} /></label>
            <label className="field">{t('pc.featuresEn')}<textarea className="input" dir="ltr" rows={5} value={(edit.features_en ?? []).join('\n')} onChange={(e) => setEdit({ ...edit, features_en: e.target.value.split('\n') })} /></label>
          </div>
          <div className="cap muted">{t('pc.featuresHelp')}</div>
          <ErrorText error={error} />
        </>}
      </Dialog>
    </>
  )
}
