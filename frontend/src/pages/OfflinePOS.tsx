import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { Head, Icon, nameOf } from '../components/ui'
import { formatKWD, fromFils, toFils } from '../money'
import { applyToBundle, getBundle, recordSale, totals, type Bundle, type OLine } from '../offline/engine'
import { useOffline } from '../offline/OfflineProvider'

const safeFils = (v: string) => { try { return v.trim() ? toFils(v) : 0n } catch { return -1n } }

/** The till without internet (D-013): sells from the saved snapshot; every receipt is numbered, signed and kept
 *  in this browser until the server has it. Credit sales and new customers need the connection. */
export default function OfflinePOS() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { membership, can } = useAuth()
  const { branch } = useBranch()
  const { device, refresh, pendingCount } = useOffline()
  const [b, setB] = useState<Bundle | null | undefined>(undefined)
  const [tab, setTab] = useState<'service' | 'product' | 'package'>('service')
  const [lines, setLines] = useState<OLine[]>([])
  const [cq, setCq] = useState('')
  const [custId, setCustId] = useState<number | null>(null)
  const [benId, setBenId] = useState<number | null>(null)
  const [coupon, setCoupon] = useState('')
  const [points, setPoints] = useState('')
  const [tip, setTip] = useState('')
  const [tipStaff, setTipStaff] = useState<number | null>(null)
  const [mode, setMode] = useState<'cash' | 'knet'>('cash')
  const [ref, setRef] = useState('')
  const [tendered, setTendered] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { if (membership && branch) getBundle(membership.tenant_id, branch.id).then((x) => setB(x ?? null)) }, [membership, branch])
  const customer = b?.customers.find((c) => c.id === custId) ?? null
  const found = useMemo(() => (cq.trim().length < 2 || !b ? [] : b.customers.filter((c) => c.full_name.includes(cq.trim()) || c.phone.includes(cq.trim())).slice(0, 5)), [cq, b])
  if (!branch || !membership) return <p className="muted">{t('common.loading')}</p>
  if (b === undefined) return <p className="muted">{t('common.loading')}</p>
  if (!device || !b) return <div className="notice bad"><Icon name="alert" />{t('off.notReady')}</div>
  const tot = totals(lines, b, coupon, Number(points || 0), customer?.points ?? 0)
  const tipF = safeFils(tip)
  const due = tot.total + (tipF > 0n ? tipF : 0n)
  const change = mode === 'cash' && tendered ? safeFils(tendered) - due : null
  const name = (x: { name_ar: string; name_en: string }) => nameOf(x, lang)
  const add = (kind: OLine['kind'], id: number, nm: string, price: string) => {
    const same = lines.find((l) => l.kind === kind && l.id === id && !l.redeem_package_id && kind !== 'package')
    if (same) setLines(lines.map((l) => (l === same ? { ...l, qty: l.qty + 1 } : l)))
    else setLines([...lines, { key: crypto.randomUUID(), kind, id, name: nm, unit_price: price, qty: 1, discount: '0', staff_id: null, redeem_package_id: null }])
  }
  const set = (key: string, p: Partial<OLine>) => setLines(lines.map((l) => (l.key === key ? { ...l, ...p } : l)))
  const pkgFor = (serviceId: number) => (customer?.packages ?? []).filter((p) => p.service_id === serviceId)
  const maxDisc = Number(b.discount_limit_percent)
  const overLimit = lines.some((l) => !l.redeem_package_id && safeFils(l.discount) * 100n > toFils(l.unit_price) * BigInt(l.qty) * BigInt(Math.round(maxDisc)))
  const problems = [...tot.problems, ...(overLimit && !can('pos.discount.override') ? ['discount_over_limit'] : []),
    ...(tipF > 0n && !tipStaff ? ['tip_needs_staff'] : []), ...(lines.some((l) => l.kind === 'package') && !customer ? ['package_needs_customer'] : []),
    ...(mode === 'knet' && !ref.trim() ? ['payment_reference_required'] : []), ...(change !== null && change < 0n ? ['tendered_short'] : [])]
  const reset = () => { setLines([]); setCustId(null); setBenId(null); setCoupon(''); setPoints(''); setTip(''); setTipStaff(null); setRef(''); setTendered(''); setErr('') }
  const sell = async () => {
    setBusy(true); setErr('')
    try {
      const printed = { lines: lines.map((l) => ({ name: l.name, qty: l.qty, price: l.unit_price })), total: fromFils(tot.total), tip: fromFils(tipF > 0n ? tipF : 0n),
        discount: fromFils(tot.manual + tot.coupon + tot.pointsDisc), customer: customer?.full_name ?? '', method: mode, at: new Date().toISOString() }
      const sale = await recordSale(device, {
        lines, payments: [{ method: mode, amount: fromFils(due), reference: mode === 'knet' ? ref.trim() : '' }], customer_id: custId, beneficiary_id: benId,
        coupon_code: coupon.trim().toUpperCase(), redeem_points: tot.points, tip: tipF > 0n ? fromFils(tipF) : '0', tip_staff_id: tipF > 0n ? tipStaff : null,
      }, tot, printed)
      await applyToBundle(membership!.tenant_id, branch!.id, lines, coupon.trim(), tot.points, custId)
      setB(await getBundle(membership!.tenant_id, branch!.id))
      setDone(sale.printed); reset(); refresh()
    } catch { setErr(t('off.saveFailed')) } finally { setBusy(false) }
  }
  if (done) return (
    <div className="card" style={{ maxWidth: 420, margin: '0 auto' }}>
      <div id="receipt">
        <div className="rc"><b>{membership.tenant_name}</b><div>{name(branch)}</div><div className="cap">{String(done.ref)} · {new Date(String(done.at)).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { timeZone: 'Asia/Kuwait' })}</div></div>
        <div className="notice" style={{ margin: '8px 0' }}>{t('off.provisional')}</div>
        {(done.lines as { name: string; qty: number; price: string }[]).map((l, i) => <div className="r" key={i}><span>{l.qty > 1 && <bdi>{l.qty}× </bdi>}{l.name}</span><span className="money">{formatKWD(fromFils(toFils(l.price) * BigInt(l.qty)), lang)}</span></div>)}
        <hr />
        {String(done.discount) !== '0.000' && <div className="r"><span>{t('pos.discount')}</span><span className="money">-{formatKWD(String(done.discount), lang)}</span></div>}
        <div className="r"><b>{t('pos.total')}</b><b className="money">{formatKWD(String(done.total), lang)}</b></div>
        {String(done.tip) !== '0.000' && <div className="r"><span>{t('pos.tip')}</span><span className="money">{formatKWD(String(done.tip), lang)}</span></div>}
        <div className="r"><span>{t(`pos.m.${String(done.method)}`)}</span><span /></div>
        <hr /><div className="rc cap">{t('inv.thanks')}</div>
      </div>
      <div className="row" style={{ marginTop: 12 }}><button className="btn" onClick={() => window.print()}><Icon name="printer" />{t('inv.print')}</button>
        <button className="btn brand" onClick={() => setDone(null)}>{t('off.next')}</button></div>
    </div>
  )
  const age = Math.round((Date.now() - new Date(b.generated_at).getTime()) / 60000)
  return (
    <>
      <Head title={t('nav.pos')} sub={`${name(branch)} · ${t('off.mode')}`} />
      <div className="notice bad"><Icon name="alert" />{t('off.banner', { n: pendingCount, age: age < 60 ? t('off.minutes', { n: age }) : t('off.hours', { n: Math.round(age / 60) }) })}</div>
      <div className="pos">
        <div>
          <div className="tabs">{(['service', 'product', 'package'] as const).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`pos.tab.${x}`)}</button>)}</div>
          <div className="grid items">
            {tab === 'service' && b.services.map((s) => <button key={s.id} className="item" onClick={() => add('service', s.id, name(s), s.price)}>
              <span className="ic"><Icon name="sparkle" /></span><b>{name(s)}</b><span className="money">{formatKWD(s.price, lang)}</span></button>)}
            {tab === 'product' && b.products.map((p) => { const q = Number(p.qty); return <button key={p.id} className="item" disabled={q <= 0} onClick={() => add('product', p.id, name(p), p.price)}>
              <span className="ic"><Icon name="box" /></span><b>{name(p)}</b><span className={`stk pill ${q > 5 ? 'mute' : q > 0 ? 'warn' : 'bad'}`}><bdi>{q}</bdi></span>
              <span className="money">{formatKWD(p.price, lang)}</span></button> })}
            {tab === 'package' && b.plans.map((p) => <button key={p.id} className="item" onClick={() => add('package', p.id, name(p), p.price)}>
              <span className="ic"><Icon name="layers" /></span><b>{name(p)}</b><span className="cap muted">{t('pkg.sessions', { n: p.sessions })}</span>
              <span className="money">{formatKWD(p.price, lang)}</span></button>)}
          </div>
        </div>
        <div className="card cart">
          <div className="row sb"><h2>{t('pos.invoice')}</h2><button className="btn ghost sm danger" onClick={reset}>{t('pos.clear')}</button></div>
          {customer ? <div className="li"><span className="av">{customer.full_name[0]}</span><div className="grow"><b>{customer.full_name}</b> <bdi className="cap muted">+{customer.phone}</bdi>
            <div className="cap muted">⭐ <bdi>{customer.points}</bdi> {t('pos.pointsUnit')} · {t('off.asOfSnapshot')}</div></div>
            <button className="btn sm ghost" onClick={() => { setCustId(null); setBenId(null); setPoints(''); setLines(lines.map((l) => ({ ...l, redeem_package_id: null }))) }}><Icon name="close" /></button></div>
            : <>
              <input className="input" placeholder={t('pos.customer')} value={cq} onChange={(e) => setCq(e.target.value)} />
              {found.length > 0 && <div className="list">{found.map((c) => <button key={c.id} className="li btn ghost" style={{ justifyContent: 'flex-start' }}
                onClick={() => { setCustId(c.id); setBenId(c.beneficiaries[0]?.id ?? null); setCq('') }}><b>{c.full_name}</b> <bdi className="cap muted">+{c.phone}</bdi></button>)}</div>}
              <div className="cap muted">{t('off.noNewCustomers')}</div>
            </>}
          {customer && customer.beneficiaries.length > 1 && <select className="input" value={benId ?? ''} onChange={(e) => setBenId(Number(e.target.value))}>
            {customer.beneficiaries.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}</select>}
          <div className="lines">
            {lines.map((l) => <div className="line" key={l.key}>
              <b className="small">{l.name}</b>
              <span className="money small">{formatKWD(fromFils(toFils(l.unit_price) * BigInt(l.qty) - (l.redeem_package_id ? toFils(l.unit_price) * BigInt(l.qty) : safeFils(l.discount) > 0n ? safeFils(l.discount) : 0n)), lang)}</span>
              {l.kind === 'service' ? <select className="input" style={{ padding: '4px 8px', fontSize: 13 }} value={l.staff_id ?? ''} onChange={(e) => set(l.key, { staff_id: Number(e.target.value) || null })}>
                <option value="">{t('pos.staff')}</option>{b.staff.map((p) => <option key={p.id} value={p.id}>{name(p)}</option>)}</select> : <span />}
              <div className="qty">
                <button onClick={() => (l.qty > 1 ? set(l.key, { qty: l.qty - 1 }) : setLines(lines.filter((x) => x.key !== l.key)))} aria-label="-">−</button>
                <bdi>{l.qty}</bdi><button disabled={l.kind === 'package'} onClick={() => set(l.key, { qty: l.qty + 1 })} aria-label="+">+</button>
              </div>
              {l.kind === 'service' && pkgFor(l.id).length > 0 && <label className="cap row" style={{ gridColumn: '1 / -1', gap: 6 }}>
                <input type="checkbox" checked={!!l.redeem_package_id} onChange={(e) => {
                  const p = pkgFor(l.id)[0]
                  set(l.key, e.target.checked ? { redeem_package_id: p.id, unit_price: p.session_value, discount: '0', qty: 1 } : { redeem_package_id: null, unit_price: b.services.find((s) => s.id === l.id)?.price ?? l.unit_price })
                }} />{t('pos.usePackage', { left: pkgFor(l.id)[0].sessions_left })}</label>}
              {!l.redeem_package_id && (can('pos.discount.line') || can('pos.discount.override')) && <label className="cap muted row" style={{ gridColumn: '1 / -1', gap: 6 }}>{t('pos.discount')}
                <input className="input" dir="ltr" inputMode="decimal" style={{ width: 90, padding: '3px 8px' }} value={l.discount} onChange={(e) => set(l.key, { discount: e.target.value })} /></label>}
            </div>)}
            {lines.length === 0 && <div className="empty small">{t('pos.empty')}</div>}
          </div>
          <div className="two">
            <input className="input" dir="ltr" placeholder={t('pos.coupon')} style={{ textTransform: 'uppercase' }} value={coupon} onChange={(e) => setCoupon(e.target.value)} />
            {customer && customer.points > 0 ? <input className="input" dir="ltr" inputMode="numeric" placeholder={t('pos.redeemPoints', { n: customer.points })} value={points} onChange={(e) => setPoints(e.target.value.replace(/\D/g, ''))} /> : <span />}
          </div>
          <div className="tot"><span className="muted">{t('pos.subtotal')}</span><span className="money">{formatKWD(fromFils(tot.subtotal), lang)}</span></div>
          <div className="tot"><span className="muted">{t('pos.discount')}{tot.coupon > 0n && ` (${t('pos.couponApplied')})`}{tot.points > 0 && ` (⭐ ${tot.points})`}</span><span className="money">{formatKWD(fromFils(tot.manual + tot.coupon + tot.pointsDisc), lang)}</span></div>
          <div className="two">
            <label className="field">{t('pos.tip')}<input className="input" dir="ltr" inputMode="decimal" placeholder="0.000" value={tip} onChange={(e) => setTip(e.target.value)} /></label>
            {tipF > 0n ? <label className="field">{t('pos.tipFor')}<select className="input" value={tipStaff ?? ''} onChange={(e) => setTipStaff(Number(e.target.value) || null)}>
              <option value="">—</option>{b.staff.map((p) => <option key={p.id} value={p.id}>{name(p)}</option>)}</select></label> : <span />}
          </div>
          <div className="tot big"><span>{t('pos.total')}</span><span className="money">{formatKWD(fromFils(due), lang)}</span></div>
          <div className="pay">{(['cash', 'knet'] as const).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`pos.m.${m}`)}</button>)}</div>
          {mode === 'cash' ? <>
            <label className="field">{t('pos.tendered')}<input className="input" dir="ltr" inputMode="decimal" value={tendered} onChange={(e) => setTendered(e.target.value)} /></label>
            {change !== null && change >= 0n && <div className="tot"><span className="muted">{t('pos.change')}</span><b className="money">{formatKWD(fromFils(change), lang)}</b></div>}
          </> : <label className="field">{t('pos.knetRef')}<input className="input" dir="ltr" value={ref} onChange={(e) => setRef(e.target.value)} /></label>}
          {problems.map((p) => <div className="notice bad" key={p}>{t(`errors.${p}`)}</div>)}
          {err && <div className="notice bad">{err}</div>}
          <button className="btn brand lg" disabled={!lines.length || busy || problems.length > 0 || tot.total < 0n} onClick={sell}>{busy ? t('common.loading') : t('off.sell')}</button>
          <div className="cap muted">{t('off.noCredit')}</div>
        </div>
      </div>
    </>
  )
}
