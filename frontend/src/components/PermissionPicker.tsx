import { useTranslation } from 'react-i18next'

/** Permission groups for display; any code not listed falls under administration. */
const GROUPS: [string, string[]][] = [
  ['g_sales', ['pos.sell', 'pos.invoices.view', 'pos.discount.line', 'pos.discount.override', 'pos.credit_sale', 'pos.return', 'cash.session.open', 'cash.variance.approve']],
  ['g_booking', ['booking.view', 'booking.manage', 'customers.view', 'customers.manage']],
  ['g_catalog', ['catalog.view', 'catalog.manage', 'catalog.price.change', 'staff.view', 'staff.manage']],
  ['g_stock', ['inventory.view', 'inventory.purchase', 'inventory.adjust', 'marketing.manage']],
  ['g_money', ['report.view.cost_profit', 'commission.view.all', 'commission.pay', 'data.export']],
  ['g_acc', ['accounting.view', 'accounting.journal.post', 'accounting.journal.reverse', 'accounting.period.close', 'accounting.setup', 'reporting.statements.approve', 'qayd.export', 'qayd.submission.record']],
]
export const permLabel = (t: (k: string) => string, code: string) => t(`perm.${code.replace(/\./g, '_')}`)

/** Grouped checkboxes. `base` (the role's set) marks per-person additions and removals. */
export function PermissionPicker({ catalog, value, onChange, base, disabled }: { catalog: string[]; value: string[]; onChange: (v: string[]) => void; base?: string[]; disabled?: boolean }) {
  const { t } = useTranslation()
  const listed = new Set(GROUPS.flatMap(([, c]) => c))
  const groups: [string, string[]][] = [...GROUPS.map(([g, c]) => [g, c.filter((x) => catalog.includes(x))] as [string, string[]]),
    ['g_admin', catalog.filter((c) => !listed.has(c))]]
  const has = new Set(value)
  const toggle = (c: string) => onChange(has.has(c) ? value.filter((x) => x !== c) : [...value, c])
  const setGroup = (codes: string[], on: boolean) => onChange(on ? [...new Set([...value, ...codes])] : value.filter((x) => !codes.includes(x)))
  return <div className="grid" style={{ gap: 10 }}>
    {groups.filter(([, c]) => c.length).map(([g, codes]) => <div key={g} className="card" style={{ padding: 10 }}>
      <div className="row sb" style={{ marginBottom: 4 }}><b className="small">{t(`perm.${g}`)}</b>
        {!disabled && <span className="row" style={{ gap: 4 }}><button type="button" className="btn sm ghost" onClick={() => setGroup(codes, true)}>{t('usr.selectAll')}</button>
          <button type="button" className="btn sm ghost" onClick={() => setGroup(codes, false)}>{t('usr.selectNone')}</button></span>}</div>
      {codes.map((c) => {
        const inBase = base?.includes(c)
        const mark = base && has.has(c) !== !!inBase ? (has.has(c) ? 'added' : 'removed') : ''
        return <label key={c} className="row" style={{ gap: 8, padding: '3px 0', cursor: disabled ? 'default' : 'pointer' }}>
          <input type="checkbox" checked={has.has(c)} disabled={disabled} onChange={() => toggle(c)} />
          <span className="small grow">{permLabel(t, c)}</span>
          {mark && <span className={`pill ${mark === 'added' ? 'good' : 'warn'}`}>{t(`usr.${mark}`)}</span>}
        </label>
      })}
    </div>)}
  </div>
}
