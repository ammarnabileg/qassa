import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Product, type Receipt, type Supplier } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'
import { formatKWD } from '../money'

type Tab = 'products' | 'receipts' | 'suppliers' | 'moves'
type PForm = { id?: number; sku: string; name_ar: string; name_en: string; kind: 'retail' | 'supply'; unit: string; sale_price: string; is_active: boolean }
type Move = { id: number; product: string; kind: string; qty: string; reason: string; ref: string; created_at: string; value?: string }

export default function Inventory() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const { branch } = useBranch()
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('products')
  const products = useQuery({ queryKey: ['products', branch?.id], enabled: !!branch, queryFn: () => api<Product[]>(`/inventory/products?branch_id=${branch!.id}`) })
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: () => api<Supplier[]>('/inventory/suppliers') })
  const receipts = useQuery({ queryKey: ['receipts'], enabled: tab === 'receipts', queryFn: () => api<Receipt[]>('/inventory/receipts') })
  const moves = useQuery({ queryKey: ['moves', branch?.id], enabled: tab === 'moves' && !!branch, queryFn: () => api<Move[]>(`/inventory/moves?branch_id=${branch!.id}`) })
  const [pForm, setPForm] = useState<PForm | null>(null)
  const [adj, setAdj] = useState<{ product: Product; qty: string; reason: string } | null>(null)
  const [grn, setGrn] = useState<{ supplier_id: string; notes: string; lines: { product_id: string; qty: string; unit_cost: string }[] } | null>(null)
  const [grnKey, setGrnKey] = useState(() => crypto.randomUUID())
  const [bill, setBill] = useState<{ receipt: Receipt; supplier_ref: string; amount: string; due_date: string } | null>(null)
  const [pay, setPay] = useState<{ receipt: Receipt; amount: string; reference: string } | null>(null)
  const [sup, setSup] = useState<{ name: string; phone: string } | null>(null)
  const done = () => { toast(t('common.saved')); setPForm(null); setAdj(null); setGrn(null); setBill(null); setPay(null); setSup(null); setGrnKey(crypto.randomUUID()) }
  const pSave = useSave<Product>([['products']], done)
  const aSave = useSave<unknown>([['products'], ['moves']], done)
  const gSave = useSave<Receipt>([['receipts'], ['products'], ['moves']], done)
  const sSave = useSave<Supplier>([['suppliers']], done)
  const showCost = can('report.view.cost_profit')
  const purchase = can('inventory.purchase')
  if (!branch) return <p className="muted">{t('common.loading')}</p>
  return (
    <>
      <Head title={t('nav.inventory')} sub={t('inv2.sub')}>
        {tab === 'products' && purchase && <button className="btn primary" onClick={() => { pSave.reset(); setPForm({ sku: '', name_ar: '', name_en: '', kind: 'retail', unit: 'pcs', sale_price: '', is_active: true }) }}><Icon name="plus" />{t('inv2.addProduct')}</button>}
        {tab === 'receipts' && purchase && <button className="btn primary" onClick={() => { gSave.reset(); setGrn({ supplier_id: String(suppliers.data?.[0]?.id ?? ''), notes: '', lines: [{ product_id: '', qty: '', unit_cost: '' }] }) }}><Icon name="truck" />{t('inv2.receive')}</button>}
        {tab === 'suppliers' && purchase && <button className="btn primary" onClick={() => { sSave.reset(); setSup({ name: '', phone: '' }) }}><Icon name="plus" />{t('inv2.addSupplier')}</button>}
      </Head>
      <div className="tabs">{(['products', 'receipts', 'suppliers', 'moves'] as Tab[]).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`inv2.tab.${x}`)}</button>)}</div>

      {tab === 'products' && <div className="tw"><table><thead><tr><th>{t('inv2.sku')}</th><th>{t('inv2.product')}</th><th>{t('inv2.kind')}</th><th className="n">{t('inv2.qty')}</th>
        {showCost && <th className="n">{t('inv2.avgCost')}</th>}<th className="n">{t('inv2.salePrice')}</th><th /></tr></thead>
        <tbody>{products.data?.map((p) => { const qty = Number(p.stock.qty); return <tr key={p.id}>
          <td className="num">{p.sku}</td><td><b>{nameOf(p, lang)}</b>{!p.is_active && <> <span className="pill mute">{t('common.inactive')}</span></>}</td>
          <td><span className="pill info">{t(`inv2.k.${p.kind}`)}</span></td>
          <td className="n"><span className={`pill ${qty > 5 ? 'good' : qty > 0 ? 'warn' : 'bad'}`}><bdi>{qty}</bdi> {p.unit}</span></td>
          {showCost && <td className="n money">{p.stock.avg_cost ? formatKWD(Number(p.stock.avg_cost).toFixed(3), lang) : '—'}</td>}
          <td className="n money">{p.sale_price ? formatKWD(p.sale_price, lang) : '—'}</td>
          <td className="row" style={{ flexWrap: 'nowrap' }}>
            {can('inventory.adjust') && <button className="btn sm" onClick={() => { aSave.reset(); setAdj({ product: p, qty: '', reason: '' }) }}>{t('inv2.adjust')}</button>}
            {purchase && <button className="btn sm" onClick={() => { pSave.reset(); setPForm({ ...p, sale_price: p.sale_price ?? '' }) }}>{t('common.edit')}</button>}</td></tr> })}
          {products.data?.length === 0 && <tr><td colSpan={7} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>}

      {tab === 'receipts' && <div className="tw"><table><thead><tr><th>{t('inv.number')}</th><th>{t('inv2.supplier')}</th><th>{t('acc.date')}</th><th>{t('inv.items')}</th><th className="n">{t('pos.total')}</th><th>{t('inv2.bill')}</th><th /></tr></thead>
        <tbody>{receipts.data?.map((r) => <tr key={r.id}>
          <td className="num">{r.number}</td><td>{r.supplier_name}</td><td className="num">{r.received_on}</td>
          <td className="small">{r.lines.map((l) => `${l.name_ar} ×${Number(l.qty)}`).join('، ')}</td>
          <td className="n money">{formatKWD(r.total, lang)}</td>
          <td>{r.bill ? <><span className="code">{r.bill.supplier_ref}</span> {r.bill.balance === '0.000' ? <span className="pill good">{t('inv.paid')}</span> : <span className="pill warn">{formatKWD(r.bill.balance, lang)}</span>}</> : <span className="pill mute">{t('inv2.noBill')}</span>}</td>
          <td>{purchase && !r.bill && <button className="btn sm" onClick={() => { gSave.reset(); setBill({ receipt: r, supplier_ref: '', amount: r.total, due_date: '' }) }}>{t('inv2.recordBill')}</button>}
            {purchase && r.bill && r.bill.balance !== '0.000' && <button className="btn sm" onClick={() => { gSave.reset(); setPay({ receipt: r, amount: r.bill!.balance, reference: '' }) }}>{t('inv2.pay')}</button>}</td></tr>)}
          {receipts.data?.length === 0 && <tr><td colSpan={7} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>}

      {tab === 'suppliers' && <div className="tw"><table><thead><tr><th>{t('inv2.supplier')}</th><th>{t('org.phone')}</th></tr></thead>
        <tbody>{suppliers.data?.map((s) => <tr key={s.id}><td><b>{s.name}</b></td><td className="num">{s.phone || '—'}</td></tr>)}
          {suppliers.data?.length === 0 && <tr><td colSpan={2} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>}

      {tab === 'moves' && <div className="tw"><table><thead><tr><th>{t('inv.time')}</th><th>{t('inv2.product')}</th><th>{t('inv2.moveKind')}</th><th className="n">{t('inv2.qty')}</th>{showCost && <th className="n">{t('inv2.value')}</th>}<th>{t('book.reason')}</th></tr></thead>
        <tbody>{moves.data?.map((m) => <tr key={m.id}><td className="num">{new Date(m.created_at).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Kuwait' })}</td>
          <td>{m.product}</td><td><span className="pill mute">{t(`inv2.mk.${m.kind}`)}</span></td>
          <td className="n num" style={{ color: Number(m.qty) < 0 ? 'var(--danger)' : 'var(--good-ink)' }}><bdi>{Number(m.qty) > 0 ? '+' : ''}{Number(m.qty)}</bdi></td>
          {showCost && <td className="n money">{m.value ? formatKWD(m.value, lang) : ''}</td>}<td className="small muted">{m.reason}</td></tr>)}</tbody></table></div>}

      <Dialog open={!!pForm} title={pForm?.id ? t('common.edit') : t('inv2.addProduct')} onClose={() => setPForm(null)} busy={pSave.busy}
        onSubmit={() => { const { id, ...body } = pForm!; pSave.save({ path: id ? `/inventory/products/${id}` : '/inventory/products', method: id ? 'PATCH' : 'POST', body: { ...body, sale_price: body.sale_price || null } }) }}>
        {pForm && <>
          <div className="two">
            <label className="field">{t('common.nameAr')}<input className="input" value={pForm.name_ar} onChange={(e) => setPForm({ ...pForm, name_ar: e.target.value })} required /></label>
            <label className="field">{t('common.nameEn')}<input className="input" dir="ltr" value={pForm.name_en} onChange={(e) => setPForm({ ...pForm, name_en: e.target.value })} /></label>
          </div>
          <div className="two">
            <label className="field">{t('inv2.sku')}<input className="input" dir="ltr" value={pForm.sku} onChange={(e) => setPForm({ ...pForm, sku: e.target.value })} required /></label>
            <label className="field">{t('inv2.kind')}<select className="input" value={pForm.kind} onChange={(e) => setPForm({ ...pForm, kind: e.target.value as PForm['kind'] })}>
              <option value="retail">{t('inv2.k.retail')}</option><option value="supply">{t('inv2.k.supply')}</option></select></label>
          </div>
          <div className="two">
            <label className="field">{t('inv2.unit')}<input className="input" value={pForm.unit} onChange={(e) => setPForm({ ...pForm, unit: e.target.value })} /></label>
            {pForm.kind === 'retail' && <label className="field">{t('inv2.salePrice')} (KWD)<input className="input" dir="ltr" inputMode="decimal" value={pForm.sale_price} onChange={(e) => setPForm({ ...pForm, sale_price: e.target.value })} /></label>}
          </div>
          {pForm.id && <label className="chk">{t('common.active')}<input type="checkbox" className="sw" checked={pForm.is_active} onChange={(e) => setPForm({ ...pForm, is_active: e.target.checked })} /></label>}
          <ErrorText error={pSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!adj} title={adj ? `${t('inv2.adjust')}: ${nameOf(adj.product, lang)}` : ''} onClose={() => setAdj(null)} busy={aSave.busy}
        onSubmit={() => aSave.save({ path: '/inventory/adjust', body: { branch_id: branch.id, product_id: adj!.product.id, qty_delta: adj!.qty, reason: adj!.reason } })}>
        {adj && <>
          <div className="small muted">{t('inv2.adjustHelp', { qty: Number(adj.product.stock.qty) })}</div>
          <label className="field">{t('inv2.qtyDelta')}<input className="input" dir="ltr" inputMode="decimal" placeholder="-2 / +3" value={adj.qty} onChange={(e) => setAdj({ ...adj, qty: e.target.value })} required /></label>
          <label className="field">{t('book.reason')}<input className="input" value={adj.reason} onChange={(e) => setAdj({ ...adj, reason: e.target.value })} required /></label>
          <ErrorText error={aSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!grn} wide title={t('inv2.receive')} onClose={() => setGrn(null)} busy={gSave.busy}
        onSubmit={() => gSave.save({ path: '/inventory/receipts', idempotencyKey: grnKey, body: { branch_id: branch.id, supplier_id: Number(grn!.supplier_id), notes: grn!.notes,
          lines: grn!.lines.filter((l) => l.product_id && l.qty).map((l) => ({ product_id: Number(l.product_id), qty: l.qty, unit_cost: l.unit_cost || '0' })) } })}>
        {grn && <>
          <label className="field">{t('inv2.supplier')}<select className="input" value={grn.supplier_id} onChange={(e) => setGrn({ ...grn, supplier_id: e.target.value })} required>
            <option value="" disabled>—</option>{suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          {suppliers.data?.length === 0 && <div className="notice">{t('inv2.noSuppliers')}</div>}
          {grn.lines.map((l, i) => <div className="row" key={i} style={{ flexWrap: 'nowrap' }}>
            <select className="input" value={l.product_id} onChange={(e) => setGrn({ ...grn, lines: grn.lines.map((x, j) => (j === i ? { ...x, product_id: e.target.value } : x)) })}>
              <option value="">{t('inv2.product')}</option>{products.data?.filter((p) => p.is_active).map((p) => <option key={p.id} value={p.id}>{nameOf(p, lang)}</option>)}</select>
            <input className="input" dir="ltr" inputMode="decimal" style={{ width: 90 }} placeholder={t('inv2.qty')} value={l.qty} onChange={(e) => setGrn({ ...grn, lines: grn.lines.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)) })} />
            <input className="input" dir="ltr" inputMode="decimal" style={{ width: 120 }} placeholder={t('inv2.unitCost')} value={l.unit_cost} onChange={(e) => setGrn({ ...grn, lines: grn.lines.map((x, j) => (j === i ? { ...x, unit_cost: e.target.value } : x)) })} />
          </div>)}
          <button type="button" className="btn sm" onClick={() => setGrn({ ...grn, lines: [...grn.lines, { product_id: '', qty: '', unit_cost: '' }] })}><Icon name="plus" />{t('inv2.addLine')}</button>
          <label className="field">{t('cust.notes')}<input className="input" value={grn.notes} onChange={(e) => setGrn({ ...grn, notes: e.target.value })} /></label>
          <div className="small muted">{t('inv2.receiveHelp')}</div>
          <ErrorText error={gSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!bill} title={t('inv2.recordBill')} onClose={() => setBill(null)} busy={gSave.busy}
        onSubmit={() => gSave.save({ path: `/inventory/receipts/${bill!.receipt.id}/bill`, idempotencyKey: grnKey, body: { supplier_ref: bill!.supplier_ref, amount: bill!.amount, due_date: bill!.due_date || null } })}>
        {bill && <>
          <div className="small muted">{t('inv2.billHelp', { total: formatKWD(bill.receipt.total, lang) })}</div>
          <label className="field">{t('inv2.supplierRef')}<input className="input" dir="ltr" value={bill.supplier_ref} onChange={(e) => setBill({ ...bill, supplier_ref: e.target.value })} required /></label>
          <div className="two">
            <label className="field">{t('inv.amount')}<input className="input" dir="ltr" inputMode="decimal" value={bill.amount} onChange={(e) => setBill({ ...bill, amount: e.target.value })} required /></label>
            <label className="field">{t('inv2.due')}<input className="input" type="date" value={bill.due_date} onChange={(e) => setBill({ ...bill, due_date: e.target.value })} /></label>
          </div>
          <ErrorText error={gSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!pay} title={t('inv2.pay')} onClose={() => setPay(null)} busy={gSave.busy}
        onSubmit={() => gSave.save({ path: `/inventory/bills/${pay!.receipt.bill!.id}/payments`, idempotencyKey: grnKey, body: { amount: pay!.amount, reference: pay!.reference } })}>
        {pay && <>
          <div className="small muted">{t('inv2.payHelp')}</div>
          <div className="two">
            <label className="field">{t('inv.amount')}<input className="input" dir="ltr" inputMode="decimal" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} required /></label>
            <label className="field">{t('pos.transferRef')}<input className="input" dir="ltr" value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} required /></label>
          </div>
          <ErrorText error={gSave.error} />
        </>}
      </Dialog>

      <Dialog open={!!sup} title={t('inv2.addSupplier')} onClose={() => setSup(null)} busy={sSave.busy} onSubmit={() => sSave.save({ path: '/inventory/suppliers', body: sup })}>
        {sup && <>
          <label className="field">{t('inv2.supplier')}<input className="input" value={sup.name} onChange={(e) => setSup({ ...sup, name: e.target.value })} required /></label>
          <label className="field">{t('org.phone')}<input className="input" dir="ltr" value={sup.phone} onChange={(e) => setSup({ ...sup, phone: e.target.value })} /></label>
          <ErrorText error={sSave.error} />
        </>}
      </Dialog>
    </>
  )
}
