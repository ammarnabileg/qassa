import { SvcIcon } from '../components/ServiceArt'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, type Appointment, type CashSession, type Category, type Customer, type Invoice, type PackagePlan, type Product, type Quote, type Wallet } from '../api/client'
import { useAuth } from '../auth'
import { OfflineSetup } from '../offline/OfflineSetup'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD, fromFils, toFils } from '../money'
import { Receipt } from './Invoices'
import { useServicesStaff } from './Bookings'

type Kind = 'service' | 'product' | 'package'
type CartLine = { key: string; kind: Kind; id: number; staff_id: number | null; qty: number; discount: string; redeem_package_id: number | null }
type Mode = 'cash' | 'knet' | 'transfer' | 'split' | 'credit'

export function useOpenSession() {
  const { branch } = useBranch()
  const { can } = useAuth()
  return useQuery({ queryKey: ['session', branch?.id], enabled: !!branch && can('cash.session.open'),
    queryFn: async () => (await api<CashSession[]>(`/pos/sessions?branch_id=${branch!.id}`)).find((s) => s.status === 'open') ?? null })
}

/** Debounce a value so the server quote is not asked on every keystroke. */
function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const h = setTimeout(() => setV(value), ms); return () => clearTimeout(h) }, [value, ms])
  return v
}

