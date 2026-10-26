import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type CashSession } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'

const dt = (iso: string | null, lang: string) => iso ? new Date(iso).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' }) : '—'

export default function Cash() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const { branch } = useBranch()
  const toast = useToast()
  const list = useQuery({ queryKey: ['session', branch?.id, 'all'], enabled: !!branch, queryFn: () => api<CashSession[]>(`/pos/sessions?branch_id=${branch!.id}`) })
  const [opening, setOpening] = useState<string | null>(null)
  const [closing, setClosing] = useState<{ counted: string; notes: string } | null>(null)
  const ok = () => { toast(t('common.saved')); setOpening(null); setClosing(null) }
  const openS = useSave<CashSession>([['session']], ok)
  const closeS = useSave<CashSession>([['session']], ok)
  const approve = useSave<CashSession>([['session']], ok)
  const open = list.data?.find((s) => s.status === 'open')
  const vPill = (s: CashSession) => s.variance_status === 'pending' ? <span className="pill warn">{t('cash.pending')}</span>
    : s.variance_status === 'approved' ? <span className="pill info">{t('cash.approved')}</span> : s.status === 'closed' ? <span className="pill good">{t('cash.balanced')}</span> : <span className="pill good">{t('cash.open')}</span>
  return (
    <>
      <Head title={t('nav.cash')} sub={t('cash.sub')}>
        {!open && <button className="btn primary" onClick={() => { openS.reset(); setOpening('') }}><Icon name="key" />{t('cash.openBtn')}</button>}
        {open && <button className="btn primary" onClick={() => { closeS.reset(); setClosing({ counted: '', notes: '' }) }}><Icon name="shield" />{t('cash.closeBtn')}</button>}
      </Head>
      <ErrorText error={list.error || approve.error} />
      {open && <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('cash.openedAt')} value={<bdi className="num" style={{ fontSize: 16 }}>{dt(open.opened_at, lang)}</bdi>} />
        <Stat label={t('cash.float')} value={formatKWD(open.opening_float, lang)} />
        <Stat label={t('cash.expected')} value={formatKWD(open.expected_now ?? '0', lang)} />
        <Stat label={t('cash.status')} value={<span className="pill good">{t('cash.open')}</span>} />
      </div>}
      {!open && !list.isPending && <div className="notice"><Icon name="info" />{t('cash.closedNotice')}</div>}
      <h2 style={{ margin: '18px 0 10px' }}>{t('cash.history')}</h2>
      <div className="tw"><table><thead><tr><th>{t('cash.openedAt')}</th><th>{t('cash.closedAt')}</th><th className="n">{t('cash.float')}</th><th className="n">{t('cash.expected')}</th><th className="n">{t('cash.counted')}</th><th className="n">{t('cash.variance')}</th><th>{t('org.status')}</th><th /></tr></thead>
        <tbody>{list.data?.map((s) => <tr key={s.id}>
          <td className="num">{dt(s.opened_at, lang)}</td><td className="num">{dt(s.closed_at, lang)}</td>
          <td className="n money">{formatKWD(s.opening_float, lang)}</td><td className="n money">{s.expected_cash ? formatKWD(s.expected_cash, lang) : '—'}</td>
          <td className="n money">{s.counted_cash ? formatKWD(s.counted_cash, lang) : '—'}</td>
          <td className="n money" style={{ color: s.variance && s.variance !== '0.000' ? 'var(--danger)' : undefined }}>{s.variance ? formatKWD(s.variance, lang) : '—'}</td>
          <td>{vPill(s)}</td>
          <td>{s.variance_status === 'pending' && can('cash.variance.approve') && <button className="btn sm" disabled={approve.busy} onClick={() => approve.save({ path: `/pos/sessions/${s.id}/approve` })}>{t('cash.approve')}</button>}</td></tr>)}
          {list.data?.length === 0 && <tr><td colSpan={8} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>

      <Dialog open={opening !== null} title={t('cash.openBtn')} onClose={() => setOpening(null)} busy={openS.busy}
        onSubmit={() => openS.save({ path: '/pos/sessions', body: { branch_id: branch!.id, opening_float: opening || '0' } })}>
        <label className="field">{t('cash.floatHelp')}<input className="input" dir="ltr" inputMode="decimal" value={opening ?? ''} onChange={(e) => setOpening(e.target.value)} required /></label>
        <ErrorText error={openS.error} />
      </Dialog>
      <Dialog open={!!closing} title={t('cash.closeBtn')} onClose={() => setClosing(null)} busy={closeS.busy}
        onSubmit={() => closeS.save({ path: `/pos/sessions/${open!.id}/close`, body: { counted_cash: closing!.counted, notes: closing!.notes } })}>
        {closing && <>
          <div className="notice info"><Icon name="info" />{t('cash.countHelp')}</div>
          <label className="field">{t('cash.counted')}<input className="input" dir="ltr" inputMode="decimal" value={closing.counted} onChange={(e) => setClosing({ ...closing, counted: e.target.value })} required /></label>
          <label className="field">{t('cust.notes')}<textarea className="input" value={closing.notes} onChange={(e) => setClosing({ ...closing, notes: e.target.value })} /></label>
          <ErrorText error={closeS.error} />
        </>}
      </Dialog>
    </>
  )
}
