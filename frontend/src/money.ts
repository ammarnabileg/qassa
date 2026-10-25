/** Fils-based arithmetic for the UI: KWD amounts are strings from the API, converted to integer fils.
 *  Never use JS floats for money math. */
export function toFils(v: string | number | undefined | null): bigint {
  const s = String(v ?? '').trim()
  if (!s) return 0n
  const m = /^(-)?(\d+)(?:\.(\d{0,3}))?$/.exec(s)
  if (!m) throw new Error('invalid amount')
  const fils = BigInt(m[2]) * 1000n + BigInt((m[3] ?? '').padEnd(3, '0') || '0')
  return m[1] ? -fils : fils
}

export function fromFils(f: bigint): string {
  const neg = f < 0n
  const a = neg ? -f : f
  return `${neg ? '-' : ''}${a / 1000n}.${String(a % 1000n).padStart(3, '0')}`
}

export function formatKWD(v: string | bigint, lang: 'ar' | 'en') {
  const s = typeof v === 'bigint' ? fromFils(v) : v
  const [i, d = '000'] = s.replace('-', '').split('.')
  const grouped = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${s.startsWith('-') ? '-' : ''}${grouped}.${d.padEnd(3, '0')} ${lang === 'ar' ? 'د.ك' : 'KWD'}`
}
