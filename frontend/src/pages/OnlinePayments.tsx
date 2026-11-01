import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, openFile, upload } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, useToast } from '../components/ui'
import { formatKWD } from '../money'

export type KycItem = { type: { id: number; code: string; stage: 'kyc' | 'contract'; name_ar: string; name_en: string; help_ar: string; help_en: string; required: boolean }
  doc: { id: number; status: 'uploaded' | 'accepted' | 'rejected'; note: string; name: string; uploaded_at: string } | null }
type Deposit = { mode: 'off' | 'fixed' | 'percent'; value: string; refund_hours: number; hold_minutes: number }
type Account = { status: string; review_note: string; active: boolean; checklist: KycItem[]; deposit: Deposit; contract: { name: string; sent_at: string } | null }
export type OnlinePay = { id: number; reference: string; purpose: 'invoice' | 'deposit'; invoice: string; invoice_id: number | null; appointment_id: number | null; refundable: string; refunds: { id: number; amount: string; status: string; detail: string }[]; amount: string; status: string; method: string; detail: string; created_at: string; customer: string }

export const KYC_PILL: Record<string, string> = { uploaded: 'info', accepted: 'good', rejected: 'bad' }
export const ACC_PILL: Record<string, string> = { not_started: 'mute', collecting: 'info', under_review: 'warn', needs_changes: 'bad', active: 'good', suspended: 'mute' }
export const REF_PILL: Record<string, string> = { requested: 'info', success: 'good', pending: 'warn', failed: 'bad' }
export const PAY_PILL: Record<string, string> = { created: 'info', paid: 'good', declined: 'bad', failed: 'bad', voided: 'mute', review: 'warn' }

/** Online payments (KlickPay, D-017): open the merchant account through us (documents), then see every payment link. */
export default function OnlinePayments() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const acc = useQuery({ queryKey: ['pay-account'], queryFn: () => api<Account>('/payments/account'), enabled: can('org.manage') })
  const list = useQuery({ queryKey: ['online-payments'], queryFn: () => api<OnlinePay[]>('/payments/online') })
  const submit = useSave<{ status: string }>([['pay-account']], () => toast(t('pay.submitted')))
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const pick = useRef<number>(0)
  const send = async (f: File) => {
    setBusy(pick.current); setErr(null)
    const body = new FormData(); body.append('doc_type', String(pick.current)); body.append('file', f)
    try { await upload('/payments/kyc', body); qc.invalidateQueries({ queryKey: ['pay-account'] }); toast(t('pay.uploaded')) } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const view = (id: number) => openFile(`/payments/kyc/${id}/file`).catch(setErr)
  const a = acc.data
  const locked = a && ['under_review', 'active', 'contract'].includes(a.status)
  const canUpload = (stage: string) => !!a && (stage === 'contract' ? a.status === 'contract' : !locked)
  return (
    <>
      <Head title={t('nav.onlinePay')} sub={t('pay.sub')} />
      {a && !a.active && <div className="card" style={{ marginBottom: 14 }}>
        <div className="row sb"><h2>{t('pay.openTitle')}</h2><span className={`pill ${ACC_PILL[a.status]}`}>{t(`pay.acc.${a.status}`)}</span></div>
        <div className="small muted" style={{ margin: '6px 0 10px' }}>{t('pay.openHelp')}</div>
        {a.review_note && <div className="notice"><Icon name="alert" />{a.review_note}</div>}
        {a.contract && <div className="notice" style={{ display: 'block' }}><b className="small">{t('pay.contractTitle')}</b>
          <div className="small">{t('pay.contractHelp')}</div>
          <button className="btn sm" style={{ marginTop: 6 }} onClick={() => openFile('/payments/contract').catch(setErr)}><Icon name="download" />{t('pay.contractDownload')}</button></div>}
        <input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) send(f) }} />
        <div className="list">{a.checklist.map(({ type, doc }) => <div className="li" key={type.id} style={{ alignItems: 'flex-start' }}>
          <div className="grow">
            <b className="small">{lang === 'en' ? type.name_en : type.name_ar}</b>{!type.required && <span className="cap muted"> · {t('pay.optional')}</span>}
            {(lang === 'en' ? type.help_en : type.help_ar) && <div className="cap muted">{lang === 'en' ? type.help_en : type.help_ar}</div>}
            {doc && <div className="cap"><span className={`pill ${KYC_PILL[doc.status]}`}>{t(`pay.doc.${doc.status}`)}</span> {doc.name}</div>}
            {doc?.status === 'rejected' && doc.note && <div className="small" style={{ color: 'var(--danger, #c0392b)' }}>{doc.note}</div>}
          </div>
          <div className="row" style={{ gap: 6 }}>
            {doc && <button className="btn sm ghost" onClick={() => view(doc.id)}><Icon name="eye" /></button>}
            {canUpload(type.stage) && <button className="btn sm" disabled={busy !== null} onClick={() => { pick.current = type.id; input.current?.click() }}>
              <Icon name="file" />{busy === type.id ? '…' : doc ? t('pay.replace') : t('pay.upload')}</button>}
          </div>
        </div>)}</div>
        <ErrorText error={err ?? submit.error} />
        {!locked && <button className="btn primary" style={{ marginTop: 10 }} disabled={submit.busy} onClick={() => submit.save({ path: '/payments/kyc/submit' })}>{t('pay.submit')}</button>}
      </div>}
      {a?.active && <div className="notice good" style={{ marginBottom: 14 }}><Icon name="check" />{t('pay.activeHelp')}</div>}
      {a?.active && <DepositCard value={a.deposit} />}
      <h2 style={{ margin: '6px 0 10px' }}>{t('pay.links')}</h2>
      <div className="tw"><table><thead><tr><th>{t('fb.invoice')}</th><th>{t('cust.name')}</th><th className="n">{t('pos.total')}</th><th>{t('org.status')}</th><th>{t('pay.method')}</th><th>{t('pay.created')}</th></tr></thead>
        <tbody>{list.data?.map((o) => <tr key={o.id}><td>{o.purpose === 'deposit' ? <span className="pill info">{t('pay.deposit')}</span> : <bdi>{o.invoice}</bdi>}</td><td>{o.customer}</td><td className="n money">{formatKWD(o.amount, lang)}</td>
          <td><span className={`pill ${PAY_PILL[o.status]}`}>{t(`pay.st.${o.status}`)}</span>{o.status === 'review' && <div className="cap muted">{o.detail}</div>}
            {o.refunds.map((r) => <div key={r.id} className="cap">{t('pay.refund')} {formatKWD(r.amount, lang)} · <span className={`pill ${REF_PILL[r.status]}`}>{t(`pay.rs.${r.status}`)}</span>{r.detail && ` · ${r.detail}`}</div>)}</td>
          <td className="small">{o.method || '—'}</td><td className="small"><bdi>{new Date(o.created_at).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })}</bdi></td></tr>)}
          {list.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('pay.none')}</td></tr>}</tbody></table></div>
    </>
  )
}

