import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Coupon, type LoyaltySettings, type PackagePlan, type Service } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD } from '../money'

type Tab = 'packages' | 'coupons' | 'points'
const today = () => new Date().toISOString().slice(0, 10)

export default function Marketing({ initial = 'packages' }: { initial?: Tab }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const manage = can('marketing.manage')
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(window.location.search).get('tab') as Tab) || initial)
  const services = useQuery({ queryKey: ['services'], queryFn: () => api<Service[]>('/catalog/services') })
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<PackagePlan[]>('/loyalty/plans') })
  const coupons = useQuery({ queryKey: ['coupons'], queryFn: () => api<Coupon[]>('/loyalty/coupons') })
  const settings = useQuery({ queryKey: ['loyalty'], queryFn: () => api<LoyaltySettings>('/loyalty/settings') })
  const [plan, setPlan] = useState<(Partial<PackagePlan> & { service: number }) | null>(null)
  const [coupon, setCoupon] = useState<Partial<Coupon> | null>(null)
  const [cfg, setCfg] = useState<LoyaltySettings | null>(null)
  useEffect(() => { if (settings.data) setCfg(settings.data) }, [settings.data])
  const done = () => { toast(t('common.saved')); setPlan(null); setCoupon(null) }
  const pSave = useSave<PackagePlan>([['plans']], done)
  const cSave = useSave<Coupon>([['coupons']], done)
  const lSave = useSave<LoyaltySettings>([['loyalty']], () => toast(t('common.saved')))
  const svcName = (id: number) => { const s = services.data?.find((x) => x.id === id); return s ? nameOf(s, lang) : '' }
  return (
    <>
      <Head title={t('nav.marketing')} sub={t('mkt.sub')}>
        {manage && tab === 'packages' && <button className="btn primary" onClick={() => { pSave.reset(); setPlan({ name_ar: '', name_en: '', service: services.data?.[0]?.id ?? 0, sessions: 3, price: '', validity_days: 180, is_active: true }) }}><Icon name="plus" />{t('mkt.addPackage')}</button>}
        {manage && tab === 'coupons' && <button className="btn primary" onClick={() => { cSave.reset(); setCoupon({ code: '', kind: 'percent', value: '10', min_total: '0', valid_from: today(), valid_to: today(), max_uses: null, is_active: true }) }}><Icon name="plus" />{t('mkt.addCoupon')}</button>}
      </Head>
      <div className="tabs">{(['packages', 'coupons', 'points'] as Tab[]).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`mkt.tab.${x}`)}</button>)}</div>

      {tab === 'packages' && <>
        <div className="notice info"><Icon name="info" />{t('mkt.packageHelp')}</div>
        <div className="cards">{plans.data?.map((p) => <div className="offer" key={p.id}>
          <div className="row sb"><b>{nameOf(p, lang)}</b>{p.is_active ? <span className="pill good">{t('common.active')}</span> : <span className="pill mute">{t('common.inactive')}</span>}</div>
          <div className="small muted">{svcName(p.service)} × <bdi>{p.sessions}</bdi> · {t('mkt.validDays', { n: p.validity_days })}</div>
          <div className="row sb"><b className="money" style={{ fontSize: 20 }}>{formatKWD(p.price, lang)}</b>
            <span className="small muted">{t('mkt.perSession', { v: formatKWD((Number(p.price) / p.sessions).toFixed(3), lang) })}</span></div>
          {manage && <button className="btn sm" onClick={() => { pSave.reset(); setPlan({ ...p }) }}>{t('common.edit')}</button>}
        </div>)}</div>
        {plans.data?.length === 0 && <div className="empty">{t('common.empty')}</div>}
      </>}

      {tab === 'coupons' && <div className="cards">{coupons.data?.map((c) => <div className="coupon" key={c.id}>
        <div className="val">{c.kind === 'percent' ? `${Number(c.value)}%` : Number(c.value)}<small>{c.kind === 'percent' ? t('mkt.off') : t('mkt.kdOff')}</small></div>
        <div className="bd"><span className="code">{c.code}</span>
          <div className="cap muted"><bdi>{c.valid_from}</bdi> → <bdi>{c.valid_to}</bdi>{Number(c.min_total) > 0 && ` · ${t('mkt.minTotal', { v: formatKWD(c.min_total, lang) })}`}</div>
          <div className="cap">{t('mkt.used', { n: c.used_count })}{c.max_uses ? ` / ${c.max_uses}` : ''}</div>
          {c.max_uses && <div className="prog"><i style={{ width: `${Math.min(100, (c.used_count / c.max_uses) * 100)}%` }} /></div>}
          {manage && <div className="row"><button className="btn sm" onClick={() => cSave.save({ path: `/loyalty/coupons/${c.id}`, method: 'PATCH', body: { is_active: !c.is_active } })}>{c.is_active ? t('platform.deactivate') : t('platform.activate')}</button></div>}
        </div></div>)}
        {coupons.data?.length === 0 && <div className="empty">{t('common.empty')}</div>}</div>}

      {tab === 'points' && cfg && <div className="card" style={{ maxWidth: 560 }}>
        <label className="chk"><span>{t('mkt.pointsOn')}<small>{t('mkt.pointsHelp')}</small></span><input type="checkbox" className="sw" disabled={!manage} checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} /></label>
        <div className="two">
          <label className="field">{t('mkt.perKd')}<input className="input" type="number" min={1} disabled={!manage} value={cfg.points_per_kd} onChange={(e) => setCfg({ ...cfg, points_per_kd: Number(e.target.value) })} /></label>
          <label className="field">{t('mkt.pointValue')}<input className="input" dir="ltr" inputMode="decimal" disabled={!manage} value={cfg.point_value} onChange={(e) => setCfg({ ...cfg, point_value: e.target.value })} /></label>
        </div>
        <label className="field">{t('mkt.minRedeem')}<input className="input" type="number" min={1} disabled={!manage} value={cfg.min_redeem} onChange={(e) => setCfg({ ...cfg, min_redeem: Number(e.target.value) })} /></label>
        <div className="small muted" style={{ margin: '10px 0' }}>{t('mkt.example', { pts: cfg.points_per_kd * 10, v: formatKWD((cfg.points_per_kd * 10 * Number(cfg.point_value)).toFixed(3), lang) })}</div>
        <div className="notice"><Icon name="info" />{t('mkt.accountingNote')}</div>
        <ErrorText error={lSave.error} />
        {manage && <button className="btn primary" disabled={lSave.busy} onClick={() => lSave.save({ path: '/loyalty/settings', method: 'PATCH', body: cfg })}>{t('common.save')}</button>}
      </div>}

      <Dialog open={!!plan} title={plan?.id ? t('common.edit') : t('mkt.addPackage')} onClose={() => setPlan(null)} busy={pSave.busy}
        onSubmit={() => { const { id, ...body } = plan!; pSave.save({ path: id ? `/loyalty/plans/${id}` : '/loyalty/plans', method: id ? 'PATCH' : 'POST', body }) }}>
        {plan && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={plan.name_ar} onChange={(e) => setPlan({ ...plan, name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={plan.name_en} onChange={(e) => setPlan({ ...plan, name_en: e.target.value })} /></label>
          </div>
          <label className="field">{t('svc.service')}<select className="input" value={plan.service} disabled={!!plan.id} onChange={(e) => setPlan({ ...plan, service: Number(e.target.value) })}>
            {services.data?.filter((s) => s.is_active).map((s) => <option key={s.id} value={s.id}>{nameOf(s, lang)} — {t(`biz.${s.business_type}`)}</option>)}</select></label>
          <div className="two">
            <label className="field">{t('mkt.sessions')}<input className="input" type="number" min={2} value={plan.sessions} disabled={!!plan.id} onChange={(e) => setPlan({ ...plan, sessions: Number(e.target.value) })} /></label>
            <label className="field">{t('svc.price')} (KWD)<input className="input" dir="ltr" inputMode="decimal" value={plan.price} onChange={(e) => setPlan({ ...plan, price: e.target.value })} required /></label>
          </div>
          <label className="field">{t('mkt.validity')}<input className="input" type="number" min={1} value={plan.validity_days} onChange={(e) => setPlan({ ...plan, validity_days: Number(e.target.value) })} /></label>
          {plan.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={!!plan.is_active} onChange={(e) => setPlan({ ...plan, is_active: e.target.checked })} /></label>}
          <ErrorText error={pSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!coupon} title={t('mkt.addCoupon')} onClose={() => setCoupon(null)} busy={cSave.busy} onSubmit={() => cSave.save({ path: '/loyalty/coupons', body: coupon })}>
        {coupon && <>
          <div className="two">
            <label className="field">{t('mkt.code')}<input className="input" dir="ltr" style={{ textTransform: 'uppercase' }} value={coupon.code} onChange={(e) => setCoupon({ ...coupon, code: e.target.value })} required /></label>
            <label className="field">{t('mkt.kind')}<select className="input" value={coupon.kind} onChange={(e) => setCoupon({ ...coupon, kind: e.target.value as Coupon['kind'] })}>
              <option value="percent">{t('mkt.percent')}</option><option value="amount">{t('mkt.amount')}</option></select></label>
          </div>
          <div className="two">
            <label className="field">{t('mkt.value')}<input className="input" dir="ltr" inputMode="decimal" value={coupon.value} onChange={(e) => setCoupon({ ...coupon, value: e.target.value })} required /></label>
            <label className="field">{t('mkt.minTotalLabel')}<input className="input" dir="ltr" inputMode="decimal" value={coupon.min_total} onChange={(e) => setCoupon({ ...coupon, min_total: e.target.value })} /></label>
          </div>
          <div className="two">
            <label className="field">{t('svc.from')}<input className="input" type="date" value={coupon.valid_from} onChange={(e) => setCoupon({ ...coupon, valid_from: e.target.value })} required /></label>
            <label className="field">{t('svc.to')}<input className="input" type="date" value={coupon.valid_to} onChange={(e) => setCoupon({ ...coupon, valid_to: e.target.value })} required /></label>
          </div>
          <label className="field">{t('mkt.maxUses')}<input className="input" type="number" min={1} placeholder="∞" value={coupon.max_uses ?? ''} onChange={(e) => setCoupon({ ...coupon, max_uses: e.target.value ? Number(e.target.value) : null })} /></label>
          <ErrorText error={cSave.error} />
        </>}
      </Dialog>
    </>
  )
}
