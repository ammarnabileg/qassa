import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, useToast } from '../components/ui'
import { TicketThread, type Ticket } from './PlatformConsole'

/** The salon's support tickets with the platform team. */
export default function Support() {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const q = useQuery({ queryKey: ['mytickets'], queryFn: () => api<Ticket[]>('/support/tickets') })
  const [open, setOpen] = useState<Ticket | null>(null)
  const [form, setForm] = useState<{ subject: string; body: string; priority: string } | null>(null)
  const s = useSave<Ticket>([['mytickets']], () => { setForm(null); toast(t('pc.ticketSent')) })
  return (
    <>
      <Head title={t('nav.support')} sub={t('pc.mySupportSub')}>
        <button className="btn primary" onClick={() => { s.reset(); setForm({ subject: '', body: '', priority: 'mid' }) }}><Icon name="plus" />{t('pc.newTicket')}</button>
      </Head>
      <ErrorText error={q.error} />
      <div className="tw"><table><thead><tr><th>#</th><th>{t('pc.subject')}</th><th>{t('pc.updated')}</th><th>{t('org.status')}</th></tr></thead>
        <tbody>{q.data?.map((k) => <tr key={k.id} className="click" onClick={() => setOpen(k)}>
          <td className="num">#{k.id}</td><td><b>{k.subject}</b><div className="cap muted">{k.messages.length} {t('pc.messages')}</div></td>
          <td className="small">{new Date(k.updated_at).toLocaleString(i18n.language === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kuwait' })}</td>
          <td><span className={`pill ${k.status === 'pending' ? 'warn' : k.status === 'closed' ? 'good' : 'info'}`}>{t(`pc.my.${k.status}`)}</span></td></tr>)}
          {q.data?.length === 0 && <tr><td colSpan={4} className="empty">{t('pc.noTickets')}</td></tr>}</tbody></table></div>
      <TicketThread ticket={open} platform={false} replyPath={open ? `/support/tickets/${open.id}/reply` : ''} onClose={() => setOpen(null)} />
      <Dialog open={!!form} title={t('pc.newTicket')} onClose={() => setForm(null)} busy={s.busy} onSubmit={() => s.save({ path: '/support/tickets', body: form })}>
        {form && <>
          <label className="field">{t('pc.subject')}<input className="input" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} required /></label>
          <label className="field">{t('pc.details')}<textarea className="input" rows={5} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} required /></label>
          <label className="field">{t('pc.priority')}<select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {['low', 'mid', 'high'].map((x) => <option key={x} value={x}>{t(`pc.pr.${x}`)}</option>)}</select></label>
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}
