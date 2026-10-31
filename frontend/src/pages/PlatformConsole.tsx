import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'

type Dash = {
  tenants: Record<string, number>; branches: number; mrr: string; arr: string; overdue: { count: number; amount: string }; new_leads: number
  history: { month: string; invoiced: string; collected: string }[]; plans: { code: string; name_ar: string; name_en: string; tenants: number }[]
  renewals: { tenant_id: number; name: string; status: string; plan: string; plan_en: string; period_end: string }[]
  tickets: { id: number; subject: string; tenant: string; priority: string; status: string }[]
}
export type SubInvoice = { id: number; number: string; tenant: number; tenant_name: string; plan_name_ar: string; plan_name_en: string; period_start: string; period_end: string
  amount: string; due_on: string; status: 'issued' | 'paid' | 'void'; overdue: boolean; paid_at: string | null; paid_method: string; paid_reference: string }
export type Ticket = { id: number; tenant: number; tenant_name: string; subject: string; priority: 'low' | 'mid' | 'high'; status: 'open' | 'pending' | 'closed'
  created_at: string; updated_at: string; messages: { id: number; from_platform: boolean; author_name: string; body: string; created_at: string }[] }
type Lead = { id: number; salon_name: string; contact_name: string; phone: string; email: string; business_type: string; branches: number; plan_code: string
  city: string; message: string; status: 'new' | 'contacted' | 'converted' | 'rejected'; notes: string; created_at: string }

export const TST: Record<string, string> = { active: 'good', trial: 'info', past_due: 'warn', read_only: 'warn', suspended: 'bad' }
const TK: Record<string, string> = { open: 'warn', pending: 'info', closed: 'good' }
const PRIO: Record<string, string> = { high: 'var(--danger)', mid: 'var(--warning)', low: 'var(--muted)' }
export const invPill = (i: SubInvoice) => (i.status === 'paid' ? 'good' : i.status === 'void' ? 'mute' : i.overdue ? 'bad' : 'info')
export const invState = (i: SubInvoice) => (i.status === 'issued' && i.overdue ? 'overdue' : i.status)
const fmtDate = (v: string, lang: string) => new Date(v).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kuwait' })

export function PlatformHome() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['pdash'], queryFn: () => api<Dash>('/platform/dashboard') })
  const d = q.data
  const max = Math.max(1, ...(d?.history.map((h) => Number(h.invoiced)) ?? [1]))
  const pmax = Math.max(1, ...(d?.plans.map((p) => p.tenants) ?? [1]))
  return (
    <>
      <Head title={t('pc.home')} sub={t('pc.homeSub')} />
      <ErrorText error={q.error} />
      {d && <>
        <div className="grid stats">
          <Stat label={t('pc.activeShops')} value={<><bdi>{d.tenants.active}</bdi><div className="cap muted">{t('pc.branchesTotal', { n: d.branches })}</div></>} />
          <Stat label={t('pc.mrr')} value={<>{formatKWD(d.mrr, lang)}<div className="cap muted">ARR {formatKWD(d.arr, lang)}</div></>} />
          <Stat label={t('pc.inTrial')} value={<bdi>{d.tenants.trial}</bdi>} />
          <Stat label={t('pc.lateSuspended')} value={<><bdi>{d.tenants.past_due + d.tenants.suspended}</bdi><div className="cap muted">{t('pc.overdueAmount', { v: formatKWD(d.overdue.amount, lang) })}</div></>} />
        </div>
        {d.new_leads > 0 && <div className="notice info" style={{ marginTop: 14 }}><Icon name="bell" />{t('pc.newLeads', { n: d.new_leads })}
          <button className="btn sm" onClick={() => nav('/platform/leads')}>{t('pc.open')}</button></div>}
        <div className="grid g2" style={{ marginTop: 14 }}>
          <div className="card"><h2>{t('pc.invoicedByMonth')}</h2>
            <div className="days">{d.history.map((h) => <div key={h.month} title={`${formatKWD(h.invoiced, lang)} / ${formatKWD(h.collected, lang)}`}>
              <span style={{ height: `${(Number(h.invoiced) / max) * 85}%` }} />{h.month.slice(5)}</div>)}</div>
            {d.history.every((h) => h.invoiced === '0.000') && <div className="small muted">{t('pc.noInvoicesYet')}</div>}</div>
          <div className="card"><h2 style={{ marginBottom: 12 }}>{t('pc.planMix')}</h2>
            <div className="bars">{d.plans.map((p) => <div className="bar" key={p.code}><span>{lang === 'en' ? p.name_en : p.name_ar}</span>
              <span className="t"><i style={{ width: `${(p.tenants / pmax) * 100}%` }} /></span><span className="small"><bdi>{p.tenants}</bdi> {t('pc.shops')}</span></div>)}</div></div>
          <div className="card"><div className="row sb" style={{ marginBottom: 6 }}><h2>{t('pc.renewals')}</h2><button className="btn sm ghost" onClick={() => nav('/platform/billing')}>{t('pc.billing')}</button></div>
            <div className="list">{d.renewals.map((r) => <div className="li" key={r.tenant_id}><span className="av">{r.name[0]}</span>
              <div className="grow"><b className="small">{r.name}</b><div className="cap muted">{lang === 'en' ? r.plan_en : r.plan} · <bdi>{r.period_end}</bdi></div></div>
              <span className={`pill ${TST[r.status]}`}>{t(`platform.st.${r.status}`)}</span></div>)}</div></div>
          <div className="card"><div className="row sb" style={{ marginBottom: 6 }}><h2>{t('pc.openTickets')}</h2><button className="btn sm ghost" onClick={() => nav('/platform/support')}>{t('pc.support')}</button></div>
            <div className="list">{d.tickets.map((k) => <div className="li" key={k.id}><span className="prio" style={{ background: PRIO[k.priority] }} />
              <div className="grow"><b className="small">{k.subject}</b><div className="cap muted">{k.tenant} · <bdi>#{k.id}</bdi></div></div>
              <span className={`pill ${TK[k.status]}`}>{t(`pc.tk.${k.status}`)}</span></div>)}
              {d.tickets.length === 0 && <div className="small muted">{t('pc.noTickets')}</div>}</div></div>
        </div>
      </>}
    </>
  )
}