export default function POS() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const { branch } = useBranch()
  const toast = useToast()
  const nav = useNavigate()
  const loc = useLocation()
  const { services, staff, branchServices, staffFor } = useServicesStaff()
  const cats = useQuery({ queryKey: ['categories'], queryFn: () => api<Category[]>('/catalog/categories') })
  const products = useQuery({ queryKey: ['products', branch?.id], enabled: !!branch && can('inventory.view'),
    queryFn: () => api<Product[]>(`/inventory/products?branch_id=${branch!.id}`) })
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<PackagePlan[]>('/loyalty/plans') })
  const session = useOpenSession()
  const [tab, setTab] = useState<Kind>('service')
  const [cat, setCat] = useState<number | 'all'>('all')
  const [q, setQ] = useState('')
  const [lines, setLines] = useState<CartLine[]>([])
  const [appointment, setAppointment] = useState<Appointment | null>(null)
  const [cq, setCq] = useState('')
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [beneficiary, setBeneficiary] = useState<number | null>(null)
  const [coupon, setCoupon] = useState('')
  const [points, setPoints] = useState('')
  const [tip, setTip] = useState('')
  const [tipStaff, setTipStaff] = useState<number | null>(null)
  const [mode, setMode] = useState<Mode>('cash')
  const [tendered, setTendered] = useState('')
  const [split, setSplit] = useState({ cash: '', card: '' })
  const [ref, setRef] = useState('')
  const [paidNow, setPaidNow] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [receipt, setReceipt] = useState<Invoice | null>(null)
  const found = useQuery({ queryKey: ['customers', cq], enabled: cq.length >= 2 && !customer, queryFn: () => api<Customer[]>(`/customers?q=${encodeURIComponent(cq)}`) })
  const wallet = useQuery({ queryKey: ['wallet', customer?.id], enabled: !!customer, queryFn: () => api<Wallet>(`/customers/${customer!.id}/wallet`) })

  // coming from the bookings board: the visit's services and staff are pre-filled
  useEffect(() => {
    const a = (loc.state as { appointment?: Appointment } | null)?.appointment
    if (!a) return
    setAppointment(a)
    setLines(a.items.map((i) => ({ key: crypto.randomUUID(), kind: 'service', id: i.service_id, staff_id: i.staff_id, qty: 1, discount: '0', redeem_package_id: null })))
    if (a.customer) api<Customer>(`/customers/${a.customer}`).then((c) => { setCustomer(c); setBeneficiary(a.beneficiary) }).catch(() => undefined)
    nav('.', { replace: true, state: null })
  }, [loc.state, nav])

  const payload = (l: CartLine) => ({
    [l.kind === 'service' ? 'service_id' : l.kind === 'product' ? 'product_id' : 'package_plan_id']: l.id,
    staff_id: l.staff_id, qty: l.qty, discount: l.discount || '0', redeem_package_id: l.redeem_package_id })
  const cartBody = { branch_id: branch?.id, customer_id: customer?.id ?? null, coupon_code: coupon.trim(),
    redeem_points: Number(points) || 0, lines: lines.map(payload) }
  // the totals always come from the server: branch prices, coupons, points and package sessions are applied there
  const quoteKey = useDebounced(JSON.stringify(cartBody))
  const quote = useQuery({ queryKey: ['quote', quoteKey], enabled: !!branch && lines.length > 0, retry: false,
    queryFn: () => api<Quote>('/pos/quote', { method: 'POST', body: JSON.parse(quoteKey) }) })
  const fresh = quoteKey === JSON.stringify(cartBody) && !quote.isFetching && !!quote.data

  const name = (l: CartLine) => {
    if (l.kind === 'service') { const s = services.find((x) => x.id === l.id); return s ? nameOf(s, lang) : '…' }
    if (l.kind === 'product') { const p = products.data?.find((x) => x.id === l.id); return p ? nameOf(p, lang) : '…' }
    const p = plans.data?.find((x) => x.id === l.id); return p ? nameOf(p, lang) : '…'
  }
  const add = (kind: Kind, id: number) => {
    const ex = lines.find((l) => l.kind === kind && l.id === id && !l.redeem_package_id && kind !== 'package')
    if (ex && !appointment) setLines(lines.map((l) => (l === ex ? { ...l, qty: l.qty + 1 } : l)))
    else setLines([...lines, { key: crypto.randomUUID(), kind, id, qty: 1, discount: '0', redeem_package_id: null,
      staff_id: kind === 'service' && staffFor(id).length === 1 ? staffFor(id)[0].id : null }])
  }
  const setLine = (k: string, p: Partial<CartLine>) => setLines(lines.map((l) => (l.key === k ? { ...l, ...p } : l)))
  const reset = () => {
    setLines([]); setAppointment(null); setCustomer(null); setBeneficiary(null); setCq(''); setCoupon(''); setPoints(''); setTip(''); setTipStaff(null)
    setTendered(''); setSplit({ cash: '', card: '' }); setRef(''); setPaidNow(''); setMode('cash'); setKey(crypto.randomUUID())
  }

  const total = toFils(quote.data?.total ?? '0') + safeFils(tip)
  const totalStr = fromFils(total)
  const payments = (): { method: string; amount: string; reference?: string }[] => {
    if (total === 0n) return []
    if (mode === 'cash') return [{ method: 'cash', amount: totalStr }]
    if (mode === 'knet' || mode === 'transfer') return [{ method: mode, amount: totalStr, reference: ref }]
    if (mode === 'split') return [{ method: 'cash', amount: split.cash || '0' }, { method: 'knet', amount: split.card || '0', reference: ref }].filter((p) => safeFils(p.amount) > 0n)
    return paidNow && safeFils(paidNow) > 0n ? [{ method: 'cash', amount: paidNow }] : []
  }
  const splitOk = mode !== 'split' || safeFils(split.cash) + safeFils(split.card) === total
  const change = mode === 'cash' && tendered ? safeFils(tendered) - total : null
  const needsDrawer = total > 0n && (mode === 'cash' || mode === 'split' || (mode === 'credit' && safeFils(paidNow) > 0n)) && !session.data
  const { save, busy, error } = useSave<Invoice>([['appointments'], ['invoices'], ['session'], ['products'], ['wallet']], (inv) => {
    setReceipt(inv); toast(t('pos.done', { n: inv.number })); reset()
  })
  const checkout = () => save({ path: '/pos/checkout', idempotencyKey: key, body: {
    ...cartBody, appointment_id: appointment?.id ?? null, beneficiary_id: beneficiary, expected_total: quote.data!.total,
    tip: tip || '0', tip_staff_id: safeFils(tip) > 0n ? tipStaff : null, payments: payments() } })

  if (!branch) return <p className="muted">{t('common.loading')}</p>
  const staffName = (id: number) => { const p = staff.find((x) => x.id === id); return p ? (lang === 'en' && p.full_name_en ? p.full_name_en : p.full_name_ar) : '' }
  const myCats = (cats.data ?? []).filter((c) => c.business_type === branch.business_type)
  const match = (x: { name_ar: string; name_en?: string }) => !q || nameOf(x, lang).toLowerCase().includes(q.toLowerCase())
  const shownServices = branchServices.filter((s) => (cat === 'all' || s.category === cat) && match(s))
  const shownProducts = (products.data ?? []).filter((p) => p.is_active && p.kind === 'retail' && p.sale_price && match(p))
  const shownPlans = (plans.data ?? []).filter((p) => p.is_active && branchServices.some((s) => s.id === p.service) && match(p))
  const pkgFor = (serviceId: number) => (wallet.data?.packages ?? []).filter((p) => p.service_id === serviceId && p.sessions_left > 0)
  return (
    <>
      <Head title={t('nav.pos')} sub={`${nameOf(branch, lang)} · ${new Date().toLocaleDateString(lang === 'ar' ? 'ar-KW' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kuwait' })}`}>
        <input className="input" placeholder={t('pos.search')} style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />
      </Head>
      {can('cash.session.open') && session.data === null && <div className="notice"><Icon name="alert" />{t('pos.noDrawer')} <Link to="/cash" style={{ color: 'inherit', fontWeight: 700 }}>{t('pos.openDrawer')}</Link></div>}
      <OfflineSetup />
      <div className="pos">
        <div>
          <div className="tabs">
            <button className={tab === 'service' ? 'on' : ''} onClick={() => setTab('service')}>{t('pos.tab.service')}</button>
            {can('inventory.view') && <button className={tab === 'product' ? 'on' : ''} onClick={() => setTab('product')}>{t('pos.tab.product')}</button>}
            {shownPlans.length > 0 && <button className={tab === 'package' ? 'on' : ''} onClick={() => setTab('package')}>{t('pos.tab.package')}</button>}
          </div>
          {tab === 'service' && <>
            <div className="seg cats">
              <button className={cat === 'all' ? 'on' : ''} onClick={() => setCat('all')}>{t('pos.all')}</button>
              {myCats.map((c) => <button key={c.id} className={cat === c.id ? 'on' : ''} onClick={() => setCat(c.id)}>{nameOf(c, lang)}</button>)}
            </div>
            <div className="grid items">
              {shownServices.map((s) => <button key={s.id} className="item" disabled={!s.current_price} onClick={() => add('service', s.id)}>
                <SvcIcon s={s} /><b>{nameOf(s, lang)}</b>
                <span className="cap muted"><bdi>{s.duration_minutes}</bdi> {t('svc.min')}</span>
                <span className="money">{s.current_price ? formatKWD(s.current_price, lang) : t('svc.noPrice')}</span></button>)}
              {shownServices.length === 0 && <div className="empty">{t('pos.noItems')}</div>}
            </div>
          </>}
          {tab === 'product' && <div className="grid items">
            {shownProducts.map((p) => { const qty = Number(p.stock.qty); return <button key={p.id} className="item" disabled={qty <= 0} onClick={() => add('product', p.id)}>
              <span className="ic"><Icon name="box" /></span><b>{nameOf(p, lang)}</b>
              <span className={`stk pill ${qty > 5 ? 'mute' : qty > 0 ? 'warn' : 'bad'}`}><bdi>{qty}</bdi></span>
              <span className="money">{formatKWD(p.sale_price!, lang)}</span></button> })}
            {shownProducts.length === 0 && <div className="empty">{t('pos.noItems')}</div>}
          </div>}
          {tab === 'package' && <div className="grid items">
            {shownPlans.map((p) => <button key={p.id} className="item" onClick={() => add('package', p.id)}>
              <span className="ic"><Icon name="layers" /></span><b>{nameOf(p, lang)}</b>
              <span className="cap muted">{t('pkg.sessions', { n: p.sessions })}</span>
              <span className="money">{formatKWD(p.price, lang)}</span></button>)}
          </div>}
        </div>

        <div className="card cart">
          <div className="row sb"><h2>{t('pos.invoice')}</h2><button className="btn ghost sm danger" onClick={reset}>{t('pos.clear')}</button></div>
          {appointment && <div className="notice info"><Icon name="calendar" />{t('pos.fromBooking', { name: appointment.beneficiary_name || appointment.customer_name })}</div>}
          {customer ? <div className="li"><span className="av">{customer.full_name[0]}</span><div className="grow"><b>{customer.full_name}</b> <bdi className="cap muted">+{customer.phone}</bdi>
            {wallet.data && <div className="cap muted">⭐ <bdi>{wallet.data.points}</bdi> {t('pos.pointsUnit')}{wallet.data.packages.length > 0 && ` · ${t('pos.hasPackages', { n: wallet.data.packages.length })}`}</div>}</div>
            {!appointment && <button className="btn sm ghost" onClick={() => { setCustomer(null); setBeneficiary(null); setPoints(''); setLines(lines.map((l) => ({ ...l, redeem_package_id: null }))) }}><Icon name="close" /></button>}</div>
            : <>
              <input className="input" placeholder={t('pos.customer')} value={cq} onChange={(e) => setCq(e.target.value)} />
              {found.data && found.data.length > 0 && <div className="list">{found.data.slice(0, 4).map((c) => <button key={c.id} className="li btn ghost" style={{ justifyContent: 'flex-start' }}
                onClick={() => { setCustomer(c); setBeneficiary(c.beneficiaries.find((b) => b.relation !== 'self')?.id ?? c.beneficiaries[0]?.id ?? null) }}>
                <b>{c.full_name}</b> <bdi className="cap muted">+{c.phone}</bdi></button>)}</div>}
            </>}
          {customer && customer.beneficiaries.length > 1 && <select className="input" value={beneficiary ?? ''} onChange={(e) => setBeneficiary(Number(e.target.value))}>
            {customer.beneficiaries.map((b) => <option key={b.id} value={b.id}>{b.full_name}</option>)}</select>}

          <div className="lines">
            {lines.map((l, i) => <div className="line" key={l.key}>
              <b className="small">{name(l)}{l.kind !== 'service' && <> <span className="pill mute">{t(`pos.tab.${l.kind}`)}</span></>}</b>
              <span className="money small">{fresh && quote.data!.lines[i] ? formatKWD(quote.data!.lines[i].total, lang) : '…'}</span>
              {l.kind === 'service' ? <select className="input" style={{ padding: '4px 8px', fontSize: 13 }} value={l.staff_id ?? ''} onChange={(e) => setLine(l.key, { staff_id: Number(e.target.value) || null })}>
                <option value="">{t('pos.staff')}</option>
                {staffFor(l.id).map((p) => <option key={p.id} value={p.id}>{staffName(p.id)}</option>)}</select> : <span />}
              <div className="qty">
                <button onClick={() => l.qty > 1 ? setLine(l.key, { qty: l.qty - 1 }) : setLines(lines.filter((x) => x.key !== l.key))} aria-label="-">−</button>
                <bdi>{l.qty}</bdi><button disabled={l.kind === 'package'} onClick={() => setLine(l.key, { qty: l.qty + 1 })} aria-label="+">+</button>
              </div>
              {l.kind === 'service' && pkgFor(l.id).length > 0 && <label className="cap row" style={{ gridColumn: '1 / -1', gap: 6 }}>
                <input type="checkbox" checked={!!l.redeem_package_id} onChange={(e) => setLine(l.key, { redeem_package_id: e.target.checked ? pkgFor(l.id)[0].id : null, discount: '0' })} />
                {t('pos.usePackage', { left: pkgFor(l.id)[0].sessions_left })}</label>}
              {!l.redeem_package_id && (can('pos.discount.line') || can('pos.discount.override')) && <label className="cap muted row" style={{ gridColumn: '1 / -1', gap: 6 }}>{t('pos.discount')}
                <input className="input" dir="ltr" inputMode="decimal" style={{ width: 90, padding: '3px 8px' }} value={l.discount} onChange={(e) => setLine(l.key, { discount: e.target.value })} /></label>}
            </div>)}
            {lines.length === 0 && <div className="empty small">{t('pos.empty')}</div>}
          </div>

          <div className="two">
            <input className="input" dir="ltr" placeholder={t('pos.coupon')} style={{ textTransform: 'uppercase' }} value={coupon} onChange={(e) => setCoupon(e.target.value)} />
            {customer && (wallet.data?.points ?? 0) > 0
              ? <input className="input" dir="ltr" inputMode="numeric" placeholder={t('pos.redeemPoints', { n: wallet.data!.points })} value={points} onChange={(e) => setPoints(e.target.value.replace(/\D/g, ''))} />
              : <span />}
          </div>
          {quote.error ? <ErrorText error={quote.error} /> : null}
          {quote.data && <>
            <div className="tot"><span className="muted">{t('pos.subtotal')}</span><span className="money">{formatKWD(quote.data.subtotal, lang)}</span></div>
            <div className="tot"><span className="muted">{t('pos.discount')}{quote.data.coupon_discount !== '0.000' && ` (${t('pos.couponApplied')})`}{quote.data.points > 0 && ` (⭐ ${quote.data.points})`}</span><span className="money">{formatKWD(quote.data.discount_total, lang)}</span></div>
          </>}
          <div className="two">
            <label className="field">{t('pos.tip')}<input className="input" dir="ltr" inputMode="decimal" placeholder="0.000" value={tip} onChange={(e) => setTip(e.target.value)} /></label>
            {safeFils(tip) > 0n ? <label className="field">{t('pos.tipFor')}<select className="input" value={tipStaff ?? ''} onChange={(e) => setTipStaff(Number(e.target.value) || null)}>
              <option value="">—</option>{staff.filter((p) => p.is_active).map((p) => <option key={p.id} value={p.id}>{staffName(p.id)}</option>)}</select></label> : <span />}
          </div>
          <div className="tot big"><span>{t('pos.total')}</span><span className="money">{quote.data ? formatKWD(totalStr, lang) : '—'}</span></div>

          {total > 0n && <div className="pay">
            {(['cash', 'knet', 'transfer', 'split'] as const).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`pos.m.${m}`)}</button>)}
            {can('pos.credit_sale') && <button className={mode === 'credit' ? 'on' : ''} onClick={() => setMode('credit')}>{t('pos.m.credit')}</button>}
          </div>}
          {total > 0n && mode === 'cash' && <>
            <label className="field">{t('pos.tendered')}<input className="input" dir="ltr" inputMode="decimal" value={tendered} onChange={(e) => setTendered(e.target.value)} /></label>
            {change !== null && <div className="tot"><span className="muted">{t('pos.change')}</span><b className="money">{change >= 0n ? formatKWD(fromFils(change), lang) : '—'}</b></div>}
          </>}
          {mode === 'split' && <div className="two">
            <label className="field">{t('pos.m.cash')}<input className="input" dir="ltr" inputMode="decimal" value={split.cash} onChange={(e) => setSplit({ ...split, cash: e.target.value })} /></label>
            <label className="field">{t('pos.m.knet')}<input className="input" dir="ltr" inputMode="decimal" value={split.card} onChange={(e) => setSplit({ ...split, card: e.target.value })} /></label>
          </div>}
          {(mode === 'knet' || mode === 'transfer' || (mode === 'split' && safeFils(split.card) > 0n)) && total > 0n &&
            <label className="field">{t(mode === 'transfer' ? 'pos.transferRef' : 'pos.knetRef')}<input className="input" dir="ltr" value={ref} onChange={(e) => setRef(e.target.value)} /></label>}
          {mode === 'credit' && <>
            <div className="small muted">{t('pos.creditHelp')}</div>
            <label className="field">{t('pos.paidNow')}<input className="input" dir="ltr" inputMode="decimal" value={paidNow} onChange={(e) => setPaidNow(e.target.value)} /></label>
          </>}
          {!splitOk && <div className="notice bad">{t('pos.splitMismatch')}</div>}
          {needsDrawer && <div className="notice">{t('pos.noDrawer')}</div>}
          <ErrorText error={error} />
          <button className="btn brand lg" disabled={!lines.length || busy || !fresh || !splitOk || needsDrawer || (safeFils(tip) > 0n && !tipStaff)}
            onClick={checkout}>{busy ? t('common.loading') : t('pos.checkout')}</button>
        </div>
      </div>
      {receipt && <Receipt invoice={receipt} onClose={() => setReceipt(null)} />}
    </>
  )
}

export function safeFils(v: string) {
  try { return toFils(v) } catch { return 0n }
}
