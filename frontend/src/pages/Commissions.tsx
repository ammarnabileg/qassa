import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, useToast } from '../components/ui'
import { formatKWD } from '../money'

type Row = { staff_id: number; name_ar: string; name_en: string; rate: string; balance: string; recent: { kind: string; amount: string; base: string; reference: string; created_at: string }[] }

export default function Commissions() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const { branch } = useBranch()
  const toast = useToast()
  const q = useQuery({ queryKey: ['commissions'], queryFn: () => api<Row[]>('/commissions') })
  const [open, setOpen] = useState<Row | null>(null)
  const [pay, setPay] = useState<{ row: Row; amount: string; reference: string } | null>(null)
  const { save, busy, error, reset } = useSave<unknown>([['commissions']], () => { toast(t('common.saved')); setPay(null) })
  const name = (r: Row) => (lang === 'en' && r.name_en) || r.name_ar
  return (
    <>
      <Head title={t('nav.commissions')} sub={t('com.sub')} />
      <ErrorText error={q.error} />
      <div className="notice info"><Icon name="info" />{t('com.rule')}</div>
      <div className="tw"><table><thead><tr><th>{t('staff.name')}</th><th className="n">{t('com.rate')}</th><th className="n">{t('com.balance')}</th><th /></tr></thead>
        <tbody>{q.data?.map((r) => <tr key={r.staff_id} className="click" onClick={() => setOpen(r)}>
          <td><b>{name(r)}</b></td><td className="n"><bdi>{Number(r.rate)}%</bdi></td>
          <td className="n money">{formatKWD(r.balance, lang)}</td>
          <td>{can('commission.pay') && Number(r.balance) > 0 && <button className="btn sm" onClick={(e) => { e.stopPropagation(); reset(); setPay({ row: r, amount: r.balance, reference: '' }) }}>{t('com.pay')}</button>}</td></tr>)}
          {q.data?.length === 0 && <tr><td colSpan={4} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>

      <Dialog open={!!open} title={open ? name(open) : ''} onClose={() => setOpen(null)}>
        {open && <div className="list">{open.recent.map((e, i) => <div className="li" key={i}>
          <span className={`pill ${e.kind === 'accrual' ? 'good' : e.kind === 'payout' ? 'info' : 'warn'}`}>{t(`com.k.${e.kind}`)}</span>
          <div className="grow small"><span className="code">{e.reference}</span>{Number(e.base) > 0 && <span className="muted"> · {t('com.on', { v: formatKWD(e.base, lang) })}</span>}</div>
          <b className="money">{formatKWD(e.amount, lang)}</b></div>)}
          {open.recent.length === 0 && <div className="empty">{t('common.empty')}</div>}</div>}
      </Dialog>

      <Dialog open={!!pay} title={pay ? `${t('com.pay')}: ${name(pay.row)}` : ''} onClose={() => setPay(null)} busy={busy}
        onSubmit={() => save({ path: `/staff/${pay!.row.staff_id}/payout`, body: { amount: pay!.amount, reference: pay!.reference, branch_id: branch?.id } })}>
        {pay && <>
          <div className="small muted">{t('com.payHelp')}</div>
          <div className="two">
            <label className="field">{t('inv.amount')}<input className="input" dir="ltr" inputMode="decimal" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} required /></label>
            <label className="field">{t('pos.transferRef')}<input className="input" dir="ltr" value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} required /></label>
          </div>
          <ErrorText error={error} />
        </>}
      </Dialog>
    </>
  )
}