export function PlatformBilling() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const toast = useToast()
  const [f, setF] = useState('')
  const owners = useQuery({ queryKey: ['tenants'], queryFn: () => api<{ id: number; owner_phone: string }[]>('/platform/tenants') })
  const phoneOf = (id: number) => owners.data?.find((x) => x.id === id)?.owner_phone.replace(/\D/g, '') || ''
  const q = useQuery({ queryKey: ['pinv', f], queryFn: () => api<SubInvoice[]>(`/platform/invoices${f ? `?status=${f}` : ''}`) })
  const [act, setAct] = useState<{ inv: SubInvoice; action: 'pay' | 'void'; method: string; reference: string; reason: string } | null>(null)
  const run = useSave<{ issued: number; past_due: number }>([['pinv'], ['pdash'], ['tenants']], (r) => toast(t('pc.billingRan', { n: r.issued, p: r.past_due })))
  const s = useSave<SubInvoice>([['pinv'], ['pdash'], ['tenants']], () => { setAct(null); toast(t('common.saved')) })
  const rows = q.data ?? []
  const sum = (st: string) => rows.filter((i) => invState(i) === st).reduce((a, i) => a + Number(i.amount), 0).toFixed(3)
  return (
    <>
      <Head title={t('pc.billing')} sub={t('pc.billingSub')}>
        <button className="btn" disabled={run.busy} onClick={() => run.save({ path: '/platform/invoices' })}><Icon name="refresh" />{t('pc.runBilling')}</button>
      </Head>
      <div className="notice"><Icon name="info" />{t('pc.manualPayments')}</div>
      <ErrorText error={q.error || run.error} />
      {!f && <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('pc.inv.paid')} value={formatKWD(sum('paid'), lang)} />
        <Stat label={t('pc.inv.issued')} value={formatKWD(sum('issued'), lang)} />
        <Stat label={t('pc.inv.overdue')} value={formatKWD(sum('overdue'), lang)} />
      </div>}
      <div className="seg" style={{ marginBottom: 14 }}>{['', 'issued', 'overdue', 'paid', 'void'].map((x) => <button key={x} className={f === x ? 'on' : ''} onClick={() => setF(x)}>{x ? t(`pc.inv.${x}`) : t('pc.all')}</button>)}</div>
      <div className="tw"><table><thead><tr><th>{t('inv.number')}</th><th>{t('platform.company')}</th><th>{t('platform.plan')}</th><th>{t('pc.period')}</th><th className="n">{t('inv.amount')}</th><th>{t('pc.due')}</th><th>{t('org.status')}</th><th /></tr></thead>
        <tbody>{rows.map((i) => <tr key={i.id}>
          <td className="num">{i.number}</td><td>{i.tenant_name}</td><td>{lang === 'en' ? i.plan_name_en : i.plan_name_ar}</td>
          <td className="small"><bdi>{i.period_start}</bdi> → <bdi>{i.period_end}</bdi></td><td className="n money">{formatKWD(i.amount, lang)}</td>
          <td className="num">{i.due_on}</td>
          <td><span className={`pill ${invPill(i)}`}>{t(`pc.inv.${invState(i)}`)}</span>{i.paid_reference && <div className="cap muted">{t(`pc.m.${i.paid_method}`)} · {i.paid_reference}</div>}</td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>{i.status === 'issued' && <>
            <button className="btn sm" onClick={() => { s.reset(); setAct({ inv: i, action: 'pay', method: 'bank', reference: '', reason: '' }) }}>{t('pc.recordPayment')}</button>
            <button className="btn sm ghost danger" onClick={() => { s.reset(); setAct({ inv: i, action: 'void', method: 'bank', reference: '', reason: '' }) }}>{t('pc.void')}</button>
            {phoneOf(i.tenant) && <a className="btn sm ghost" style={{ color: '#25D366' }} target="_blank" rel="noreferrer"
              href={`https://wa.me/${phoneOf(i.tenant)}?text=${encodeURIComponent(t('pc.remindText', { name: i.tenant_name, n: i.number, v: formatKWD(i.amount, lang), d: i.due_on }))}`}><Icon name="whatsapp" />{t('pc.remind')}</a>}</>}</td></tr>)}
          {rows.length === 0 && <tr><td colSpan={8} className="empty">{t('pc.noInvoicesYet')}</td></tr>}</tbody></table></div>
      <Dialog open={!!act} title={act ? `${act.action === 'pay' ? t('pc.recordPayment') : t('pc.void')} · ${act.inv.number}` : ''} onClose={() => setAct(null)} busy={s.busy}
        onSubmit={() => s.save({ path: `/platform/invoices/${act!.inv.id}/action`, body: { action: act!.action, method: act!.method, reference: act!.reference, reason: act!.reason } })}>
        {act && <>
          <div className="small muted">{act.inv.tenant_name} · {formatKWD(act.inv.amount, lang)}</div>
          {act.action === 'pay' ? <div className="two">
            <label className="field">{t('pc.method')}<select className="input" value={act.method} onChange={(e) => setAct({ ...act, method: e.target.value })}>
              {['bank', 'knet', 'cash', 'other'].map((m) => <option key={m} value={m}>{t(`pc.m.${m}`)}</option>)}</select></label>
            <label className="field">{t('pos.transferRef')}<input className="input" dir="ltr" value={act.reference} onChange={(e) => setAct({ ...act, reference: e.target.value })} required /></label>
          </div> : <label className="field">{t('book.reason')}<input className="input" value={act.reason} onChange={(e) => setAct({ ...act, reason: e.target.value })} required /></label>}
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}

