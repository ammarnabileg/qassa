import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api, type Customer } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'

type Overview = {
  settings: { enabled: boolean; points_per_kd: number; point_value: string; min_redeem: number }
  outstanding: number; outstanding_value: string; redeemed_month: number
  balances: { customer_id: number; name: string; phone: string; kids: string[]; balance: number; earned: number; used: number; value: string }[]
  recent: { id: number; name: string; kind: 'earn' | 'redeem' | 'reverse' | 'adjust'; points: number; at: string; invoice: string; note: string }[]
}

/** Points & loyalty (reference v-loyal): program status, balances per family and the latest movements. */
export default function Loyalty() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const data = useQuery({ queryKey: ['loyalty-points'], queryFn: () => api<Overview>('/loyalty/points') })
  const [adj, setAdj] = useState<{ q: string; customer: Customer | null; points: string; sign: 1 | -1; note: string } | null>(null)
  const found = useQuery({ queryKey: ['customers', adj?.q], enabled: !!adj && adj.q.length >= 2 && !adj.customer, queryFn: () => api<Customer[]>(`/customers?q=${encodeURIComponent(adj!.q)}`) })
  const save = useSave<{ balance: number }>([['loyalty-points'], ['wallet']], (r) => { setAdj(null); toast(t('loy.newBalance', { n: r.balance })) })
  const d = data.data
  const when = (iso: string) => new Date(iso).toLocaleDateString(lang === 'ar' ? 'ar-KW' : 'en-GB', { day: 'numeric', month: 'long', timeZone: 'Asia/Kuwait' })
  if (data.isError) return <ErrorText error={data.error} />
  return (
    <>
      <Head title={t('nav.loyalty')} sub={t('loy.sub')}>
        {can('marketing.manage') && <button className="btn" onClick={() => { save.reset(); setAdj({ q: '', customer: null, points: '', sign: 1, note: '' }) }}>{t('loy.adjust')}</button>}
        {can('catalog.view') && <button className="btn primary" onClick={() => nav('/marketing?tab=points')}>{t('loy.rules')}</button>}
      </Head>
      {d && <>
        <div className="grid stats">
          <Stat label={t('loy.status')} value={<span className={`pill ${d.settings.enabled ? 'good' : 'mute'}`}>{d.settings.enabled ? t('loy.on') : t('loy.off')}</span>}
            sub={t('loy.earnRule', { n: d.settings.points_per_kd })} />
          <Stat label={t('loy.outstanding')} value={<bdi>{d.outstanding}</bdi>} sub={t('loy.liability', { v: formatKWD(d.outstanding_value, lang) })} />
          <Stat label={t('loy.pointValue')} value={formatKWD(d.settings.point_value, lang)} sub={t('loy.minRedeem', { n: d.settings.min_redeem })} />
          <Stat label={t('loy.redeemedMonth')} value={<bdi>{d.redeemed_month}</bdi>} />
        </div>
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(0,1fr)', gap: 14, marginTop: 16, alignItems: 'start' }}>
          <div><h2 style={{ marginBottom: 10 }}>{t('loy.balances')}</h2>
            <div className="tw"><table><thead><tr><th>{t('loy.family')}</th><th className="n">{t('loy.balance')}</th><th className="n">{t('loy.earned')}</th><th className="n">{t('loy.used')}</th><th className="n">{t('loy.worth')}</th><th></th></tr></thead>
              <tbody>{d.balances.map((b) => <tr key={b.customer_id}><td><b>{b.kids.length ? b.kids.join('، ') : b.name}</b>{b.kids.length > 0 && <div className="cap muted">{b.name}</div>}</td>
                <td className="n"><b><bdi>{b.balance}</bdi></b></td><td className="n"><bdi>{b.earned}</bdi></td><td className="n"><bdi>{b.used}</bdi></td>
                <td className="n money">{formatKWD(b.value, lang)}</td>
                <td><a className="btn sm ghost" style={{ color: '#25D366' }} href={`https://wa.me/${b.phone}`} target="_blank" rel="noreferrer" aria-label="WhatsApp"><Icon name="whatsapp" /></a></td></tr>)}
                {d.balances.length === 0 && <tr><td colSpan={6} className="empty">{t('loy.none')}</td></tr>}</tbody></table></div></div>
          <div><h2 style={{ marginBottom: 10 }}>{t('loy.recent')}</h2>
            <div className="card"><div className="list">{d.recent.map((e) => <div className="li" key={e.id}>
              <div className="grow"><b className="small">{e.name}</b><div className="cap muted">{e.invoice ? t('loy.invoice', { n: e.invoice }) : t(`loy.k.${e.kind}`)}{e.note && !e.invoice ? ` · ${e.note}` : ''} · {when(e.at)}</div></div>
              <b style={{ color: e.points >= 0 ? 'var(--brand-700)' : 'var(--danger, #c0392b)' }}><bdi>{e.points > 0 ? '+' : ''}{e.points}</bdi></b></div>)}
              {d.recent.length === 0 && <div className="small muted">{t('loy.none')}</div>}</div></div></div>
        </div>
      </>}

      <Dialog open={!!adj} title={t('loy.adjust')} onClose={() => setAdj(null)} busy={save.busy} submitLabel={t('common.save')}
        onSubmit={() => save.save({ path: '/loyalty/points/adjust', method: 'POST', body: { customer_id: adj!.customer?.id, points: adj!.sign * Number(adj!.points || 0), note: adj!.note } })}>
        {adj && <>
          {adj.customer ? <div className="li"><b className="grow">{adj.customer.full_name}</b><button type="button" className="btn sm ghost" onClick={() => setAdj({ ...adj, customer: null })}><Icon name="close" /></button></div>
            : <><input className="input" placeholder={t('pos.customer')} value={adj.q} onChange={(e) => setAdj({ ...adj, q: e.target.value })} />
              <div className="list">{found.data?.slice(0, 5).map((c) => <button type="button" key={c.id} className="li btn ghost" style={{ justifyContent: 'flex-start' }} onClick={() => setAdj({ ...adj, customer: c })}>
                <b>{c.full_name}</b> <bdi className="cap muted">+{c.phone}</bdi></button>)}</div></>}
          <div className="seg"><button type="button" className={adj.sign === 1 ? 'on' : ''} onClick={() => setAdj({ ...adj, sign: 1 })}>{t('loy.add')}</button>
            <button type="button" className={adj.sign === -1 ? 'on' : ''} onClick={() => setAdj({ ...adj, sign: -1 })}>{t('loy.deduct')}</button></div>
          <label className="field">{t('loy.points')}<input className="input" dir="ltr" inputMode="numeric" value={adj.points} onChange={(e) => setAdj({ ...adj, points: e.target.value.replace(/\D/g, '') })} required /></label>
          <label className="field">{t('loy.reason')}<input className="input" value={adj.note} onChange={(e) => setAdj({ ...adj, note: e.target.value })} required /></label>
          <ErrorText error={save.error} />
        </>}
      </Dialog>
    </>
  )
}
