import { Icon } from './ui'

/** Service illustrations, ported from the reference (js/ui/service-art.js): a child's face with the haircut drawn in. */
const H = '#4A2E1F', SK = '#F5C6A0'
const LONG: Record<string, string> = {
  layered: 'M17 44 Q14 20 40 18 Q66 20 63 44 L66 72 Q56 66 54 76 L26 76 Q24 66 14 72Z', dyeW: 'M17 44 Q14 20 40 18 Q66 20 63 44 L66 72 Q56 66 54 76 L26 76 Q24 66 14 72Z',
  dryL: 'M17 44 Q14 20 40 18 Q66 20 63 44 L64 76 L16 76Z', dryM: 'M18 44 Q16 20 40 18 Q64 20 62 44 L62 64 L18 64Z', oil: 'M17 44 Q14 20 40 18 Q66 20 63 44 L64 74 L16 74Z',
  waveL: 'M17 44 Q14 20 40 18 Q66 20 63 44 Q68 52 62 58 Q68 64 62 72 L18 72 Q12 64 18 58 Q12 52 17 44Z', waveS: 'M18 44 Q16 20 40 18 Q64 20 62 44 Q68 50 62 56 Q66 62 58 62 L22 62 Q14 62 18 56 Q12 50 18 44Z',
  keratin: 'M17 44 Q14 20 40 18 Q66 20 63 44 L64 76 L16 76Z', washG: 'M18 44 Q16 20 40 18 Q64 20 62 44 L62 66 L18 66Z', trimG: 'M17 44 Q14 20 40 18 Q66 20 63 44 L64 72 L16 72Z',
  bob: 'M18 52 Q14 20 40 19 Q66 20 62 52 L54 52 Q56 34 40 33 Q24 34 26 52Z', french: 'M19 50 Q15 20 40 19 Q65 20 61 50 L54 50 Q56 36 40 35 Q24 36 26 50Z',
  straw: 'M19 50 Q15 20 40 19 Q65 20 61 50 L54 50 Q56 36 40 35 Q24 36 26 50Z', dryS: 'M19 50 Q15 20 40 19 Q65 20 61 50 L54 50 Q56 34 40 33 Q24 34 26 50Z',
}
const BOY = 'M22 42 Q21 22 40 22 Q59 22 58 42 Q55 32 40 31 Q25 32 22 42Z'
const TOP: Record<string, string> = {
  baby: 'M30 30 Q40 24 50 30 Q46 27 40 27 Q34 27 30 30Z', boy: BOY, trimB: BOY, washB: BOY, boyBig: 'M22 40 Q22 20 40 20 Q58 20 58 40 L56 36 Q52 28 40 28 Q28 28 24 36Z',
  qadhla: 'M22 42 Q21 22 40 21 Q59 22 58 42 Q56 34 50 32 Q46 40 30 40 Q40 34 44 30 Q30 32 22 42Z', pixie: 'M21 44 Q20 21 40 21 Q60 21 59 44 Q57 33 48 32 Q38 40 26 38 Q34 34 36 30 Q26 34 21 44Z',
  french: 'M24 36 Q26 24 40 23 Q54 24 56 36 L56 38 L24 38Z', straw: 'M24 37 Q30 30 34 36 Q38 30 42 36 Q46 30 50 36 Q54 30 56 37 Q54 24 40 23 Q26 24 24 37Z',
}
const SCISSORS = (x: number, y: number) => `<g transform="translate(${x} ${y}) rotate(30)" stroke="#081510" stroke-width="2" fill="none"><circle cx="0" cy="12" r="3"/><circle cx="7" cy="12" r="3"/><path d="M2 9 9 -3M5 9 -2 -3"/></g>`
const BUBBLES = (d: number) => `<g fill="#fff" stroke="#8EC9F0" stroke-width="1.5"><circle cx="28" cy="${20 - d}" r="5"/><circle cx="40" cy="${15 - d}" r="6"/><circle cx="52" cy="${20 - d}" r="5"/><circle cx="${62 + d}" cy="${12 - d}" r="3"/></g>`
const AIR = (x: number) => `<g stroke="#7AA9D6" stroke-width="2" stroke-linecap="round"><path d="M${x} ${x === 64 ? 22 : 24}h10M${x + 2} ${x === 64 ? 30 : 32}h8M${x} ${x === 64 ? 38 : 40}h10"/></g>`
const BEARD = '<path d="M23 46 Q24 66 40 66 Q56 66 57 46 Q52 58 40 58 Q28 58 23 46Z" fill="#4A2E1F"/><path d="M34 53 Q40 50 46 53" stroke="#4A2E1F" stroke-width="3" fill="none" stroke-linecap="round"/>'
const EX: Record<string, string> = {
  trimB: SCISSORS(56, 10), trimG: SCISSORS(56, 8), washB: BUBBLES(0), washG: BUBBLES(2), dryS: AIR(64), dryM: AIR(66), dryL: AIR(66),
  oil: '<path d="M66 10 Q72 20 66 24 Q60 20 66 10Z" fill="#E7B53C"/>',
  keratin: '<g fill="#FFC83D"><path d="M64 10l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/><path d="M14 18l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z"/></g><path d="M24 30 L22 70M58 30 L60 70" stroke="#fff" stroke-width="1.5" opacity=".35"/>',
  straw: '<g transform="translate(52 20)"><path d="M0 0 Q-6 -6 -9 0 Q-6 6 0 0Z M0 0 Q6 -6 9 0 Q6 6 0 0Z" fill="#E94F7C"/><circle r="2" fill="#C2185B"/></g>',
  pixie: '<circle cx="56" cy="30" r="3" fill="#E94F7C"/>',
  baby: `<path d="M41 22 q3 -6 7 -3 q-4 0 -5 4" stroke="${H}" stroke-width="2" fill="none" stroke-linecap="round"/>`,
  boyBig: `<path d="M22 40 L24 46 M58 40 L56 46" stroke="${H}" stroke-width="3" opacity=".5"/>`,
  beard: BEARD, beardTrim: BEARD + SCISSORS(58, 8),
  shave: '<path d="M23 47 Q24 66 40 66 Q56 66 57 47 Q50 56 40 56 Q30 56 23 47Z" fill="#fff" stroke="#D7DEE5"/><circle cx="30" cy="58" r="3" fill="#fff" stroke="#D7DEE5"/><circle cx="50" cy="58" r="3" fill="#fff" stroke="#D7DEE5"/><path d="M60 50 l12 -12" stroke="#8A96A3" stroke-width="3" stroke-linecap="round"/>',
  mask: '<path d="M26 40 Q40 34 54 40 Q56 52 50 56 Q40 60 30 56 Q24 52 26 40Z" fill="#2B2F33" opacity=".75"/><circle cx="34" cy="44" r="2.6" fill="#F5C6A0"/><circle cx="46" cy="44" r="2.6" fill="#F5C6A0"/>',
  dyeM: '<path d="M22 40 Q22 22 40 22 Q58 22 58 40 Q55 31 40 30 Q25 31 22 40Z" fill="#7B3FA0" opacity=".75"/><circle cx="66" cy="14" r="6" fill="#7B3FA0"/>',
  dyeW: '<path d="M22 30 L20 70 M30 22 L28 74 M52 22 L54 74 M60 30 L62 70" stroke="#D9822B" stroke-width="3" opacity=".8"/>',
}
const FACE = `<circle cx="40" cy="44" r="17" fill="${SK}"/><circle cx="34" cy="44" r="1.8" fill="#2A1B12"/><circle cx="46" cy="44" r="1.8" fill="#2A1B12"/><path d="M35 51 Q40 55 45 51" stroke="#B5674A" stroke-width="1.8" fill="none" stroke-linecap="round"/><circle cx="30" cy="49" r="2.5" fill="#F29C9C" opacity=".5"/><circle cx="50" cy="49" r="2.5" fill="#F29C9C" opacity=".5"/>`

