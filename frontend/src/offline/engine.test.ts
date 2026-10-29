import { describe, expect, it } from 'vitest'
import { canonical, totals, type Bundle, type OLine } from './engine'

const payload = { uuid: '00000000-0000-4000-8000-000000000001', seq: 7, created_at: '2026-10-30T09:15:00.000Z', total: '12.000',
  lines: [{ service_id: 3, qty: 1, unit_price: '15.000', discount: '0', staff_id: 4 }], payments: [{ method: 'cash', amount: '12.000', reference: '' }],
  customer_id: null, beneficiary_id: null, coupon_code: 'ONE', redeem_points: 0, tip: '0', tip_staff_id: null, note: 'قص' }
// produced by apps.pos.services.offline.canonical / sign on the server with the same payload and secret
const SERVER_CANONICAL = '{"beneficiary_id":null,"coupon_code":"ONE","created_at":"2026-10-30T09:15:00.000Z","customer_id":null,"lines":[{"discount":"0","qty":1,"service_id":3,"staff_id":4,"unit_price":"15.000"}],"note":"قص","payments":[{"amount":"12.000","method":"cash","reference":""}],"redeem_points":0,"seq":7,"tip":"0","tip_staff_id":null,"total":"12.000","uuid":"00000000-0000-4000-8000-000000000001"}'
const SERVER_SIGNATURE = 'e6d31012f641f42bebf5d13b287c1e5efb3a61194583f279cee612b385ed83bd'

async function hmac(secret: string, text: string) {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  return [...new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(text)))].map((x) => x.toString(16).padStart(2, '0')).join('')
}

const bundle = { coupons: [{ code: 'P15', kind: 'percent', value: '15', min_total: '0', left: 1 }, { code: 'USED', kind: 'amount', value: '1', min_total: '0', left: 0 }],
  loyalty: { enabled: true, point_value: '0.010', min_redeem: 100 } } as unknown as Bundle
const line = (price: string, qty = 1, discount = '0', pkg: number | null = null): OLine =>
  ({ key: price + qty, kind: 'service', id: 1, name: 'x', unit_price: price, qty, discount, redeem_package_id: pkg })

describe('offline engine', () => {
  it('signs exactly like the server', async () => {
    expect(canonical(payload)).toBe(SERVER_CANONICAL)
    expect(await hmac('abc123secret', canonical(payload))).toBe(SERVER_SIGNATURE)
  })
  it('computes coupon and points like the server (fils, half-up)', () => {
    const t = totals([line('3.335'), line('5.000', 1, '0.500')], bundle, 'p15', 150, 500)
    // base 7.835 → 15% = 1.17525 → 1.175 ; points: 150 × 0.010 = 1.500
    expect([t.coupon, t.pointsDisc, t.total, t.points]).toEqual([1175n, 1500n, 5160n, 150])
  })
  it('never discounts below zero and flags invalid promotions', () => {
    const t = totals([line('1.000')], bundle, 'USED', 50, 40)
    expect(t.problems).toEqual(['coupon_used_up', 'points_below_minimum'])
    expect(totals([line('4.000', 1, '0', 9)], bundle, '', 0, 0).total).toBe(0n)   // package session: free line
  })
})
