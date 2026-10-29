import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { pending } from '../offline/engine'

type Sale = { id: number; ref: string; status: 'synced' | 'review' | 'conflict'; flags: string[]; error: string; invoice_id: number | null
  invoice_number: string | null; created_at: string; total: string; device: string }
type Dev = { id: number; name: string; branch_id: number; last_sync_at: string | null; received: number; missing_seq: number[] }

/** Receipts made without internet: what needs a manager's look, what could not be posted, and lost receipts (D-013). */
export default function OfflineReceipts() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can, membership } = useAuth()
  const toast = useToast()
  const [f, setF] = useState<'review' | 'conflict' | ''>('review')
  const sales = useQuery({ queryKey: ['offline-sales', f], queryFn: () => api<Sale[]>(`/pos/offline/sales${f ? `?status=${f}` : ''}`) })
  const devices = useQuery({ queryKey: ['pos-devices'], queryFn: () => api<Dev[]>('/pos/devices') })
  const local = useQuery({ queryKey: ['offline-local'], queryFn: () => pending(membership!.tenant_id).then((x) => x.length), enabled: !!membership })
  const act = useSave<Sale>([['offline-sales'], ['invoices']], (r) => toast(t(r.status === 'conflict' ? 'off.stillConflict' : 'common.saved')))
  const fmt = (d: string) => new Date(d).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })
  const flag = (x: string) => { const [k, v] = x.split(':'); return t(`off.flag.${k}`, { v: v && t(`errors.${v}`, { defaultValue: v }) }) }
  const missing = (devices.data ?? []).filter((d) => d.missing_seq.length > 0)
  const manage = can('pos.discount.override')
  return (
    <>
      <Head title={t('nav.offline')} sub={t('off.pageSub')} />
      <ErrorText error={sales.error || act.error} />
      {missing.map((d) => <div className="notice bad" key={d.id}><Icon name="alert" />{t('off.missing', { device: d.name, list: d.missing_seq.map((n) => `OFF-${d.id}-${n}`).join('، ') })}</div>)}
      <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('off.thisDevice')} value={<bdi>{local.data ?? 0}</bdi>} />
        <Stat label={t('off.devices')} value={<bdi>{devices.data?.length ?? 0}</bdi>} />
      </div>
      <div className="seg" style={{ marginBottom: 14 }}>{(['review', 'conflict', ''] as const).map((x) => <button key={x} className={f === x ? 'on' : ''} onClick={() => setF(x)}>{t(`off.st.${x || 'all'}`)}</button>)}</div>
      <div className="tw"><table><thead><tr><th>{t('off.ref')}</th><th>{t('inv.time')}</th><th>{t('off.device')}</th><th className="n">{t('pos.total')}</th><th>{t('inv.number')}</th><th>{t('off.what')}</th><th /></tr></thead>
        <tbody>{sales.data?.map((x) => <tr key={x.id}>
          <td className="num">{x.ref}</td><td className="small">{fmt(x.created_at)}</td><td className="small">{x.device}</td>
          <td className="n money">{formatKWD(x.total, lang)}</td><td className="num">{x.invoice_number ?? '—'}</td>
          <td className="small">{x.status === 'conflict' ? <span className="pill bad">{t(`errors.${x.error}`, { defaultValue: x.error })}</span>
            : x.flags.length ? x.flags.map((g) => <div key={g}>{flag(g)}</div>) : <span className="pill good">{t('off.st.synced')}</span>}</td>
          <td>{manage && x.status === 'review' && <button className="btn sm" onClick={() => act.save({ path: `/pos/offline/sales/${x.id}/acknowledge` })}>{t('off.ack')}</button>}
            {manage && x.status === 'conflict' && <button className="btn sm" onClick={() => act.save({ path: `/pos/offline/sales/${x.id}/retry` })}>{t('off.retry')}</button>}</td></tr>)}
          {sales.data?.length === 0 && <tr><td colSpan={7} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>
      <div className="notice info" style={{ marginTop: 14 }}><Icon name="info" />{t('off.howItWorks')}</div>
    </>
  )
}