export function TicketThread({ ticket, replyPath, platform, onClose }: { ticket: Ticket | null; replyPath: string; platform: boolean; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const [body, setBody] = useState('')
  const [st, setSt] = useState('')
  const s = useSave<Ticket>([['ptickets'], ['mytickets'], ['pdash']], () => { setBody(''); setSt(''); toast(t('common.saved')); onClose() })
  return (
    <Dialog open={!!ticket} wide title={ticket ? `#${ticket.id} · ${ticket.subject}` : ''} onClose={onClose} busy={s.busy} submitLabel={t('pc.send')}
      onSubmit={() => s.save({ path: replyPath, body: { body, ...(st ? { status: st } : {}) } })}>
      {ticket && <>
        {platform && <div className="cap muted">{ticket.tenant_name}</div>}
        <div className="list">{ticket.messages.map((m) => <div key={m.id} className="card" style={{ boxShadow: 'none', background: m.from_platform ? 'var(--brand-soft)' : 'var(--surface-2)' }}>
          <div className="cap muted">{m.from_platform ? t('pc.platformTeam') : m.author_name} · <bdi>{fmtDate(m.created_at, i18n.language)}</bdi></div>
          <div className="small" style={{ whiteSpace: 'pre-wrap' }}>{m.body}</div></div>)}</div>
        <label className="field">{t('pc.reply')}<textarea className="input" rows={4} value={body} onChange={(e) => setBody(e.target.value)} /></label>
        <label className="field">{t('org.status')}<select className="input" value={st} onChange={(e) => setSt(e.target.value)}>
          <option value="">{t(platform ? 'pc.autoPending' : 'pc.autoOpen')}</option>
          {(platform ? ['open', 'pending', 'closed'] : ['closed']).map((x) => <option key={x} value={x}>{t(`pc.tk.${x}`)}</option>)}</select></label>
        {platform && <div className="cap muted">{t('pc.waNotice')}</div>}
        <ErrorText error={s.error} />
      </>}
    </Dialog>
  )
}

export function PlatformSupport() {
  const { t, i18n } = useTranslation()
  const [f, setF] = useState('open')
  const q = useQuery({ queryKey: ['ptickets', f], queryFn: () => api<Ticket[]>(`/platform/tickets${f ? `?status=${f}` : ''}`) })
  const [open, setOpen] = useState<Ticket | null>(null)
  return (
    <>
      <Head title={t('pc.support')} sub={t('pc.supportSub')} />
      <ErrorText error={q.error} />
      <div className="seg" style={{ marginBottom: 14 }}>{['open', 'pending', 'closed', ''].map((x) => <button key={x} className={f === x ? 'on' : ''} onClick={() => setF(x)}>{x ? t(`pc.tk.${x}`) : t('pc.all')}</button>)}</div>
      <div className="tw"><table><thead><tr><th>#</th><th>{t('pc.subject')}</th><th>{t('platform.company')}</th><th>{t('pc.priority')}</th><th>{t('pc.updated')}</th><th>{t('org.status')}</th></tr></thead>
        <tbody>{q.data?.map((k) => <tr key={k.id} className="click" onClick={() => setOpen(k)}>
          <td className="num">#{k.id}</td><td><b>{k.subject}</b></td><td>{k.tenant_name}</td>
          <td><span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}><span className="prio" style={{ background: PRIO[k.priority] }} />{t(`pc.pr.${k.priority}`)}</span></td>
          <td className="small">{fmtDate(k.updated_at, i18n.language)}</td><td><span className={`pill ${TK[k.status]}`}>{t(`pc.tk.${k.status}`)}</span></td></tr>)}
          {q.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('pc.noTickets')}</td></tr>}</tbody></table></div>
      <TicketThread ticket={open} platform replyPath={open ? `/platform/tickets/${open.id}/reply` : ''} onClose={() => setOpen(null)} />
    </>
  )
}

