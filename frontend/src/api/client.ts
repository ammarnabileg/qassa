/** API client: session cookie + CSRF, X-Tenant on tenant-scoped calls, Idempotency-Key on every POST. */
export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>
  constructor(status: number, code: string, message = '', details: Record<string, unknown> = {}) {
    super(message || code)
    this.status = status
    this.code = code
    this.details = details
  }
}

let tenantId: number | null = null
export const setTenant = (id: number | null) => { tenantId = id }
export const getTenant = () => tenantId

function cookie(name: string) {
  return document.cookie.split('; ').find((c) => c.startsWith(name + '='))?.split('=')[1]
}

async function ensureCsrf() {
  if (!cookie('csrftoken')) await fetch('/api/v1/auth/csrf', { credentials: 'include' })
  return cookie('csrftoken') ?? ''
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown; idempotencyKey?: string } = {}): Promise<T> {
  const method = opts.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (tenantId) headers['X-Tenant'] = String(tenantId)
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json'
    headers['X-CSRFToken'] = await ensureCsrf()
    if (method === 'POST') headers['Idempotency-Key'] = opts.idempotencyKey ?? crypto.randomUUID()
  }
  let res: Response
  try {
    res = await fetch('/api/v1' + path, { method, headers, credentials: 'include', body: opts.body ? JSON.stringify(opts.body) : undefined })
  } catch {
    throw new ApiError(0, 'network')
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const e = data?.error ?? {}
    throw new ApiError(res.status, e.code ?? 'unknown', e.message ?? '', e.details ?? {})
  }
  return data as T
}

export type Membership = { tenant_id: number; tenant_name: string; tenant_status: string; tenant_business_type: 'kids' | 'men' | 'women'; role: string; role_name: { ar: string; en: string }; permissions: string[]; all_branches: boolean; branch_ids: number[] }
export type Me = { id: number; email: string; full_name: string; language: 'ar' | 'en'; is_platform_staff: boolean; mfa_required: boolean; memberships: Membership[] }
export type LoginResult = Me | { mfa: 'setup' | 'verify'; methods: ('totp' | 'whatsapp')[]; phone: string }
export type Branch = { id: number; legal_entity: number; name_ar: string; name_en: string; code: string; business_type: 'kids' | 'men' | 'women'; timezone: string; address: string; phone: string; latitude: string | null; longitude: string | null; opens_at: string; closes_at: string; online_booking: boolean; is_active: boolean }
export type LegalEntity = { id: number; name_ar: string; name_en: string; commercial_registration: string; legal_form: string; base_currency: string; fiscal_year_start_month: number }
export type Account = { id: number; code: string; name_ar: string; name_en: string; type: string; is_postable: boolean; is_control: boolean; is_active: boolean }
export type TBRow = { account_id: number; code: string; name_ar: string; name_en: string; type: string; opening: string; debit: string; credit: string; closing: string; normal_side: string }

export type Category = { id: number; name_ar: string; name_en: string; business_type: 'kids' | 'men' | 'women'; sort: number }
export type Service = { id: number; category: number; business_type: string; name_ar: string; name_en: string; duration_minutes: number; home_visit: boolean; is_active: boolean; current_price: string | null }
export type Price = { id: number; branch: number | null; price: string; valid_from: string; valid_to: string | null }
export type Staff = { id: number; full_name_ar: string; full_name_en: string; phone: string; commission_percent: string; is_active: boolean; branch_ids: number[]; service_ids: number[] }
export type Beneficiary = { id: number; full_name: string; relation: 'self' | 'child' | 'other'; birth_date: string | null; gender: '' | 'm' | 'f'; notes: string; is_active: boolean }
export type Customer = { id: number; full_name: string; phone: string; email: string; preferred_language: 'ar' | 'en'; whatsapp_opt_in: boolean; marketing_opt_in: boolean; notes: string; is_active: boolean; created_at: string; beneficiaries: Beneficiary[] }
export type Plan = { id: number; code: string; name_ar: string; name_en: string; monthly_price: string; max_branches: number; max_staff: number; custom_domain: boolean; is_active: boolean; sort: number }
export type SubscriptionInfo = { plan: { code: string; name_ar: string; name_en: string; monthly_price: string; max_branches: number; max_staff: number } | null; current_period_end: string | null; hosts: string[]; usage: { branches?: number; staff?: number } }
export type TenantRow = { id: number; name: string; slug: string; status: string; default_business_type: 'kids' | 'men' | 'women'; plan: string | null; branches: number; hosts: string[]; owner_phone: string; created_at: string }
export type Domain = { id: number; host: string; kind: 'subdomain' | 'custom'; is_active: boolean; created_at: string; activated_at: string | null }

