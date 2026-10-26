import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, Stat } from '../components/ui'

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
