import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatKWD } from '../money'

/** Pricing-page calculator: what no-shows cost a salon a month, and what reminders might win back, next to the plan price.
 *  The recovery rate is the visitor's own assumption (editable), not a promise. */
export function SavingsCalc({ planPrice }: { planPrice: number | null }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const [f, setF] = useState({ noShows: '5', ticket: '6', rate: '30' })
  const n = (v: string) => Math.max(0, Number(v) || 0)
  const lost = n(f.noShows) * n(f.ticket) * 4.33
  const back = lost * Math.min(100, n(f.rate)) / 100
  const field = (k: keyof typeof f, label: string, help?: string) => <label className="field">{label}
    <input className="input" dir="ltr" inputMode="decimal" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value.replace(/[^\d.]/g, '') })} />
    {help && <small className="muted">{help}</small>}</label>
  return (
    <div className="card" style={{ maxWidth: 760, margin: '0 auto' }}>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 12 }}>
        {field('noShows', t('calc.noShows'))}
        {field('ticket', t('calc.ticket'))}
        {field('rate', t('calc.rate'), t('calc.rateHelp'))}
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 12, marginTop: 12 }}>
        <div><div className="small muted">{t('calc.lost')}</div><div className="money" style={{ fontSize: 26, fontWeight: 800, color: 'var(--danger, #c0392b)' }}>{formatKWD(lost.toFixed(3), lang)}</div></div>
        <div><div className="small muted">{t('calc.back')}</div><div className="money" style={{ fontSize: 26, fontWeight: 800, color: 'var(--brand-700)' }}>{formatKWD(back.toFixed(3), lang)}</div></div>
        {planPrice !== null && <div><div className="small muted">{t('calc.plan')}</div><div className="money" style={{ fontSize: 26, fontWeight: 800 }}>{formatKWD(planPrice.toFixed(3), lang)}</div></div>}
      </div>
      <div className="cap muted" style={{ marginTop: 10 }}>{t('calc.note')}</div>
    </div>
  )
}