export type ApptItem = { id: number; service_id: number; staff_id: number; service_name_ar: string; service_name_en: string; starts_at: string; ends_at: string }
export type ApptStatus = 'booked' | 'arrived' | 'in_service' | 'completed' | 'invoiced' | 'cancelled' | 'no_show'
export type Appointment = { id: number; branch: number; customer: number | null; beneficiary: number | null; walk_in_name: string; customer_name: string; beneficiary_name: string; customer_phone: string; status: ApptStatus; source: 'reception' | 'walk_in' | 'online'; starts_at: string; ends_at: string; business_date: string; notes: string; status_reason: string; invoice_id: number | null; items: ApptItem[] }
export type CashSession = { id: number; branch: number; status: 'open' | 'closed'; opened_by: number; opened_at: string; opening_float: string; closed_by: number | null; closed_at: string | null; expected_cash: string | null; counted_cash: string | null; variance: string | null; variance_status: 'none' | 'pending' | 'approved'; variance_approved_by: number | null; notes: string; expected_now: string | null }
export type InvLine = { id: number; kind: 'service' | 'product' | 'package'; product_id: number | null; redeemed_package_id: number | null; service_id: number | null; staff_id: number | null; name_ar: string; name_en: string; qty: number; unit_price: string; discount: string; line_total: string; returned: string }
export type InvPayment = { id: number; direction: 'in' | 'out'; method: 'cash' | 'knet' | 'transfer'; amount: string; reference: string; received_at: string; credit_note_id: number | null }
export type Invoice = { id: number; number: string; branch: number; customer: number | null; customer_name: string; customer_phone: string; beneficiary: number | null; beneficiary_name: string; appointment: number | null; subtotal: string; discount_total: string; total: string; tip: string; points_redeemed: number; is_credit: boolean; business_date: string; issued_at: string; issued_by_name: string; lines: InvLine[]; payments: InvPayment[]; credit_notes: { id: number; number: string; reason: string; total: string; issued_at: string }[]; state: { paid: string; credited: string; balance: string; refundable: string } }

export type Product = { id: number; sku: string; name_ar: string; name_en: string; kind: 'retail' | 'supply'; unit: string; sale_price: string | null; is_active: boolean; stock: { qty: string; avg_cost?: string } }
export type Supplier = { id: number; name: string; phone: string; is_active: boolean }
export type Receipt = { id: number; number: string; branch: number; supplier: number; supplier_name: string; received_on: string; total: string; notes: string; lines: { product_id: number; name_ar: string; qty: string; unit_cost: string; line_total: string }[]; bill: { id: number; supplier_ref: string; amount: string; due_date: string | null; balance: string } | null }
export type PackagePlan = { id: number; name_ar: string; name_en: string; service: number; sessions: number; price: string; validity_days: number; is_active: boolean }
export type Coupon = { id: number; code: string; kind: 'percent' | 'amount'; value: string; min_total: string; valid_from: string; valid_to: string; max_uses: number | null; used_count: number; is_active: boolean }
export type LoyaltySettings = { enabled: boolean; points_per_kd: number; point_value: string; min_redeem: number }
export type Wallet = { points: number; packages: { id: number; name_ar: string; name_en: string; service_id: number; sessions_left: number; sessions_total: number; session_value: string; expires_on: string }[]; history: { kind: string; points: number; invoice: string; created_at: string }[] }
export type Quote = { subtotal: string; discount_total: string; total: string; coupon_discount: string; points: number; points_discount: string; lines: { total: string }[] }
export type Member = { id: number; user_id: number; email: string; full_name: string; phone: string; role: string; role_name: { ar: string; en: string }; all_branches: boolean; branch_ids: number[]; discount_limit_percent: string; is_active: boolean; has_password: boolean }