export const ART_KEYS = ['baby', 'boyBig', 'boy', 'trimB', 'washB', 'qadhla', 'pixie', 'bob', 'french', 'straw', 'layered', 'trimG', 'washG',
  'dryS', 'dryM', 'dryL', 'oil', 'waveS', 'waveL', 'keratin', 'beard', 'beardTrim', 'shave', 'mask', 'dyeM', 'dyeW']

/** Best guess from the Arabic/English name when the service has no art set (kids salons get faces by default). */
export function guessArt(name: string, biz: string): string {
  const n = name.toLowerCase(), has = (...w: string[]) => w.some((x) => n.includes(x))
  const girl = has('بنت', 'girl')
  if (has('كيراتين', 'keratin')) return 'keratin'
  if (has('ويفي', 'wav')) return has('طويل', 'long') ? 'waveL' : 'waveS'
  if (has('سشوار', 'blow', 'dry')) return has('طويل', 'long') ? 'dryL' : has('وسط', 'medium') ? 'dryM' : 'dryS'
  if (has('زيت', 'oil')) return 'oil'
  if (has('صبغ', 'dye', 'color')) return girl || biz === 'women' ? 'dyeW' : 'dyeM'
  if (has('ماسك', 'mask')) return 'mask'
  if (has('حلاقة ذقن', 'حلاقة دقن', 'shave')) return 'shave'
  if (has('لحية', 'لحيه', 'دقن', 'ذقن', 'beard')) return has('تحديد', 'trim') ? 'beardTrim' : 'beard'
  if (has('غسيل', 'wash')) return girl ? 'washG' : 'washB'
  if (has('تحديد', 'trim')) return girl ? 'trimG' : 'trimB'
  if (has('قذلة', 'qadhla')) return 'qadhla'
  if (has('بوي', 'pixie')) return 'pixie'
  if (has('فرنسي', 'french')) return 'french'
  if (has('كاريه', 'bob')) return 'bob'
  if (has('فراولة', 'straw')) return 'straw'
  if (has('مدرج', 'layer')) return 'layered'
  if (has('أقل من سنة', 'سنة', 'baby')) return 'baby'
  if (has('كبير', 'big')) return 'boyBig'
  if (girl) return 'bob'
  if (biz === 'kids' || has('ولد', 'boy', 'قصة', 'قص', 'cut')) return 'boy'
  return ''
}

