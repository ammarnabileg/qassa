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
export type LoginResult = Me | { mfa: 'setup' | 'verify' }
export type Branch = { id: number; legal_entity: number; name_ar: string; name_en: string; code: string; business_type: 'kids' | 'men' | 'women'; timezone: string; address: string; phone: string; is_active: boolean }
export type LegalEntity = { id: number; name_ar: string; name_en: string; commercial_registration: string; legal_form: string; base_currency: string; fiscal_year_start_month: number }
export type Account = { id: number; code: string; name_ar: string; name_en: string; type: string; is_postable: boolean; is_control: boolean; is_active: boolean }
export type TBRow = { account_id: number; code: string; name_ar: string; name_en: string; type: string; opening: string; debit: string; credit: string; closing: string; normal_side: string }

export type Category = { id: number; name_ar: string; name_en: string; business_type: 'kids' | 'men' | 'women'; sort: number }
export type Service = { id: number; category: number; business_type: string; name_ar: string; name_en: string; duration_minutes: number; home_visit: boolean; is_active: boolean; current_price: string | null }
export type Price = { id: number; branch: number | null; price: string; valid_from: string; valid_to: string | null }
export type Staff = { id: number; full_name_ar: string; full_name_en: string; phone: string; is_active: boolean; branch_ids: number[]; service_ids: number[] }
export type Beneficiary = { id: number; full_name: string; relation: 'self' | 'child' | 'other'; birth_date: string | null; gender: '' | 'm' | 'f'; notes: string; is_active: boolean }
export type Customer = { id: number; full_name: string; phone: string; email: string; preferred_language: 'ar' | 'en'; whatsapp_opt_in: boolean; marketing_opt_in: boolean; notes: string; is_active: boolean; created_at: string; beneficiaries: Beneficiary[] }
export type Plan = { id: number; code: string; name_ar: string; name_en: string; monthly_price: string; max_branches: number; max_staff: number; custom_domain: boolean; is_active: boolean; sort: number }
export type SubscriptionInfo = { plan: { code: string; name_ar: string; name_en: string; monthly_price: string; max_branches: number; max_staff: number } | null; current_period_end: string | null; hosts: string[]; usage: { branches?: number; staff?: number } }
export type TenantRow = { id: number; name: string; slug: string; status: string; default_business_type: 'kids' | 'men' | 'women'; plan: string | null; branches: number; hosts: string[]; created_at: string }
export type Domain = { id: number; host: string; kind: 'subdomain' | 'custom'; is_active: boolean; created_at: string; activated_at: string | null }
