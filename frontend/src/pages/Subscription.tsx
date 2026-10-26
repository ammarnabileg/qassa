import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, type Plan, type SubscriptionInfo } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { Head, Icon, nameOf, Stat } from '../components/ui'
import { formatKWD } from '../money'

export default function Subscription() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const sub = useQuery({ queryKey: ['subscription'], queryFn: () => api<SubscriptionInfo>('/subscription') })
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/platform/plans') })
  if (sub.isError) return <ErrorText error={sub.error} />
  const s = sub.data
  const limit = (n: number) => (n >= 99 ? t('plan.unlimited') : String(n))
  return (
    <>
      <Head title={t('nav.subscription')} sub={t('plan.sub')} />
      {s?.plan && <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('plan.current')} value={nameOf(s.plan, lang)} />
        <Stat label={t('plan.branchesUsed')} value={<bdi>{s.usage.branches} / {limit(s.plan.max_branches)}</bdi>} />
        <Stat label={t('plan.staffUsed')} value={<bdi>{s.usage.staff} / {limit(s.plan.max_staff)}</bdi>} />
        <Stat label={t('plan.renews')} value={<bdi className="num">{s.current_period_end}</bdi>} />
      </div>}
      {s && s.hosts.length > 0 && <div className="card" style={{ marginBottom: 14 }}>
        <h2>{t('plan.appLinks')}</h2><div className="small muted">{t('plan.appLinksHelp')}</div>
        <div className="list">{s.hosts.map((h) => <div className="li" key={h}><Icon name="link" /><a className="grow code" href={`https://${h}`} target="_blank" rel="noreferrer">{h}</a></div>)}</div>
      </div>}
      <div className="notice info"><Icon name="info" />{t('plan.changeVia')}</div>
      <div className="cards">{plans.data?.map((p) => <div key={p.id} className={`plan${s?.plan?.code === p.code ? ' hl' : ''}`}>
        <div className="row sb"><b>{nameOf(p, lang)}</b>{s?.plan?.code === p.code && <span className="pill good">{t('plan.yours')}</span>}</div>
        <div className="price">{formatKWD(p.monthly_price, lang)}<span className="small muted"> / {t('plan.month')}</span></div>
        <ul>
          <li><Icon name="store" />{t('plan.branches', { n: limit(p.max_branches) })}</li>
          <li><Icon name="users" />{t('plan.staff', { n: limit(p.max_staff) })}</li>
          <li><Icon name="link" />{p.custom_domain ? t('plan.customDomain') : t('plan.subdomain')}</li>
        </ul>
      </div>)}</div>
    </>
  )
}