export function ServiceArt({ art, size = 48, label }: { art: string; size?: number; label?: string }) {
  const k = art
  const girl = /pixie|bob|french|straw|layered|trimG|washG|dry|oil|wave|keratin|dyeW/.test(k)
  const bg = /wash|dry|oil|wave|keratin|shave|mask|dye/.test(k) ? '#D9F5E6' : girl ? '#FFE1EC' : '#DCE8FF'
  const body = `<rect width="80" height="80" rx="18" fill="${bg}"/>${LONG[k] ? `<path d="${LONG[k]}" fill="${H}"/>` : ''}${FACE}<path d="${TOP[k] ?? 'M21 42 Q20 21 40 21 Q60 21 59 42 Q56 31 40 30 Q24 31 21 42Z'}" fill="${H}"/>${EX[k] ?? ''}`
  // static, trusted markup (no user input) — same SVG as the reference
  return <svg viewBox="0 0 80 80" width={size} height={size} role="img" aria-label={label} style={{ flex: 'none' }} dangerouslySetInnerHTML={{ __html: body }} />
}

/** The service's tile picture: its drawing, or the sparkle icon when none fits (as the reference falls back to an emoji). */
export function SvcIcon({ s, size = 48 }: { s: { art?: string; name_ar: string; name_en: string; business_type: string }; size?: number }) {
  const k = s.art || guessArt(`${s.name_ar} ${s.name_en}`, s.business_type)
  return k ? <ServiceArt art={k} size={size} label={s.name_ar} /> : <span className="ic"><Icon name="sparkle" /></span>
}
