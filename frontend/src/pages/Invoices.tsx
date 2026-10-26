import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { api, type Invoice } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD, fromFils } from '../money'
import { safeFils } from './POS'

const todayISO = () => new Date(Date.now() - 4 * 3600e3).toISOString().slice(0, 10)
const dt = (iso: string, lang: string) => new Date(iso).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })

/** Printable receipt (72 mm), using the design's #receipt / #printArea styles. */
export function Receipt({ invoice: inv, onClose }: { invoice: Invoice; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { membership } = useAuth()
  const { branch } = useBranch()
  const [printing, setPrinting] = useState(false)
  useEffect(() => {
    if (!printing) return
    const done = () => setPrinting(false)
    window.addEventListener('afterprint', done, { once: true })
    window.print()
    return () => window.removeEventListener('afterprint', done)
  }, [printing])
  const body = (
    <div id="receipt">
      <div className="rc"><b>{membership?.tenant_name}</b><div>{branch ? nameOf(branch, lang) : ''}</div><div className="cap">{inv.number} · {dt(inv.issued_at, lang)}</div></div>
      <hr />
      {inv.lines.map((l) => <div className="r" key={l.id}><span>{l.qty > 1 && <bdi>{l.qty}× </bdi>}{nameOf({ name_ar: l.name_ar, name_en: l.name_en }, lang)}</span><span className="money">{formatKWD(l.line_total, lang)}</span></div>)}
      <hr />
      {inv.discount_total !== '0.000' && <div className="r"><span>{t('pos.discount')}</span><span className="money">-{formatKWD(inv.discount_total, lang)}</span></div>}
      {inv.points_redeemed > 0 && <div className="r cap muted"><span>{t('inv.pointsUsed')}</span><span><bdi>{inv.points_redeemed}</bdi> {t('pos.pointsUnit')}</span></div>}
      <div className="r"><b>{t('pos.total')}</b><b className="money">{formatKWD(inv.total, lang)}</b></div>
      {inv.tip !== '0.000' && <div className="r"><span>{t('pos.tip')}</span><span className="money">{formatKWD(inv.tip, lang)}</span></div>}
      {inv.payments.map((p) => <div className="r" key={p.id}><span>{p.direction === 'out' ? t('inv.refund') + ' · ' : ''}{t(`pos.m.${p.method}`)}{p.reference && ` (${p.reference})`}</span><span className="money">{formatKWD(p.amount, lang)}</span></div>)}
      {inv.state.balance !== '0.000' && <div className="r"><b>{t('inv.balance')}</b><b className="money">{formatKWD(inv.state.balance, lang)}</b></div>}
      <hr /><div className="rc cap">{inv.beneficiary_name || inv.customer_name}{inv.customer_phone && <> · <bdi>+{inv.customer_phone}</bdi></>}</div>
      <div className="rc cap">{t('inv.thanks')}</div>
    </div>
  )
  return (
    <>
      <Dialog open title={t('inv.receipt')} onClose={onClose}>
        {body}
        <div className="row">
          <button type="button" className="btn primary" onClick={() => setPrinting(true)}><Icon name="printer" />{t('inv.print')}</button>
          {inv.customer_phone && <a className="btn" target="_blank" rel="noreferrer"
            href={`https://wa.me/${inv.customer_phone}?text=${encodeURIComponent(t('inv.waText', { n: inv.number, total: formatKWD(inv.total, lang) }))}`}><Icon name="whatsapp" />{t('inv.sendWa')}</a>}
        </div>
      </Dialog>
      <div id="printArea" hidden={!printing}>{body}</div>
    </>
  )
}

function InvoiceDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const q = useQuery({ queryKey: ['invoice', id], queryFn: () => api<Invoice>(`/pos/invoices/${id}`) })
  const [mode, setMode] = useState<'view' | 'collect' | 'return' | 'receipt'>('view')
  const [pay, setPay] = useState({ method: 'cash', amount: '', reference: '' })
  const [ret, setRet] = useState<Record<number, string>>({})
  const [restock, setRestock] = useState<Record<number, string>>({})
  const [reason, setReason] = useState('')
  const [refund, setRefund] = useState({ method: 'cash', amount: '', reference: '' })
  const [key, setKey] = useState(() => crypto.randomUUID())
  const done = () => { toast(t('common.saved')); setMode('view'); setKey(crypto.randomUUID()) }
  const collect = useSave<Invoice>([['invoice', id], ['invoices'], ['session']], done)
  const credit = useSave<Invoice>([['invoice', id], ['invoices'], ['session']], done)
  const inv = q.data
  if (!inv) return <Dialog open title={t('common.loading')} onClose={onClose}><ErrorText error={q.error} /></Dialog>
  if (mode === 'receipt') return <Receipt invoice={inv} onClose={() => setMode('view')} />
  const retTotal = Object.values(ret).reduce((a, v) => a + safeFils(v), 0n)
  const submit = mode === 'collect'
    ? () => collect.save({ path: `/pos/invoices/${id}/payments`, idempotencyKey: key, body: { payments: [pay] } })
    : mode === 'return'
      ? () => credit.save({ path: `/pos/invoices/${id}/credit-notes`, idempotencyKey: key, body: {
        reason, lines: Object.entries(ret).filter(([, v]) => safeFils(v) > 0n).map(([lid, amount]) => ({ invoice_line_id: Number(lid), amount, restock_qty: Number(restock[Number(lid)] || 0) })),
        refund: safeFils(refund.amount) > 0n ? refund : null } })
      : undefined
  return (
    <Dialog open wide title={inv.number} onClose={onClose} onSubmit={submit} busy={collect.busy || credit.busy}
      submitLabel={mode === 'collect' ? t('inv.collect') : t('inv.issueReturn')}>
      <div className="row sb">
        <div className="small muted">{dt(inv.issued_at, lang)} · {inv.issued_by_name}{(inv.beneficiary_name || inv.customer_name) && ` · ${inv.beneficiary_name || inv.customer_name}`}</div>
        <div className="row">{inv.is_credit && <span className="pill warn">{t('inv.credit')}</span>}
          {inv.state.balance === '0.000' ? <span className="pill good">{t('inv.paid')}</span> : <span className="pill bad">{t('inv.balance')}: {formatKWD(inv.state.balance, lang)}</span>}</div>
      </div>
      <div className="tw"><table><thead><tr><th>{t('svc.service')}</th><th>{t('pos.qty')}</th><th className="n">{t('svc.price')}</th><th className="n">{t('pos.discount')}</th><th className="n">{t('pos.total')}</th>
        {mode === 'return' && <th className="n">{t('inv.returnAmount')}</th>}</tr></thead>
        <tbody>{inv.lines.map((l) => { const left = fromFils(safeFils(l.line_total) - safeFils(l.returned)); return <tr key={l.id}>
          <td>{nameOf({ name_ar: l.name_ar, name_en: l.name_en }, lang)}{l.returned !== '0' && l.returned !== '0.000' && <> <span className="pill warn">{t('inv.returned')} {formatKWD(l.returned, lang)}</span></>}</td>
          <td><bdi>{l.qty}</bdi></td><td className="n money">{formatKWD(l.unit_price, lang)}</td><td className="n money">{formatKWD(l.discount, lang)}</td><td className="n money">{formatKWD(l.line_total, lang)}</td>
          {mode === 'return' && <td className="n"><input className="input" dir="ltr" inputMode="decimal" placeholder={left} style={{ width: 100 }} value={ret[l.id] ?? ''} onChange={(e) => setRet({ ...ret, [l.id]: e.target.value })} />
            {l.kind === 'product' && <label className="cap muted" style={{ display: 'block' }}>{t('inv.restock')} <input className="input" type="number" min={0} max={l.qty} style={{ width: 64 }} value={restock[l.id] ?? ''} onChange={(e) => setRestock({ ...restock, [l.id]: e.target.value })} /></label>}</td>}
        </tr> })}</tbody></table></div>
      <div className="list">
        {inv.payments.map((p) => <div className="li" key={p.id}><Icon name={p.direction === 'in' ? 'wallet' : 'undo'} /><div className="grow small">{p.direction === 'out' && `${t('inv.refund')} · `}{t(`pos.m.${p.method}`)}{p.reference && <> · <span className="code">{p.reference}</span></>}<div className="cap muted">{dt(p.received_at, lang)}</div></div><b className="money">{p.direction === 'out' ? '-' : ''}{formatKWD(p.amount, lang)}</b></div>)}
        {inv.credit_notes.map((c) => <div className="li" key={c.id}><Icon name="file" /><div className="grow small">{c.number} · {c.reason}</div><b className="money">-{formatKWD(c.total, lang)}</b></div>)}
      </div>
      {mode === 'view' && <div className="row">
        <button type="button" className="btn" onClick={() => setMode('receipt')}><Icon name="printer" />{t('inv.receipt')}</button>
        {can('pos.sell') && inv.state.balance !== '0.000' && <button type="button" className="btn primary" onClick={() => { setPay({ method: 'cash', amount: inv.state.balance, reference: '' }); setMode('collect') }}>{t('inv.collect')}</button>}
        {can('pos.return') && <button type="button" className="btn danger" onClick={() => setMode('return')}><Icon name="undo" />{t('inv.return')}</button>}
      </div>}
      {mode === 'collect' && <div className="two">
        <label className="field">{t('inv.method')}<select className="input" value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>
          {(['cash', 'knet', 'transfer'] as const).map((m) => <option key={m} value={m}>{t(`pos.m.${m}`)}</option>)}</select></label>
        <label className="field">{t('inv.amount')}<input className="input" dir="ltr" inputMode="decimal" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} required /></label>
        {pay.method !== 'cash' && <label className="field">{t('pos.knetRef')}<input className="input" dir="ltr" value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} required /></label>}
      </div>}
      {mode === 'return' && <>
        <div className="tot"><span className="muted">{t('inv.returnTotal')}</span><b className="money">{formatKWD(fromFils(retTotal), lang)}</b></div>
        <label className="field">{t('book.reason')}<input className="input" value={reason} onChange={(e) => setReason(e.target.value)} required /></label>
        <div className="two">
          <label className="field">{t('inv.refundMethod')}<select className="input" value={refund.method} onChange={(e) => setRefund({ ...refund, method: e.target.value })}>
            {(['cash', 'knet', 'transfer'] as const).map((m) => <option key={m} value={m}>{t(`pos.m.${m}`)}</option>)}</select></label>
          <label className="field">{t('inv.refundAmount')}<input className="input" dir="ltr" inputMode="decimal" placeholder="0.000" value={refund.amount} onChange={(e) => setRefund({ ...refund, amount: e.target.value })} /></label>
        </div>
        {refund.method !== 'cash' && safeFils(refund.amount) > 0n && <label className="field">{t('pos.knetRef')}<input className="input" dir="ltr" value={refund.reference} onChange={(e) => setRefund({ ...refund, reference: e.target.value })} required /></label>}
        <div className="small muted">{t('inv.returnHelp')}</div>
      </>}
      <ErrorText error={collect.error || credit.error} />
      {mode !== 'view' && <button type="button" className="btn ghost sm" onClick={() => setMode('view')}>{t('common.back')}</button>}
    </Dialog>
  )
}

