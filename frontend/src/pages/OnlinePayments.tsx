import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, openFile, upload } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, useToast } from '../components/ui'
import { formatKWD } from '../money'

export type KycItem = { type: { id: number; code: string; name_ar: string; name_en: string; help_ar: string; help_en: string; required: boolean }
  doc: { id: number; status: 'uploaded' | 'accepted' | 'rejected'; note: string; name: string; uploaded_at: string } | null }
type Account = { status: string; review_note: string; active: boolean; checklist: KycItem[] }
export type OnlinePay = { id: number; reference: string; invoice: string; invoice_id: number; amount: string; status: string; method: string; detail: string; created_at: string; customer: string }

export const KYC_PILL: Record<string, string> = { uploaded: 'info', accepted: 'good', rejected: 'bad' }
export const ACC_PILL: Record<string, string> = { not_started: 'mute', collecting: 'info', under_review: 'warn', needs_changes: 'bad', active: 'good', suspended: 'mute' }
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
  const locked = a && ['under_review', 'active'].includes(a.status)
  return (
    <>
      <Head title={t('nav.onlinePay')} sub={t('pay.sub')} />
      {a && !a.active && <div className="card" style={{ marginBottom: 14 }}>
        <div className="row sb"><h2>{t('pay.openTitle')}</h2><span className={`pill ${ACC_PILL[a.status]}`}>{t(`pay.acc.${a.status}`)}</span></div>
        <div className="small muted" style={{ margin: '6px 0 10px' }}>{t('pay.openHelp')}</div>
        {a.review_note && <div className="notice"><Icon name="alert" />{a.review_note}</div>}
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
            {!locked && <button className="btn sm" disabled={busy !== null} onClick={() => { pick.current = type.id; input.current?.click() }}>
              <Icon name="file" />{busy === type.id ? '…' : doc ? t('pay.replace') : t('pay.upload')}</button>}
          </div>
        </div>)}</div>
        <ErrorText error={err ?? submit.error} />
        {!locked && <button className="btn primary" style={{ marginTop: 10 }} disabled={submit.busy} onClick={() => submit.save({ path: '/payments/kyc/submit' })}>{t('pay.submit')}</button>}
      </div>}
      {a?.active && <div className="notice good" style={{ marginBottom: 14 }}><Icon name="check" />{t('pay.activeHelp')}</div>}
      <h2 style={{ margin: '6px 0 10px' }}>{t('pay.links')}</h2>
      <div className="tw"><table><thead><tr><th>{t('fb.invoice')}</th><th>{t('cust.name')}</th><th className="n">{t('pos.total')}</th><th>{t('org.status')}</th><th>{t('pay.method')}</th><th>{t('pay.created')}</th></tr></thead>
        <tbody>{list.data?.map((o) => <tr key={o.id}><td><bdi>{o.invoice}</bdi></td><td>{o.customer}</td><td className="n money">{formatKWD(o.amount, lang)}</td>
          <td><span className={`pill ${PAY_PILL[o.status]}`}>{t(`pay.st.${o.status}`)}</span>{o.status === 'review' && <div className="cap muted">{o.detail}</div>}</td>
          <td className="small">{o.method || '—'}</td><td className="small"><bdi>{new Date(o.created_at).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })}</bdi></td></tr>)}
          {list.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('pay.none')}</td></tr>}</tbody></table></div>
    </>
  )
}