/** Booking deposit policy for the customer app. */
function DepositCard({ value }: { value: Deposit }) {
  const { t } = useTranslation()
  const toast = useToast()
  const [f, setF] = useState<Deposit>(value)
  const save = useSave<unknown>([['pay-account']], () => toast(t('common.saved')))
  return <div className="card" style={{ marginBottom: 14, maxWidth: 640 }}>
    <h2>{t('pay.depositTitle')}</h2>
    <div className="small muted" style={{ margin: '4px 0 10px' }}>{t('pay.depositHelp')}</div>
    <div className="two">
      <label className="field">{t('pay.depositMode')}<select className="input" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value as Deposit['mode'] })}>
        {(['off', 'fixed', 'percent'] as const).map((m) => <option key={m} value={m}>{t(`pay.dm.${m}`)}</option>)}</select></label>
      {f.mode !== 'off' && <label className="field">{f.mode === 'fixed' ? t('pay.depositKwd') : t('pay.depositPct')}<input className="input" dir="ltr" inputMode="decimal" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></label>}
    </div>
    {f.mode !== 'off' && <div className="two">
      <label className="field">{t('pay.refundHours')}<input className="input" type="number" min={0} max={168} value={f.refund_hours} onChange={(e) => setF({ ...f, refund_hours: Number(e.target.value) })} />
        <small className="muted">{t('pay.refundHoursHelp', { n: f.refund_hours })}</small></label>
      <label className="field">{t('pay.holdMinutes')}<input className="input" type="number" min={5} max={120} value={f.hold_minutes} onChange={(e) => setF({ ...f, hold_minutes: Number(e.target.value) })} />
        <small className="muted">{t('pay.holdHelp', { n: f.hold_minutes })}</small></label>
    </div>}
    <ErrorText error={save.error} />
    <button className="btn primary" disabled={save.busy} onClick={() => save.save({ path: '/payments/account', method: 'PATCH',
      body: { deposit_mode: f.mode, deposit_value: f.value || '0', deposit_refund_hours: f.refund_hours, deposit_hold_minutes: f.hold_minutes } })}>{t('common.save')}</button>
  </div>
}