export function PlatformLeads() {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const q = useQuery({ queryKey: ['leads'], queryFn: () => api<Lead[]>('/platform/leads') })
  const [edit, setEdit] = useState<Lead | null>(null)
  const s = useSave<Lead>([['leads'], ['pdash']], () => { setEdit(null); toast(t('common.saved')) })
  return (
    <>
      <Head title={t('pc.leads')} sub={t('pc.leadsSub')} />
      <ErrorText error={q.error} />
      <div className="tw"><table><thead><tr><th>{t('pc.salon')}</th><th>{t('pc.contact')}</th><th>{t('org.type')}</th><th>{t('org.branches')}</th><th>{t('platform.plan')}</th><th>{t('pc.received')}</th><th>{t('org.status')}</th><th /></tr></thead>
        <tbody>{q.data?.map((l) => <tr key={l.id}>
          <td><b>{l.salon_name}</b>{l.city && <div className="cap muted">{l.city}</div>}</td>
          <td>{l.contact_name}<div className="cap muted" dir="ltr" style={{ textAlign: 'start' }}>+{l.phone}{l.email && ` · ${l.email}`}</div></td>
          <td><span className="pill info">{t(`biz.${l.business_type}`)}</span></td><td><bdi>{l.branches}</bdi></td><td>{l.plan_code || '—'}</td>
          <td className="small">{fmtDate(l.created_at, i18n.language)}</td>
          <td><span className={`pill ${l.status === 'new' ? 'warn' : l.status === 'converted' ? 'good' : l.status === 'rejected' ? 'mute' : 'info'}`}>{t(`pc.ls.${l.status}`)}</span></td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>
            <a className="btn sm" href={`https://wa.me/${l.phone}`} target="_blank" rel="noreferrer"><Icon name="whatsapp" /></a>
            <button className="btn sm" onClick={() => { s.reset(); setEdit({ ...l }) }}>{t('platform.manage')}</button></td></tr>)}
          {q.data?.length === 0 && <tr><td colSpan={8} className="empty">{t('pc.noLeads')}</td></tr>}</tbody></table></div>
      <Dialog open={!!edit} title={edit?.salon_name ?? ''} onClose={() => setEdit(null)} busy={s.busy}
        onSubmit={() => s.save({ path: `/platform/leads/${edit!.id}`, method: 'PATCH', body: { status: edit!.status, notes: edit!.notes } })}>
        {edit && <>
          {edit.message && <div className="notice">{edit.message}</div>}
          <label className="field">{t('org.status')}<select className="input" value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value as Lead['status'] })}>
            {['new', 'contacted', 'converted', 'rejected'].map((x) => <option key={x} value={x}>{t(`pc.ls.${x}`)}</option>)}</select></label>
          <label className="field">{t('cust.notes')}<textarea className="input" rows={3} value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></label>
          <div className="cap muted">{t('pc.convertHint')}</div>
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}

