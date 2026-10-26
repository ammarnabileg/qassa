import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, type Appointment, type CashSession, type Category, type Customer, type Invoice } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD, fromFils, toFils } from '../money'
import { Receipt } from './Invoices'
import { useServicesStaff } from './Bookings'

type CartLine = { key: string; service_id: number; staff_id: number | null; qty: number; discount: string }
type Mode = 'cash' | 'knet' | 'transfer' | 'split' | 'credit'

export function useOpenSession() {
  const { branch } = useBranch()
  const { can } = useAuth()
  return useQuery({ queryKey: ['session', branch?.id], enabled: !!branch && can('cash.session.open'),
    queryFn: async () => (await api<CashSession[]>(`/pos/sessions?branch_id=${branch!.id}`)).find((s) => s.status === 'open') ?? null })
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
  const session = useOpenSession()
  const [cat, setCat] = useState<number | 'all'>('all')
  const [q, setQ] = useState('')
  const [lines, setLines] = useState<CartLine[]>([])
  const [appointment, setAppointment] = useState<Appointment | null>(null)
  const [cq, setCq] = useState('')
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [beneficiary, setBeneficiary] = useState<number | null>(null)
  const [mode, setMode] = useState<Mode>('cash')
  const [tendered, setTendered] = useState('')
  const [split, setSplit] = useState({ cash: '', card: '' })
  const [ref, setRef] = useState('')
  const [paidNow, setPaidNow] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [receipt, setReceipt] = useState<Invoice | null>(null)
  const found = useQuery({ queryKey: ['customers', cq], enabled: cq.length >= 2 && !customer, queryFn: () => api<Customer[]>(`/customers?q=${encodeURIComponent(cq)}`) })

  // coming from the bookings board: the visit's services and staff are pre-filled
  useEffect(() => {
    const a = (loc.state as { appointment?: Appointment } | null)?.appointment
    if (!a) return
    setAppointment(a)
    setLines(a.items.map((i) => ({ key: crypto.randomUUID(), service_id: i.service_id, staff_id: i.staff_id, qty: 1, discount: '0' })))
    if (a.customer) api<Customer>(`/customers/${a.customer}`).then((c) => { setCustomer(c); setBeneficiary(a.beneficiary) }).catch(() => undefined)
    nav('.', { replace: true, state: null })
  }, [loc.state, nav])

  const svc = (id: number) => services.find((s) => s.id === id)
  const priceF = (id: number) => toFils(svc(id)?.current_price ?? '0')
  const totals = useMemo(() => {
    let sub = 0n, disc = 0n
    for (const l of lines) { sub += priceF(l.service_id) * BigInt(l.qty); disc += safeFils(l.discount) }
    return { sub, disc, total: sub - disc }
  }, [lines, services]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = branchServices.filter((s) => (cat === 'all' || s.category === cat) && (!q || nameOf(s, lang).toLowerCase().includes(q.toLowerCase())))
  const myCats = (cats.data ?? []).filter((c) => c.business_type === branch?.business_type)

  const add = (id: number) => {
    const ex = lines.find((l) => l.service_id === id && !appointment)
    if (ex) setLines(lines.map((l) => (l === ex ? { ...l, qty: l.qty + 1 } : l)))
    else setLines([...lines, { key: crypto.randomUUID(), service_id: id, staff_id: staffFor(id).length === 1 ? staffFor(id)[0].id : null, qty: 1, discount: '0' }])
  }
  const setLine = (k: string, p: Partial<CartLine>) => setLines(lines.map((l) => (l.key === k ? { ...l, ...p } : l)))
  const reset = () => { setLines([]); setAppointment(null); setCustomer(null); setBeneficiary(null); setCq(''); setTendered(''); setSplit({ cash: '', card: '' }); setRef(''); setPaidNow(''); setMode('cash'); setKey(crypto.randomUUID()) }

  const totalStr = fromFils(totals.total)
  const payments = (): { method: string; amount: string; reference?: string }[] => {
    if (mode === 'cash') return [{ method: 'cash', amount: totalStr }]
    if (mode === 'knet' || mode === 'transfer') return [{ method: mode, amount: totalStr, reference: ref }]
    if (mode === 'split') return [{ method: 'cash', amount: split.cash || '0' }, { method: 'knet', amount: split.card || '0', reference: ref }].filter((p) => safeFils(p.amount) > 0n)
    return paidNow && safeFils(paidNow) > 0n ? [{ method: 'cash', amount: paidNow }] : []
  }
  const splitOk = mode !== 'split' || safeFils(split.cash) + safeFils(split.card) === totals.total
  const change = mode === 'cash' && tendered ? safeFils(tendered) - totals.total : null
  const needsDrawer = (mode === 'cash' || mode === 'split' || (mode === 'credit' && safeFils(paidNow) > 0n)) && !session.data
  const { save, busy, error } = useSave<Invoice>([['appointments'], ['invoices'], ['session']], (inv) => { setReceipt(inv); toast(t('pos.done', { n: inv.number })); reset() })
  const checkout = () => save({ path: '/pos/checkout', idempotencyKey: key, body: {
    branch_id: branch!.id, appointment_id: appointment?.id ?? null, customer_id: customer?.id ?? null, beneficiary_id: beneficiary,
    expected_total: totalStr, payments: payments(),
    lines: lines.map((l) => ({ service_id: l.service_id, staff_id: l.staff_id, qty: l.qty, discount: l.discount || '0' })) } })

  if (!branch) return <p className="muted">{t('common.loading')}</p>
  const staffName = (id: number) => { const p = staff.find((x) => x.id === id); return p ? (lang === 'en' && p.full_name_en ? p.full_name_en : p.full_name_ar) : '' }
  return (
    <>
      <Head title={t('nav.pos')} sub={`${nameOf(branch, lang)} · ${new Date().toLocaleDateString(lang === 'ar' ? 'ar-KW' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}`}>
        <input className="input" placeholder={t('pos.search')} style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />
      </Head>
      {can('cash.session.open') && session.data === null && <div className="notice"><Icon name="alert" />{t('pos.noDrawer')} <Link to="/cash" style={{ color: 'inherit', fontWeight: 700 }}>{t('pos.openDrawer')}</Link></div>}
      <div className="pos">
        <div>
          <div className="seg cats">
            <button className={cat === 'all' ? 'on' : ''} onClick={() => setCat('all')}>{t('pos.all')}</button>
            {myCats.map((c) => <button key={c.id} className={cat === c.id ? 'on' : ''} onClick={() => setCat(c.id)}>{nameOf(c, lang)}</button>)}
          </div>
          <div className="grid items">
            {shown.map((s) => <button key={s.id} className="item" disabled={!s.current_price} onClick={() => add(s.id)}>
              <span className="ic"><Icon name="sparkle" /></span><b>{nameOf(s, lang)}</b>
              <span className="cap muted"><bdi>{s.duration_minutes}</bdi> {t('svc.min')}</span>
              <span className="money">{s.current_price ? formatKWD(s.current_price, lang) : t('svc.noPrice')}</span></button>)}
            {shown.length === 0 && <div className="empty">{t('pos.noItems')}</div>}
          </div>
        </div>

        <div className="card cart">
          <div className="row sb"><h2>{t('pos.invoice')}</h2><button className="btn ghost sm danger" onClick={reset}>{t('pos.clear')}</button></div>
          {appointment && <div className="notice info"><Icon name="calendar" />{t('pos.fromBooking', { name: appointment.beneficiary_name || appointment.customer_name })}</div>}
          {customer ? <div className="li"><span className="av">{customer.full_name[0]}</span><div className="grow"><b>{customer.full_name}</b> <bdi className="cap muted">+{customer.phone}</bdi></div>
            {!appointment && <button className="btn sm ghost" onClick={() => { setCustomer(null); setBeneficiary(null) }}><Icon name="close" /></button>}</div>
            : <>
              <input className="input" placeholder={t('pos.customer')} value={cq} onChange={(e) => setCq(e.target.value)} />
              {found.data && found.data.length > 0 && <div className="list">{found.data.slice(0, 4).map((c) => <button key={c.id} className="li btn ghost" style={{ justifyContent: 'flex-start' }}
                onClick={() => { setCustomer(c); setBeneficiary(c.beneficiaries.find((b) => b.relation !== 'self')?.id ?? c.beneficiaries[0]?.id ?? null) }}>
                <b>{c.full_name}</b> <bdi className="cap muted">+{c.phone}</bdi></button>)}</div>}
            </>}
          {customer && customer.beneficiaries.length > 1 && <select className="input" value={beneficiary ?? ''} onChange={(e) => setBeneficiary(Number(e.target.value))}>
            {customer.beneficiaries.map((b) => <option key={b.id} value={b.id}>{b.full_name}</option>)}</select>}

          <div className="lines">
            {lines.map((l) => { const s = svc(l.service_id); return <div className="line" key={l.key}>
              <b className="small">{s ? nameOf(s, lang) : '…'}</b>
              <span className="money small">{formatKWD(fromFils(priceF(l.service_id) * BigInt(l.qty) - safeFils(l.discount)), lang)}</span>
              <select className="input" style={{ padding: '4px 8px', fontSize: 13 }} value={l.staff_id ?? ''} onChange={(e) => setLine(l.key, { staff_id: Number(e.target.value) || null })}>
                <option value="">{t('pos.staff')}</option>
                {staffFor(l.service_id).map((p) => <option key={p.id} value={p.id}>{staffName(p.id)}</option>)}</select>
              <div className="qty">
                <button onClick={() => l.qty > 1 ? setLine(l.key, { qty: l.qty - 1 }) : setLines(lines.filter((x) => x.key !== l.key))} aria-label="-">−</button>
                <bdi>{l.qty}</bdi><button onClick={() => setLine(l.key, { qty: l.qty + 1 })} aria-label="+">+</button>
              </div>
              {(can('pos.discount.line') || can('pos.discount.override')) && <label className="cap muted row" style={{ gridColumn: '1 / -1', gap: 6 }}>{t('pos.discount')}
                <input className="input" dir="ltr" inputMode="decimal" style={{ width: 90, padding: '3px 8px' }} value={l.discount} onChange={(e) => setLine(l.key, { discount: e.target.value })} /></label>}
            </div> })}
            {lines.length === 0 && <div className="empty small">{t('pos.empty')}</div>}
          </div>

          <div className="tot"><span className="muted">{t('pos.subtotal')}</span><span className="money">{formatKWD(fromFils(totals.sub), lang)}</span></div>
          <div className="tot"><span className="muted">{t('pos.discount')}</span><span className="money">{formatKWD(fromFils(totals.disc), lang)}</span></div>
          <div className="tot big"><span>{t('pos.total')}</span><span className="money">{formatKWD(totalStr, lang)}</span></div>

          <div className="pay">
            {(['cash', 'knet', 'transfer', 'split'] as const).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`pos.m.${m}`)}</button>)}
            {can('pos.credit_sale') && <button className={mode === 'credit' ? 'on' : ''} onClick={() => setMode('credit')}>{t('pos.m.credit')}</button>}
          </div>
          {mode === 'cash' && <>
            <label className="field">{t('pos.tendered')}<input className="input" dir="ltr" inputMode="decimal" value={tendered} onChange={(e) => setTendered(e.target.value)} /></label>
            {change !== null && <div className="tot"><span className="muted">{t('pos.change')}</span><b className="money">{change >= 0n ? formatKWD(fromFils(change), lang) : '—'}</b></div>}
          </>}
          {mode === 'split' && <div className="two">
            <label className="field">{t('pos.m.cash')}<input className="input" dir="ltr" inputMode="decimal" value={split.cash} onChange={(e) => setSplit({ ...split, cash: e.target.value })} /></label>
            <label className="field">{t('pos.m.knet')}<input className="input" dir="ltr" inputMode="decimal" value={split.card} onChange={(e) => setSplit({ ...split, card: e.target.value })} /></label>
          </div>}
          {(mode === 'knet' || mode === 'transfer' || (mode === 'split' && safeFils(split.card) > 0n)) &&
            <label className="field">{t(mode === 'transfer' ? 'pos.transferRef' : 'pos.knetRef')}<input className="input" dir="ltr" value={ref} onChange={(e) => setRef(e.target.value)} /></label>}
          {mode === 'credit' && <>
            <div className="small muted">{t('pos.creditHelp')}</div>
            <label className="field">{t('pos.paidNow')}<input className="input" dir="ltr" inputMode="decimal" value={paidNow} onChange={(e) => setPaidNow(e.target.value)} /></label>
          </>}
          {!splitOk && <div className="notice bad">{t('pos.splitMismatch')}</div>}
          {needsDrawer && <div className="notice">{t('pos.noDrawer')}</div>}
          <ErrorText error={error} />
          <button className="btn brand lg" disabled={!lines.length || busy || !splitOk || needsDrawer || lines.some((l) => !svc(l.service_id)?.current_price)}
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
