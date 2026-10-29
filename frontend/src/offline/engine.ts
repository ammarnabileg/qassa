/** Offline till: totals computed exactly like the server (fils, half-up), signed receipts, and sync. D-013. */
import { api } from '../api/client'
import { fromFils, toFils } from '../money'
import { kvGet, kvSet, nextSeq, saleDel, salePut, salesAll, type StoredSale } from './store'

export type Bundle = {
  generated_at: string; business_date: string; branch_id: number; discount_limit_percent: string
  services: { id: number; name_ar: string; name_en: string; price: string; category: string }[]
  products: { id: number; name_ar: string; name_en: string; price: string; qty: string }[]
  plans: { id: number; name_ar: string; name_en: string; price: string; sessions: number; service_id: number }[]
  coupons: { code: string; kind: 'percent' | 'amount'; value: string; min_total: string; left: number | null }[]
  staff: { id: number; name_ar: string; name_en: string }[]
  customers: { id: number; full_name: string; phone: string; points: number; beneficiaries: { id: number; full_name: string }[]
    packages: { id: number; service_id: number; sessions_left: number; session_value: string; name_ar: string }[] }[]
  loyalty: { enabled: boolean; point_value: string; min_redeem: number }
}
export type Device = { id: number; secret: string; branch_id: number; name: string; tenant: number }
export type OLine = { key: string; kind: 'service' | 'product' | 'package'; id: number; name: string; unit_price: string; qty: number; discount: string
  staff_id?: number | null; redeem_package_id?: number | null }

const deviceKey = (tenant: number) => `device:${tenant}`
const bundleKey = (tenant: number, branch: number) => `bundle:${tenant}:${branch}`
export const getDevice = (tenant: number) => kvGet<Device>(deviceKey(tenant))
export const getBundle = (tenant: number, branch: number) => kvGet<Bundle>(bundleKey(tenant, branch))

export async function registerDevice(tenant: number, branch_id: number, name: string): Promise<Device> {
  const d = await api<Omit<Device, 'tenant'>>('/pos/devices', { method: 'POST', body: { branch_id, name } })
  const dev = { ...d, tenant }
  await kvSet(deviceKey(tenant), dev)
  return dev
}

export async function refreshBundle(tenant: number, branch: number): Promise<Bundle> {
  const b = await api<Bundle>(`/pos/offline/bundle?branch_id=${branch}`)
  await kvSet(bundleKey(tenant, branch), b)
  return b
}

/** Half-up rounding of a fils amount × rate (rate as a decimal string), all integers. */
function mulRate(fils: bigint, rate: string, divisor: bigint): bigint {
  const [i, f = ''] = rate.split('.')
  const scale = 10n ** BigInt(f.length)
  const num = fils * BigInt(i + f)
  const den = scale * divisor
  return (num * 2n + den) / (2n * den)
}

export type Totals = { subtotal: bigint; manual: bigint; coupon: bigint; points: number; pointsDisc: bigint; total: bigint; problems: string[] }

/** Mirrors sales._plan_lines / _apply_promotions (server re-checks everything on sync). */
export function totals(lines: OLine[], b: Bundle, couponCode: string, redeemPoints: number, customerPoints: number): Totals {
  let subtotal = 0n, manual = 0n, base = 0n
  const problems: string[] = []
  for (const l of lines) {
    const gross = toFils(l.unit_price) * BigInt(l.qty)
    const disc = l.redeem_package_id ? gross : toFils(l.discount || '0')
    subtotal += gross
    manual += disc
    if (!l.redeem_package_id) base += gross - disc
  }
  let coupon = 0n
  const code = couponCode.trim().toUpperCase()
  if (code) {
    const c = b.coupons.find((x) => x.code.toUpperCase() === code)
    if (!c) problems.push('coupon_invalid')
    else if (c.left === 0) problems.push('coupon_used_up')
    else if (base < toFils(c.min_total)) problems.push('coupon_min_total')
    else coupon = c.kind === 'percent' ? mulRate(base, c.value, 100n) : (toFils(c.value) < base ? toFils(c.value) : base)
  }
  let points = 0, pointsDisc = 0n
  if (redeemPoints > 0) {
    if (!b.loyalty.enabled) problems.push('loyalty_disabled')
    else if (redeemPoints < b.loyalty.min_redeem) problems.push('points_below_minimum')
    else if (redeemPoints > customerPoints) problems.push('points_insufficient')
    else {
      const pv = toFils(b.loyalty.point_value)
      const maxPoints = pv > 0n ? Number((base - coupon) / pv) : 0
      points = Math.min(redeemPoints, maxPoints)
      pointsDisc = BigInt(points) * pv
    }
  }
  return { subtotal, manual, coupon, points, pointsDisc, total: subtotal - manual - coupon - pointsDisc, problems }
}