/** Read-only, time-limited view of a company for support; requires a written reason. */
export function SupportAccessDialog({ tenant, onClose }: { tenant: { id: number; name: string } | null; onClose: () => void }) {
  const { t } = useTranslation()
  const { chooseTenant } = useAuth()
  const [reason, setReason] = useState('')
  const s = useSave<unknown>([], () => { chooseTenant(tenant!.id); window.location.assign('/') })
  return (
    <Dialog open={!!tenant} title={tenant ? `${t('pc.viewAs')}: ${tenant.name}` : ''} onClose={onClose} busy={s.busy} submitLabel={t('pc.startSupport')}
      onSubmit={() => s.save({ path: `/platform/tenants/${tenant!.id}/support`, body: { reason } })}>
      <div className="notice"><Icon name="shield" />{t('pc.supportRules')}</div>
      <label className="field">{t('book.reason')}<textarea className="input" rows={3} minLength={10} value={reason} onChange={(e) => setReason(e.target.value)} required /></label>
      <ErrorText error={s.error} />
    </Dialog>
  )
}

type PSettings = { support_email: string; sales_whatsapp: string; headline_ar: string; headline_en: string; sub_ar: string; sub_en: string; trial_days: number }

/** Platform settings (reference v-p-set): what the public site shows and the trial length. */
export function PlatformSettingsPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const q = useQuery({ queryKey: ['psettings'], queryFn: () => api<PSettings>('/platform/settings') })
  const [f, setF] = useState<PSettings | null>(null)
  if (q.data && !f) setF(q.data)
  const s = useSave<PSettings>([['psettings'], ['site']], (r) => { setF(r); toast(t('common.saved')) })
  return (
    <>
      <Head title={t('pc.settings')} sub={t('pc.settingsSub')}><a className="btn" href="/" target="_blank" rel="noreferrer"><Icon name="eye" />{t('pc.preview')}</a></Head>
      {f && <div className="grid g2">
        <div className="card"><h2>{t('pc.identity')}</h2>
          <label className="field">{t('pc.supportEmail')}<input className="input" dir="ltr" type="email" value={f.support_email} onChange={(e) => setF({ ...f, support_email: e.target.value })} /></label>
          <label className="field">{t('pc.salesWa')}<input className="input" dir="ltr" inputMode="tel" placeholder="5xxxxxxx" value={f.sales_whatsapp} onChange={(e) => setF({ ...f, sales_whatsapp: e.target.value })} /></label>
          <label className="field">{t('pc.trialDays')}<input className="input" type="number" min={0} max={90} value={f.trial_days} onChange={(e) => setF({ ...f, trial_days: Number(e.target.value) })} /></label>
          <div className="cap muted">{t('pc.trialHelp')}</div></div>
        <div className="card"><h2>{t('pc.pricingPage')}</h2>
          <label className="field">{t('pc.headlineAr')}<input className="input" value={f.headline_ar} placeholder={t('site.headline')} onChange={(e) => setF({ ...f, headline_ar: e.target.value })} /></label>
          <label className="field">{t('pc.headlineEn')}<input className="input" dir="ltr" value={f.headline_en} onChange={(e) => setF({ ...f, headline_en: e.target.value })} /></label>
          <label className="field">{t('pc.subAr')}<textarea className="input" rows={2} value={f.sub_ar} placeholder={t('site.sub')} onChange={(e) => setF({ ...f, sub_ar: e.target.value })} /></label>
          <label className="field">{t('pc.subEn')}<textarea className="input" dir="ltr" rows={2} value={f.sub_en} onChange={(e) => setF({ ...f, sub_en: e.target.value })} /></label>
          <div className="cap muted">{t('pc.emptyDefault')}</div></div>
        <div className="card"><h2>{t('pc.gateways')}</h2>
          <div className="notice"><Icon name="info" />{t('pc.gatewaysNote')}</div>
          {['knet', 'myfatoorah', 'tap', 'applepay'].map((g) => <label className="chk" key={g}><span>{t(`pc.gw.${g}`)}<small>{t('pc.gwOff')}</small></span>
            <input type="checkbox" className="sw" checked={false} disabled readOnly /></label>)}</div>
      </div>}
      <ErrorText error={s.error} />
      {f && <button className="btn primary" style={{ marginTop: 14 }} disabled={s.busy} onClick={() => s.save({ path: '/platform/settings', method: 'PATCH', body: f })}>{t('common.save')}</button>}
    </>
  )
}
