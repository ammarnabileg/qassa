import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, openFile } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { ACC_PILL, KYC_PILL, type KycItem } from './OnlinePayments'

type Row = { tenant_id: number; tenant: string; slug: string; status: string; environment: string; docs: number; accepted: number; rejected: number; has_credentials: boolean; commission_percent: string; commission_fixed: string; submitted_at: string | null }
type Detail = { tenant_id: number; status: string; review_note: string; environment: string; client_id: string; has_secret: boolean; merchant_token: string; commission_percent: string; commission_fixed: string; webhook_url: string; has_webhook_secret: boolean; webhook_secret?: string; checklist: KycItem[] }
type Report = { month: string; rows: { tenant_id: number; tenant: string; paid_count: number; paid_amount: string; failed_count: number; failed_amount: string; pending_count: number; review_count: number; commission_percent: string; commission_fixed: string; commission: string }[]; totals: { paid: string; commission: string; paid_n: number; failed_n: number } }
const STATUSES = ['collecting', 'under_review', 'needs_changes', 'active', 'suspended']

/** Platform: open each salon's KlickPay account as their agent (review documents, enter credentials, set commission),
 *  and see per salon how many online payments succeeded or failed and the commission due. */
export default function PlatformPayments() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const [tab, setTab] = useState<'accounts' | 'report'>('accounts')
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const accounts = useQuery({ queryKey: ['pp-accounts'], queryFn: () => api<{ accounts: Row[]; required_types: number }>('/platform/payments/accounts') })
  const report = useQuery({ queryKey: ['pp-report', month], queryFn: () => api<Report>(`/platform/payments/report?month=${month}`), enabled: tab === 'report' })
  const [open, setOpen] = useState<number | null>(null)
  return (
    <>
      <Head title={t('nav.onlinePay')} sub={t('pp.sub')} />
      <div className="tabs"><button className={tab === 'accounts' ? 'on' : ''} onClick={() => setTab('accounts')}>{t('pp.accounts')}</button>
        <button className={tab === 'report' ? 'on' : ''} onClick={() => setTab('report')}>{t('pp.report')}</button></div>
      {tab === 'accounts' && <div className="tw"><table><thead><tr><th>{t('platform.company')}</th><th>{t('org.status')}</th><th>{t('pp.docs')}</th><th>{t('pp.commission')}</th><th>{t('pp.env')}</th><th /></tr></thead>
        <tbody>{accounts.data?.accounts.map((r) => <tr key={r.tenant_id}>
          <td><b>{r.tenant}</b><div className="cap muted">{r.slug}</div></td>
          <td><span className={`pill ${ACC_PILL[r.status]}`}>{t(`pay.acc.${r.status}`)}</span></td>
          <td className="small"><bdi>{r.docs}</bdi> / <bdi>{accounts.data.required_types}</bdi>{r.accepted > 0 && <> · <span className="pill good">{r.accepted}</span></>}{r.rejected > 0 && <> <span className="pill bad">{r.rejected}</span></>}</td>
          <td className="small"><bdi>{Number(r.commission_percent)}%</bdi>{Number(r.commission_fixed) > 0 && <> + {formatKWD(r.commission_fixed, lang)}</>}</td>
          <td className="small">{t(`pp.e.${r.environment}`)}</td>
          <td><button className="btn sm" onClick={() => setOpen(r.tenant_id)}>{t('platform.manage')}</button></td></tr>)}</tbody></table></div>}
      {tab === 'report' && <>
        <label className="field" style={{ maxWidth: 220 }}>{t('pp.month')}<input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
        {report.data && <>
          <div className="grid stats">
            <Stat label={t('pp.paid')} value={formatKWD(report.data.totals.paid, lang)} sub={t('pp.count', { n: report.data.totals.paid_n })} />
            <Stat label={t('pp.failed')} value={<bdi>{report.data.totals.failed_n}</bdi>} />
            <Stat label={t('pp.commissionDue')} value={formatKWD(report.data.totals.commission, lang)} />
          </div>
          <div className="tw" style={{ marginTop: 14 }}><table><thead><tr><th>{t('platform.company')}</th><th className="n">{t('pp.paidN')}</th><th className="n">{t('pp.paid')}</th><th className="n">{t('pp.failedN')}</th><th className="n">{t('pp.failedAmt')}</th><th className="n">{t('pp.pending')}</th><th>{t('pp.commission')}</th><th className="n">{t('pp.commissionDue')}</th></tr></thead>
            <tbody>{report.data.rows.map((r) => <tr key={r.tenant_id}><td><b>{r.tenant}</b>{r.review_count > 0 && <div className="cap" style={{ color: 'var(--danger, #c0392b)' }}>{t('pp.reviewN', { n: r.review_count })}</div>}</td>
              <td className="n"><bdi>{r.paid_count}</bdi></td><td className="n money">{formatKWD(r.paid_amount, lang)}</td>
              <td className="n"><bdi>{r.failed_count}</bdi></td><td className="n money">{formatKWD(r.failed_amount, lang)}</td><td className="n"><bdi>{r.pending_count}</bdi></td>
              <td className="small"><bdi>{Number(r.commission_percent)}%</bdi>{Number(r.commission_fixed) > 0 && <> + {formatKWD(r.commission_fixed, lang)}</>}</td>
              <td className="n money"><b>{formatKWD(r.commission, lang)}</b></td></tr>)}
              {report.data.rows.length === 0 && <tr><td colSpan={8} className="empty">{t('pp.noPayments')}</td></tr>}</tbody></table></div>
          <div className="cap muted" style={{ marginTop: 8 }}>{t('pp.reportNote')}</div>
        </>}
      </>}
      {open !== null && <AccountDialog tenantId={open} onClose={() => setOpen(null)} />}
    </>
  )
}