/** Same canonical form as offline.canonical() on the server: sorted keys, no spaces, raw unicode. */
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']'
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    return '{' + Object.keys(o).filter((k) => o[k] !== undefined).sort().map((k) => JSON.stringify(k) + ':' + canonical(o[k])).join(',') + '}'
  }
  return JSON.stringify(v)
}

async function hmac(secret: string, text: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(text))
  return [...new Uint8Array(sig)].map((x) => x.toString(16).padStart(2, '0')).join('')
}

/** Save a sale locally (signed, numbered). Returns the stored record, including what to print. */
export async function recordSale(dev: Device, body: {
  lines: OLine[]; payments: { method: string; amount: string; reference: string }[]; customer_id: number | null; beneficiary_id: number | null
  coupon_code: string; redeem_points: number; tip: string; tip_staff_id: number | null
}, t: Totals, printed: Record<string, unknown>): Promise<StoredSale> {
  const seq = await nextSeq(dev.tenant)
  const payload = {
    uuid: crypto.randomUUID(), seq, created_at: new Date().toISOString(), total: fromFils(t.total),
    lines: body.lines.map((l) => ({
      ...(l.kind === 'service' ? { service_id: l.id } : l.kind === 'product' ? { product_id: l.id } : { package_plan_id: l.id }),
      qty: l.qty, unit_price: l.unit_price, discount: l.redeem_package_id ? '0' : (l.discount || '0'),
      ...(l.staff_id ? { staff_id: l.staff_id } : {}), ...(l.redeem_package_id ? { redeem_package_id: l.redeem_package_id } : {}),
    })),
    payments: body.payments, customer_id: body.customer_id, beneficiary_id: body.beneficiary_id,
    coupon_code: body.coupon_code, redeem_points: body.redeem_points, tip: body.tip || '0', tip_staff_id: body.tip_staff_id,
  }
  const sale: StoredSale = { payload, signature: await hmac(dev.secret, canonical(payload)), tenant: dev.tenant, printed: { ...printed, ref: `OFF-${dev.id}-${seq}` } }
  await salePut(sale)
  return sale
}

export const pending = async (tenant: number) => (await salesAll()).filter((s) => s.tenant === tenant).sort((a, b) => a.payload.seq - b.payload.seq)

type Result = { uuid: string; status?: 'synced' | 'review' | 'conflict'; rejected?: string }

/** Send unsent receipts in order. A receipt leaves the browser only once the server has stored it. */
export async function syncNow(tenant: number): Promise<{ sent: number; review: number; conflict: number; rejected: number; left: number }> {
  const dev = await getDevice(tenant)
  const list = await pending(tenant)
  const out = { sent: 0, review: 0, conflict: 0, rejected: 0, left: list.length }
  if (!dev || list.length === 0) return out
  for (let i = 0; i < list.length; i += 50) {
    const chunk = list.slice(i, i + 50)
    const r = await api<{ results: Result[] }>('/pos/offline/sync', { method: 'POST', body: { device_id: dev.id, sales: chunk.map((s) => ({ payload: s.payload, signature: s.signature })) } })
    for (const x of r.results) {
      if (x.status) { await saleDel(x.uuid); out.sent++; if (x.status === 'review') out.review++; if (x.status === 'conflict') out.conflict++ }
      else if (x.rejected) out.rejected++   // kept in the browser and shown; never deleted silently
    }
  }
  out.left = (await pending(tenant)).length
  return out
}

/** After an offline sale, update the local snapshot so this device does not sell the same stock, coupon use,
 *  points or package session twice before the connection returns. The server stays the judge on sync. */
export async function applyToBundle(tenant: number, branch: number, lines: OLine[], couponCode: string, points: number, customerId: number | null) {
  const b = await getBundle(tenant, branch)
  if (!b) return
  for (const l of lines) {
    if (l.kind === 'product') {
      const p = b.products.find((x) => x.id === l.id)
      if (p) p.qty = String(Number(p.qty) - l.qty)
    }
    if (l.redeem_package_id && customerId) {
      const pk = b.customers.find((c) => c.id === customerId)?.packages.find((x) => x.id === l.redeem_package_id)
      if (pk) pk.sessions_left -= l.qty
    }
  }
  const c = couponCode ? b.coupons.find((x) => x.code.toUpperCase() === couponCode.toUpperCase()) : undefined
  if (c && c.left !== null) c.left = Math.max(0, c.left - 1)
  const cust = customerId ? b.customers.find((x) => x.id === customerId) : undefined
  if (cust && points) cust.points -= points
  if (cust) cust.packages = cust.packages.filter((p) => p.sessions_left > 0)
  await kvSet(bundleKey(tenant, branch), b)
}
