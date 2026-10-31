import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, Stat, useToast } from '../components/ui'

type Msg = { id: number; to: string; kind: string; preview: string; status: 'sent' | 'failed'; error: string; created_at: string }
type St = { gateway: string; state: 'new' | 'connecting' | 'open' | 'close'; phone: string; checked_at: string | null; connected_at: string | null; messages: Msg[]; qr?: string | null }

const PILL = { open: 'good', connecting: 'warn', close: 'bad', new: 'mute' } as const
const dt = (iso: string, lang: string) => new Date(iso).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })

/** The company's own WhatsApp number (D-002): connect by scanning a QR from the salon's phone. */
export default function WhatsApp() {
  const { t, i18n } = useTranslation()
  const [qr, setQr] = useState<string | null>(null)
  const st = useQuery({ queryKey: ['whatsapp'], queryFn: () => api<St>('/whatsapp'),
    refetchInterval: (q) => (q.state.data?.state === 'connecting' || qr ? 3000 : false) })
  const connect = useSave<St>([['whatsapp']], (r) => setQr(r.qr ?? null))
  const disconnect = useSave<St>([['whatsapp']], () => setQr(null))
  const s = st.data
  const showQr = qr && s?.state !== 'open'
  return (
    <>
      <Head title={t('nav.whatsapp')} sub={t('wa.sub')}>
        {s && s.state !== 'open' && <button className="btn primary" disabled={connect.busy} onClick={() => connect.save({ path: '/whatsapp/connect' })}><Icon name="whatsapp" />{t('wa.connect')}</button>}
        {s?.state === 'open' && <button className="btn danger" disabled={disconnect.busy} onClick={() => disconnect.save({ path: '/whatsapp/disconnect' })}>{t('wa.disconnect')}</button>}
      </Head>
      <ErrorText error={st.error || connect.error || disconnect.error} />
      {s && s.gateway !== 'evolution' && <div className="notice"><Icon name="alert" />{t('wa.noGateway')}</div>}
      {s && <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('wa.state')} value={<span className={`pill ${PILL[s.state]}`}>{t(`wa.st.${s.state}`)}</span>} />
        <Stat label={t('wa.number')} value={s.phone ? <bdi className="num" dir="ltr">+{s.phone}</bdi> : '—'} />
        <Stat label={t('wa.sent')} value={<bdi>{s.messages.filter((m) => m.status === 'sent').length}</bdi>} />
        <Stat label={t('wa.failed')} value={<bdi>{s.messages.filter((m) => m.status === 'failed').length}</bdi>} />
      </div>}
      {showQr && <div className="card" style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
        <img src={qr!} alt="QR" width={240} height={240} style={{ borderRadius: 12, border: '1px solid var(--line)' }} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <h2>{t('wa.scanTitle')}</h2>
          <ol className="small" style={{ lineHeight: 2 }}><li>{t('wa.step1')}</li><li>{t('wa.step2')}</li><li>{t('wa.step3')}</li></ol>
          <div className="small muted">{t('wa.qrExpires')}</div>
        </div>
      </div>}
      <div className="notice info"><Icon name="info" />{t('wa.risk')}</div>
      <AutoMessages />
      <h2 style={{ margin: '18px 0 10px' }}>{t('wa.log')}</h2>
      <div className="tw"><table><thead><tr><th>{t('inv.time')}</th><th>{t('wa.to')}</th><th>{t('wa.kind')}</th><th>{t('org.status')}</th><th>{t('wa.detail')}</th></tr></thead>
        <tbody>{s?.messages.map((m) => <tr key={m.id}><td className="num">{dt(m.created_at, i18n.language)}</td><td className="num" dir="ltr" style={{ textAlign: 'start' }}>+{m.to}</td>
          <td>{t(`wa.k.${m.kind}`, { defaultValue: m.kind })}</td>
          <td><span className={`pill ${m.status === 'sent' ? 'good' : 'bad'}`}>{t(`wa.ms.${m.status}`)}</span></td>
          <td className="small muted">{m.error || m.preview}</td></tr>)}
          {s?.messages.length === 0 && <tr><td colSpan={5} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>
    </>
  )
}