export default function Invoices() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { branch } = useBranch()
  const [params, setParams] = useSearchParams()
  const [date, setDate] = useState(todayISO())
  const [q, setQ] = useState('')
  const [unpaid, setUnpaid] = useState(false)
  const openId = Number(params.get('open')) || null
  const list = useQuery({ queryKey: ['invoices', branch?.id, date, q, unpaid], enabled: !!branch,
    queryFn: () => api<Invoice[]>(`/pos/invoices?branch_id=${branch!.id}&date=${date}&q=${encodeURIComponent(q)}${unpaid ? '&unpaid=true' : ''}`) })
  const rows = list.data ?? []
  const sum = rows.reduce((a, r) => a + safeFils(r.total), 0n)
  return (
    <>
      <Head title={t('nav.invoices')} sub={t('inv.sub')}>
        <input className="input" placeholder={t('inv.search')} style={{ width: 200 }} value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="row small"><input type="checkbox" checked={unpaid} onChange={(e) => setUnpaid(e.target.checked)} />{t('inv.unpaidOnly')}</label>
        {!q && !unpaid && <input type="date" className="input" style={{ width: 'auto' }} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Head>
      <ErrorText error={list.error} />
      <div className="tw"><table><thead><tr><th>{t('inv.number')}</th><th>{t('inv.time')}</th><th>{t('cust.name')}</th><th>{t('inv.items')}</th><th>{t('inv.payment')}</th><th className="n">{t('pos.total')}</th><th>{t('org.status')}</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id} className="click" onClick={() => setParams({ open: String(r.id) })}>
          <td className="num">{r.number}</td><td className="num">{dt(r.issued_at, lang)}</td><td>{r.beneficiary_name || r.customer_name || '—'}</td>
          <td className="small">{r.lines.map((l) => nameOf({ name_ar: l.name_ar, name_en: l.name_en }, lang)).join('، ')}</td>
          <td className="small">{[...new Set(r.payments.filter((p) => p.direction === 'in').map((p) => t(`pos.m.${p.method}`)))].join(' + ') || '—'}</td>
          <td className="n money">{formatKWD(r.total, lang)}</td>
          <td>{r.credit_notes.length > 0 && <span className="pill warn">{t('inv.returned')}</span>}{' '}
            {r.state.balance === '0.000' ? <span className="pill good">{t('inv.paid')}</span> : <span className="pill bad">{t('inv.due')}</span>}</td></tr>)}
          {rows.length === 0 && <tr><td colSpan={7} className="empty">{list.isPending ? t('common.loading') : t('common.empty')}</td></tr>}</tbody>
        {rows.length > 0 && <tfoot><tr><th colSpan={5}>{t('inv.count', { n: rows.length })}</th><th className="n money">{formatKWD(fromFils(sum), lang)}</th><th /></tr></tfoot>}
      </table></div>
      {openId && <InvoiceDialog id={openId} onClose={() => setParams({})} />}
    </>
  )
}
