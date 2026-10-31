import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { Head, Icon, Stat } from '../components/ui'

type Data = { sent: number; rated: number; average: number | null; low: number; distribution: Record<string, number>
  items: { id: number; rating: number; comment: string; rated_at: string; customer: string; phone: string; branch_ar: string; branch_en: string; invoice: string }[] }

/** Visit ratings collected over WhatsApp. Low ratings are highlighted so the manager can call the customer back. */
export default function Feedback() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { branch, company } = useBranch()
  const bq = !company && branch ? `?branch_id=${branch.id}` : ''
  const q = useQuery({ queryKey: ['feedback', bq], queryFn: () => api<Data>(`/feedback${bq}`) })
  const d = q.data
  if (q.isError) return <ErrorText error={q.error} />
  const max = d ? Math.max(1, ...Object.values(d.distribution)) : 1
  return (
    <>
      <Head title={t('nav.feedback')} sub={t('fb.sub')} />
      {d && <>
        <div className="grid stats">
          <Stat label={t('fb.average')} value={d.average ? <bdi>{d.average.toFixed(1)} ⭐</bdi> : '—'} sub={t('fb.ratedOf', { n: d.rated, m: d.sent })} />
          <Stat label={t('fb.low')} value={<bdi>{d.low}</bdi>} sub={t('fb.lowHelp')} />
        </div>
        <div className="card" style={{ marginTop: 14, maxWidth: 520 }}>
          {[5, 4, 3, 2, 1].map((n) => <div key={n} className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span style={{ width: 34 }}><bdi>{n} ⭐</bdi></span>
            <div className="prog" style={{ flex: 1 }}><i style={{ width: `${(d.distribution[n] / max) * 100}%` }} /></div>
            <bdi className="small" style={{ width: 30 }}>{d.distribution[n]}</bdi></div>)}
        </div>
        <div className="tw" style={{ marginTop: 14 }}><table><thead><tr><th>{t('fb.rating')}</th><th>{t('cust.name')}</th><th>{t('fb.comment')}</th><th>{t('nav.branches')}</th><th>{t('fb.invoice')}</th><th></th></tr></thead>
          <tbody>{d.items.map((f) => <tr key={f.id} style={f.rating <= 3 ? { background: 'var(--danger-soft, #fdecea)' } : undefined}>
            <td><bdi>{'⭐'.repeat(f.rating)}</bdi></td><td><b>{f.customer}</b></td><td className="small">{f.comment || '—'}</td>
            <td>{lang === 'en' && f.branch_en ? f.branch_en : f.branch_ar}</td><td><bdi>{f.invoice}</bdi></td>
            <td><a className="btn sm ghost" style={{ color: '#25D366' }} href={`https://wa.me/${f.phone}`} target="_blank" rel="noreferrer" aria-label="WhatsApp"><Icon name="whatsapp" /></a></td></tr>)}
            {d.items.length === 0 && <tr><td colSpan={6} className="empty">{t('fb.none')}</td></tr>}</tbody></table></div>
      </>}
    </>
  )
}