function AccountDialog({ tenantId, onClose }: { tenantId: number; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const toast = useToast()
  const q = useQuery({ queryKey: ['pp-account', tenantId], queryFn: () => api<Detail>(`/platform/payments/accounts/${tenantId}`) })
  const [f, setF] = useState<{ status?: string; review_note?: string; environment?: string; client_id?: string; client_secret?: string; merchant_token?: string; commission_percent?: string; commission_fixed?: string }>({})
  const [secret, setSecret] = useState<{ url: string; secret: string } | null>(null)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const save = useSave<Detail>([['pp-account', tenantId], ['pp-accounts']], (r) => { toast(t('common.saved')); setF({}); if (r.webhook_secret) setSecret({ url: r.webhook_url, secret: r.webhook_secret }) })
  const review = useSave<unknown>([['pp-account', tenantId], ['pp-accounts']], () => toast(t('common.saved')))
  const [fileErr, setFileErr] = useState<unknown>(null)
  const d = q.data
  const v = <K extends keyof typeof f>(k: K, fallback: string) => f[k] ?? fallback
  return (
    <Dialog open wide title={t('pp.manage')} onClose={onClose} busy={save.busy}
      onSubmit={() => save.save({ path: `/platform/payments/accounts/${tenantId}`, method: 'PATCH', body: f })}>
      {d && <>
        <h3>{t('pp.docs')}</h3>
        <div className="list">{d.checklist.map(({ type, doc }) => <div className="li" key={type.id} style={{ alignItems: 'flex-start' }}>
          <div className="grow"><b className="small">{lang === 'en' ? type.name_en : type.name_ar}</b>{!type.required && <span className="cap muted"> · {t('pay.optional')}</span>}
            {doc ? <div className="cap"><span className={`pill ${KYC_PILL[doc.status]}`}>{t(`pay.doc.${doc.status}`)}</span> {doc.name}{doc.note && ` · ${doc.note}`}</div>
              : <div className="cap muted">{t('pp.notUploaded')}</div>}</div>
          {doc && <div className="row" style={{ gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <button type="button" className="btn sm ghost" onClick={() => openFile(`/platform/payments/kyc/${doc.id}/file`).catch(setFileErr)}><Icon name="eye" /></button>
            <button type="button" className="btn sm" disabled={review.busy} onClick={() => review.save({ path: `/platform/payments/kyc/${doc.id}/review`, body: { accept: true } })}><Icon name="check" />{t('pp.accept')}</button>
            <input className="input" style={{ width: 180, padding: '4px 8px' }} placeholder={t('pp.rejectNote')} value={notes[doc.id] ?? ''} onChange={(e) => setNotes({ ...notes, [doc.id]: e.target.value })} />
            <button type="button" className="btn sm danger" disabled={review.busy || !(notes[doc.id] ?? '').trim()} onClick={() => review.save({ path: `/platform/payments/kyc/${doc.id}/review`, body: { accept: false, note: notes[doc.id] } })}>{t('pp.reject')}</button>
          </div>}
        </div>)}</div>
        <ErrorText error={review.error ?? fileErr} />
        <h3 style={{ marginTop: 12 }}>{t('pp.account')}</h3>
        <div className="two">
          <label className="field">{t('org.status')}<select className="input" value={v('status', d.status)} onChange={(e) => setF({ ...f, status: e.target.value })}>
            {[...new Set([d.status, ...STATUSES])].map((s) => <option key={s} value={s}>{t(`pay.acc.${s}`)}</option>)}</select></label>
          <label className="field">{t('pp.env')}<select className="input" value={v('environment', d.environment)} onChange={(e) => setF({ ...f, environment: e.target.value })}>
            {['staging', 'production'].map((s) => <option key={s} value={s}>{t(`pp.e.${s}`)}</option>)}</select></label>
        </div>
        <label className="field">{t('pp.noteToSalon')}<input className="input" value={v('review_note', d.review_note)} onChange={(e) => setF({ ...f, review_note: e.target.value })} /></label>
        <div className="two">
          <label className="field">client-id<input className="input" dir="ltr" value={v('client_id', d.client_id)} onChange={(e) => setF({ ...f, client_id: e.target.value })} /></label>
          <label className="field">client-secret<input className="input" dir="ltr" type="password" autoComplete="off" placeholder={d.has_secret ? '••••••••' : ''} value={f.client_secret ?? ''} onChange={(e) => setF({ ...f, client_secret: e.target.value })} />
            <small className="muted">{t('pp.secretHelp')}</small></label>
        </div>
        <label className="field">merchant_token<input className="input" dir="ltr" value={v('merchant_token', d.merchant_token)} onChange={(e) => setF({ ...f, merchant_token: e.target.value })} /></label>
        <div className="two">
          <label className="field">{t('pp.percent')}<input className="input" dir="ltr" inputMode="decimal" value={v('commission_percent', d.commission_percent)} onChange={(e) => setF({ ...f, commission_percent: e.target.value })} /></label>
          <label className="field">{t('pp.fixed')}<input className="input" dir="ltr" inputMode="decimal" value={v('commission_fixed', d.commission_fixed)} onChange={(e) => setF({ ...f, commission_fixed: e.target.value })} /></label>
        </div>
        <h3 style={{ marginTop: 12 }}>Webhook</h3>
        <div className="small muted">{t('pp.webhookHelp')}</div>
        {d.webhook_url && <input className="input" dir="ltr" readOnly value={d.webhook_url} onFocus={(e) => e.target.select()} />}
        <button type="button" className="btn sm" disabled={save.busy} onClick={() => save.save({ path: `/platform/payments/accounts/${tenantId}`, method: 'PATCH', body: { new_webhook_secret: true } })}>
          <Icon name="key" />{d.has_webhook_secret ? t('pp.rotate') : t('pp.makeSecret')}</button>
        {secret && <div className="notice" style={{ display: 'block' }}><div className="small">{t('pp.secretOnce')}</div>
          <input className="input" dir="ltr" readOnly value={secret.secret} onFocus={(e) => e.target.select()} /></div>}
        <ErrorText error={save.error} />
      </>}
    </Dialog>
  )
}