type Auto = { booking_confirmation: boolean; reminder: boolean; reminder_hours: number; receipt: boolean; feedback: boolean; google_review_url: string; winback: boolean; winback_days: number; winback_coupon: string }

/** Automatic service messages from the salon's own number (D-012). */
function AutoMessages() {
  const { t } = useTranslation()
  const toast = useToast()
  const q = useQuery({ queryKey: ['wa-auto'], queryFn: () => api<Auto>('/whatsapp/auto-settings') })
  const s = useSave<Auto>([['wa-auto']], () => toast(t('common.saved')))
  const set = (patch: Partial<Auto>) => s.save({ path: '/whatsapp/auto-settings', method: 'PATCH', body: patch })
  const d = q.data
  if (!d) return null
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>{t('wa.auto.title')}</h2><div className="small muted">{t('wa.auto.sub')}</div>
      <label className="chk"><span>{t('wa.auto.confirm')}<small>{t('wa.auto.confirmHelp')}</small></span><input type="checkbox" className="sw" checked={d.booking_confirmation} disabled={s.busy} onChange={(e) => set({ booking_confirmation: e.target.checked })} /></label>
      <label className="chk"><span>{t('wa.auto.reminder')}<small>{t('wa.auto.reminderHelp', { n: d.reminder_hours })}</small></span><input type="checkbox" className="sw" checked={d.reminder} disabled={s.busy} onChange={(e) => set({ reminder: e.target.checked })} /></label>
      {d.reminder && <label className="field" style={{ maxWidth: 220 }}>{t('wa.auto.hours')}<select className="input" value={d.reminder_hours} onChange={(e) => set({ reminder_hours: Number(e.target.value) })}>
        {[1, 2, 3, 6, 12, 24].map((h) => <option key={h} value={h}>{t('wa.auto.hoursN', { n: h })}</option>)}</select></label>}
      <label className="chk"><span>{t('wa.auto.receipt')}<small>{t('wa.auto.receiptHelp')}</small></span><input type="checkbox" className="sw" checked={d.receipt} disabled={s.busy} onChange={(e) => set({ receipt: e.target.checked })} /></label>
      <label className="chk"><span>{t('wa.auto.feedback')}<small>{t('wa.auto.feedbackHelp')}</small></span><input type="checkbox" className="sw" checked={d.feedback} disabled={s.busy} onChange={(e) => set({ feedback: e.target.checked })} /></label>
      {d.feedback && <label className="field">{t('wa.auto.reviewUrl')}<input className="input" dir="ltr" type="url" placeholder="https://g.page/r/…/review" defaultValue={d.google_review_url}
        onBlur={(e) => e.target.value !== d.google_review_url && set({ google_review_url: e.target.value.trim() })} /><small className="muted">{t('wa.auto.reviewUrlHelp')}</small></label>}
      <h3 style={{ margin: '14px 0 4px' }}>{t('wa.auto.marketing')}</h3>
      <label className="chk"><span>{t('wa.auto.winback')}<small>{t('wa.auto.winbackHelp', { n: d.winback_days })}</small></span><input type="checkbox" className="sw" checked={d.winback} disabled={s.busy} onChange={(e) => set({ winback: e.target.checked })} /></label>
      {d.winback && <div className="two">
        <label className="field">{t('wa.auto.winbackDays')}<select className="input" value={d.winback_days} onChange={(e) => set({ winback_days: Number(e.target.value) })}>
          {[21, 30, 45, 60, 90].map((n) => <option key={n} value={n}>{t('wa.auto.daysN', { n })}</option>)}</select></label>
        <label className="field">{t('wa.auto.winbackCoupon')}<input className="input" dir="ltr" placeholder="BACK10" defaultValue={d.winback_coupon}
          onBlur={(e) => e.target.value.trim().toUpperCase() !== d.winback_coupon && set({ winback_coupon: e.target.value.trim() })} /></label>
      </div>}
      <ErrorText error={s.error} />
    </div>
  )
}
