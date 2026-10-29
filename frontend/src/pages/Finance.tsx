import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, Stat, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { useOrg } from './Org'

type Acc = { id: number; code: string; name_ar: string; name_en: string; type: string; is_postable: boolean; is_control: boolean }
type Expense = { id: number; branch: number | null; expense_date: string; account_code: string; account_name_ar: string; account_name_en: string
  description: string; amount: string; paid_from: 'bank' | 'cash' | 'accrued'; reference: string; paid_on: string | null; paid_reference: string }
type Asset = { id: number; name: string; acquired_on: string; cost: string; residual_value: string; life_months: number; monthly: string; accumulated: string; book_value: string }
type Row = { account_id: number; code: string; name_ar: string; name_en: string; amount: string }
type Income = { from: string; to: string; revenue: Row[]; total_revenue: string; expenses: Row[]; total_expenses: string; gross_profit: string; net_profit: string }
type Balance = { as_of: string; assets: Row[]; total_assets: string; liabilities: Row[]; total_liabilities: string; equity: Row[]; unclosed_profit: string; total_equity: string; balanced: boolean }
type Year = { id: number; name: string; start_date: string; end_date: string; closing_entry: string | null; periods: { id: number; number: number; start_date: string; end_date: string; status: 'open' | 'closed' }[] }
type Version = { id: number; kind: string; params: Record<string, string>; note: string; sha256: string; created_at: string; created_by: string }

const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kuwait' })
const thisYear = () => today().slice(0, 4)

function useEntity() {
  const org = useOrg()
  const e = org.data?.legal_entities[0]
  return { e, q: e ? `?legal_entity_id=${e.id}` : '' }
}

export function Expenses() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const { branch } = useBranch()
  const toast = useToast()
  const { e, q } = useEntity()
  const list = useQuery({ enabled: !!e, queryKey: ['expenses', e?.id], queryFn: () => api<Expense[]>(`/accounting/expenses${q}`) })
  const accs = useQuery({ enabled: !!e, queryKey: ['accounts', e?.id], queryFn: () => api<Acc[]>(`/accounting/accounts${q}`) })
  const [form, setForm] = useState<{ expense_date: string; account_id: string; description: string; amount: string; paid_from: string; reference: string; branch: boolean } | null>(null)
  const [pay, setPay] = useState<{ x: Expense; paid_on: string; reference: string } | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const done = () => { setForm(null); setPay(null); setKey(crypto.randomUUID()); toast(t('common.saved')) }
  const s = useSave<Expense>([['expenses']], done)
  const expenseAccs = (accs.data ?? []).filter((a) => a.type === 'expense' && a.is_postable && !a.is_control)
  const open = (list.data ?? []).filter((x) => x.paid_from === 'accrued' && !x.paid_on)
  return (
    <>
      <Head title={t('nav.expenses')} sub={t('fin.expSub')}>
        {can('accounting.journal.post') && <button className="btn primary" onClick={() => { s.reset(); setForm({ expense_date: today(), account_id: String(expenseAccs[0]?.id ?? ''), description: '', amount: '', paid_from: 'bank', reference: '', branch: true }) }}><Icon name="plus" />{t('fin.addExpense')}</button>}
      </Head>
      <ErrorText error={list.error} />
      {open.length > 0 && <div className="notice"><Icon name="clock" />{t('fin.accruedOpen', { n: open.length, v: formatKWD(open.reduce((a, x) => a + Number(x.amount), 0).toFixed(3), lang) })}</div>}
      <div className="tw"><table><thead><tr><th>{t('acc.date')}</th><th>{t('acc.account')}</th><th>{t('fin.description')}</th><th>{t('fin.paidFrom')}</th><th className="n">{t('inv.amount')}</th><th /></tr></thead>
        <tbody>{list.data?.map((x) => <tr key={x.id}>
          <td className="num">{x.expense_date}</td><td><span className="num">{x.account_code}</span> {lang === 'en' ? x.account_name_en : x.account_name_ar}</td>
          <td>{x.description}{x.reference && <div className="cap muted">{x.reference}</div>}</td>
          <td><span className={`pill ${x.paid_from === 'accrued' && !x.paid_on ? 'warn' : 'mute'}`}>{t(`fin.pf.${x.paid_from}`)}</span>{x.paid_from === 'accrued' && x.paid_on && <div className="cap muted">{t('fin.paidOn', { d: x.paid_on })}</div>}</td>
          <td className="n money">{formatKWD(x.amount, lang)}</td>
          <td>{x.paid_from === 'accrued' && !x.paid_on && can('accounting.journal.post') && <button className="btn sm" onClick={() => { s.reset(); setPay({ x, paid_on: today(), reference: '' }) }}>{t('inv2.pay')}</button>}</td></tr>)}
          {list.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>
      <Dialog open={!!form} title={t('fin.addExpense')} onClose={() => setForm(null)} busy={s.busy}
        onSubmit={() => s.save({ path: `/accounting/expenses${q}`, idempotencyKey: key, body: { ...form, account_id: Number(form!.account_id), branch_id: form!.branch || form!.paid_from === 'cash' ? branch?.id : null } })}>
        {form && <>
          <div className="two">
            <label className="field">{t('acc.date')}<input className="input" type="date" value={form.expense_date} onChange={(ev) => setForm({ ...form, expense_date: ev.target.value })} required /></label>
            <label className="field">{t('inv.amount')} (KWD)<input className="input" dir="ltr" inputMode="decimal" value={form.amount} onChange={(ev) => setForm({ ...form, amount: ev.target.value })} required /></label>
          </div>
          <label className="field">{t('acc.account')}<select className="input" value={form.account_id} onChange={(ev) => setForm({ ...form, account_id: ev.target.value })}>
            {expenseAccs.map((a) => <option key={a.id} value={a.id}>{a.code} — {nameOf(a, lang)}</option>)}</select></label>
          <label className="field">{t('fin.description')}<input className="input" value={form.description} onChange={(ev) => setForm({ ...form, description: ev.target.value })} required /></label>
          <div className="two">
            <label className="field">{t('fin.paidFrom')}<select className="input" value={form.paid_from} onChange={(ev) => setForm({ ...form, paid_from: ev.target.value })}>
              {['bank', 'cash', 'accrued'].map((x) => <option key={x} value={x}>{t(`fin.pf.${x}`)}</option>)}</select></label>
            <label className="field">{t('fin.reference')}<input className="input" dir="ltr" value={form.reference} onChange={(ev) => setForm({ ...form, reference: ev.target.value })} /></label>
          </div>
          {form.paid_from === 'cash' ? <div className="cap muted">{t('fin.cashBranch', { b: branch ? nameOf(branch, lang) : '' })}</div> :
            <label className="chk">{t('fin.forBranch', { b: branch ? nameOf(branch, lang) : '' })}<input type="checkbox" className="sw" checked={form.branch} onChange={(ev) => setForm({ ...form, branch: ev.target.checked })} /></label>}
          <ErrorText error={s.error} />
        </>}
      </Dialog>
      <Dialog open={!!pay} title={t('inv2.pay')} onClose={() => setPay(null)} busy={s.busy}
        onSubmit={() => s.save({ path: `/accounting/expenses/${pay!.x.id}/pay`, idempotencyKey: key, body: { paid_on: pay!.paid_on, reference: pay!.reference } })}>
        {pay && <>
          <div className="small muted">{pay.x.description} · {formatKWD(pay.x.amount, lang)}</div>
          <div className="two">
            <label className="field">{t('acc.date')}<input className="input" type="date" value={pay.paid_on} onChange={(ev) => setPay({ ...pay, paid_on: ev.target.value })} required /></label>
            <label className="field">{t('pos.transferRef')}<input className="input" dir="ltr" value={pay.reference} onChange={(ev) => setPay({ ...pay, reference: ev.target.value })} required /></label>
          </div>
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}

export function Assets() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const { e, q } = useEntity()
  const list = useQuery({ enabled: !!e, queryKey: ['assets', e?.id], queryFn: () => api<Asset[]>(`/accounting/assets${q}`) })
  const [form, setForm] = useState<{ name: string; acquired_on: string; cost: string; residual_value: string; life_months: number; paid_from: string; reference: string } | null>(null)
  const [month, setMonth] = useState(today().slice(0, 7))
  const [key, setKey] = useState(() => crypto.randomUUID())
  const s = useSave<Asset>([['assets']], () => { setForm(null); setKey(crypto.randomUUID()); toast(t('common.saved')) })
  const dep = useSave<{ posted: number; already_posted: number; total: string }>([['assets']], (r) => toast(t('fin.depDone', { n: r.posted, a: r.already_posted, v: formatKWD(r.total, lang) })))
  const rows = list.data ?? []
  const post = can('accounting.journal.post')
  return (
    <>
      <Head title={t('nav.assets')} sub={t('fin.assetSub')}>
        {post && <button className="btn primary" onClick={() => { s.reset(); setForm({ name: '', acquired_on: today(), cost: '', residual_value: '0', life_months: 60, paid_from: 'bank', reference: '' }) }}><Icon name="plus" />{t('fin.addAsset')}</button>}
      </Head>
      <div className="grid stats" style={{ marginBottom: 14 }}>
        <Stat label={t('fin.totalCost')} value={formatKWD(rows.reduce((a, x) => a + Number(x.cost), 0).toFixed(3), lang)} />
        <Stat label={t('fin.accDep')} value={formatKWD(rows.reduce((a, x) => a + Number(x.accumulated), 0).toFixed(3), lang)} />
        <Stat label={t('fin.bookValue')} value={formatKWD(rows.reduce((a, x) => a + Number(x.book_value), 0).toFixed(3), lang)} />
      </div>
      {post && <div className="card row" style={{ marginBottom: 14 }}>
        <span className="grow small">{t('fin.depHelp')}</span>
        <input className="input" type="month" style={{ width: 'auto' }} value={month} onChange={(ev) => setMonth(ev.target.value)} />
        <button className="btn" disabled={dep.busy} onClick={() => dep.save({ path: `/accounting/depreciation${q}`, body: { month } })}>{t('fin.runDep')}</button>
      </div>}
      <ErrorText error={list.error || dep.error} />
      <div className="tw"><table><thead><tr><th>{t('fin.asset')}</th><th>{t('fin.acquired')}</th><th className="n">{t('fin.cost')}</th><th>{t('fin.life')}</th><th className="n">{t('fin.monthly')}</th><th className="n">{t('fin.accDep')}</th><th className="n">{t('fin.bookValue')}</th></tr></thead>
        <tbody>{rows.map((a) => <tr key={a.id}><td><b>{a.name}</b></td><td className="num">{a.acquired_on}</td><td className="n money">{formatKWD(a.cost, lang)}</td>
          <td>{t('fin.months', { n: a.life_months })}</td><td className="n money">{formatKWD(a.monthly, lang)}</td><td className="n money">{formatKWD(a.accumulated, lang)}</td><td className="n money">{formatKWD(a.book_value, lang)}</td></tr>)}
          {rows.length === 0 && <tr><td colSpan={7} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>
      <Dialog open={!!form} title={t('fin.addAsset')} onClose={() => setForm(null)} busy={s.busy} onSubmit={() => s.save({ path: `/accounting/assets${q}`, idempotencyKey: key, body: form })}>
        {form && <>
          <label className="field">{t('fin.asset')}<input className="input" value={form.name} onChange={(ev) => setForm({ ...form, name: ev.target.value })} required /></label>
          <div className="two">
            <label className="field">{t('fin.acquired')}<input className="input" type="date" value={form.acquired_on} onChange={(ev) => setForm({ ...form, acquired_on: ev.target.value })} required /></label>
            <label className="field">{t('fin.cost')} (KWD)<input className="input" dir="ltr" inputMode="decimal" value={form.cost} onChange={(ev) => setForm({ ...form, cost: ev.target.value })} required /></label>
          </div>
          <div className="two">
            <label className="field">{t('fin.lifeMonths')}<input className="input" type="number" min={1} value={form.life_months} onChange={(ev) => setForm({ ...form, life_months: Number(ev.target.value) })} /></label>
            <label className="field">{t('fin.residual')}<input className="input" dir="ltr" inputMode="decimal" value={form.residual_value} onChange={(ev) => setForm({ ...form, residual_value: ev.target.value })} /></label>
          </div>
          <div className="two">
            <label className="field">{t('fin.paidFrom')}<select className="input" value={form.paid_from} onChange={(ev) => setForm({ ...form, paid_from: ev.target.value })}>
              <option value="bank">{t('fin.pf.bank')}</option><option value="payable">{t('fin.pf.payable')}</option></select></label>
            <label className="field">{t('fin.reference')}<input className="input" dir="ltr" value={form.reference} onChange={(ev) => setForm({ ...form, reference: ev.target.value })} /></label>
          </div>
          {form.cost && form.life_months > 0 && <div className="small muted">{t('fin.preview', { v: formatKWD(((Number(form.cost) - Number(form.residual_value || 0)) / form.life_months).toFixed(3), lang) })}</div>}
          <div className="cap muted">{t('fin.capPolicy')}</div>
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}

export function Settlements() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const { e, q } = useEntity()
  const data = useQuery({ enabled: !!e, queryKey: ['settlements', e?.id], queryFn: () => api<{ status: { channel: string; account: string; open_balance: string; last_settlement: string | null }[]
    settlements: { id: number; channel: string; settled_on: string; gross: string; fees: string; net: string; reference: string }[] }>(`/accounting/settlements${q}`) })
  const [form, setForm] = useState<{ channel: string; settled_on: string; gross: string; fees: string; reference: string } | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const s = useSave<unknown>([['settlements']], () => { setForm(null); setKey(crypto.randomUUID()); toast(t('common.saved')) })
  return (
    <>
      <Head title={t('nav.settlements')} sub={t('fin.setSub')}>
        {can('accounting.journal.post') && <button className="btn primary" onClick={() => { s.reset(); setForm({ channel: 'knet', settled_on: today(), gross: '', fees: '', reference: '' }) }}><Icon name="plus" />{t('fin.addSettlement')}</button>}
      </Head>
      <ErrorText error={data.error} />
      <div className="grid stats" style={{ marginBottom: 14 }}>{data.data?.status.map((x) => <Stat key={x.channel} label={t('fin.openIn', { c: t(`fin.ch.${x.channel}`) })}
        value={<>{formatKWD(x.open_balance, lang)}<div className="cap muted">{x.last_settlement ? t('fin.lastSettled', { d: x.last_settlement }) : t('fin.neverSettled')}</div></>} />)}</div>
      <div className="notice info"><Icon name="info" />{t('fin.setRule')}</div>
      <div className="tw"><table><thead><tr><th>{t('acc.date')}</th><th>{t('fin.channel')}</th><th>{t('fin.reference')}</th><th className="n">{t('fin.gross')}</th><th className="n">{t('fin.fees')}</th><th className="n">{t('fin.net')}</th></tr></thead>
        <tbody>{data.data?.settlements.map((x) => <tr key={x.id}><td className="num">{x.settled_on}</td><td>{t(`fin.ch.${x.channel}`)}</td><td className="code">{x.reference}</td>
          <td className="n money">{formatKWD(x.gross, lang)}</td><td className="n money">{formatKWD(x.fees, lang)}</td><td className="n money">{formatKWD(x.net, lang)}</td></tr>)}
          {data.data?.settlements.length === 0 && <tr><td colSpan={6} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>
      <Dialog open={!!form} title={t('fin.addSettlement')} onClose={() => setForm(null)} busy={s.busy} onSubmit={() => s.save({ path: `/accounting/settlements${q}`, idempotencyKey: key, body: form })}>
        {form && <>
          <div className="two">
            <label className="field">{t('fin.channel')}<select className="input" value={form.channel} onChange={(ev) => setForm({ ...form, channel: ev.target.value })}>
              <option value="knet">{t('fin.ch.knet')}</option><option value="gateway">{t('fin.ch.gateway')}</option></select></label>
            <label className="field">{t('acc.date')}<input className="input" type="date" value={form.settled_on} onChange={(ev) => setForm({ ...form, settled_on: ev.target.value })} required /></label>
          </div>
          <div className="two">
            <label className="field">{t('fin.gross')}<input className="input" dir="ltr" inputMode="decimal" value={form.gross} onChange={(ev) => setForm({ ...form, gross: ev.target.value })} required /></label>
            <label className="field">{t('fin.fees')}<input className="input" dir="ltr" inputMode="decimal" value={form.fees} onChange={(ev) => setForm({ ...form, fees: ev.target.value })} /></label>
          </div>
          <label className="field">{t('fin.providerRef')}<input className="input" dir="ltr" value={form.reference} onChange={(ev) => setForm({ ...form, reference: ev.target.value })} required /></label>
          {form.gross && <div className="small muted">{t('fin.bankGets', { v: formatKWD((Number(form.gross) - Number(form.fees || 0)).toFixed(3), lang) })}</div>}
          <ErrorText error={s.error} />
        </>}
      </Dialog>
    </>
  )
}

function Lines({ rows, lang }: { rows: Row[]; lang: 'ar' | 'en' }) {
  return <>{rows.map((r) => <div className="r" key={r.account_id}><span><span className="num muted">{r.code}</span> {lang === 'en' ? r.name_en : r.name_ar}</span><span className="money">{formatKWD(r.amount, lang)}</span></div>)}</>
}

export function Statements() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const { e, q } = useEntity()
  const [tab, setTab] = useState<'pl' | 'bs' | 'versions'>('pl')
  const [range, setRange] = useState({ from: `${thisYear()}-01-01`, to: today(), as_of: today() })
  const pl = useQuery({ enabled: !!e && tab === 'pl', queryKey: ['is', e?.id, range.from, range.to], queryFn: () => api<Income>(`/accounting/income-statement${q}&from=${range.from}&to=${range.to}`) })
  const bs = useQuery({ enabled: !!e && tab === 'bs', queryKey: ['bs', e?.id, range.as_of], queryFn: () => api<Balance>(`/accounting/balance-sheet${q}&as_of=${range.as_of}`) })
  const vers = useQuery({ enabled: !!e && tab === 'versions', queryKey: ['versions', e?.id], queryFn: () => api<Version[]>(`/accounting/report-versions${q}`) })
  const [note, setNote] = useState('')
  const [view, setView] = useState<number | null>(null)
  const one = useQuery({ enabled: !!view, queryKey: ['version', view], queryFn: () => api<{ data: Income & Balance; kind: string; intact: boolean; sha256: string; params: Record<string, string> }>(`/accounting/report-versions/${view}`) })
  const fz = useSave<{ id: number; sha256: string }>([['versions']], () => { setNote(''); toast(t('fin.frozen')) })
  const freeze = () => fz.save({ path: `/accounting/report-versions${q}`, body: tab === 'pl'
    ? { kind: 'income_statement', params: { from: range.from, to: range.to }, note } : { kind: 'balance_sheet', params: { as_of: range.as_of }, note } })
  const statement = (d: Income | Balance | undefined, kind: string) => !d ? null : kind === 'income_statement' || 'revenue' in d ? (() => {
    const x = d as Income
    return <div className="card stmt">
      <b>{t('fin.revenue')}</b><Lines rows={x.revenue} lang={lang} /><div className="r"><b>{t('fin.totalRevenue')}</b><b className="money">{formatKWD(x.total_revenue, lang)}</b></div><hr />
      <b>{t('fin.expenses')}</b><Lines rows={x.expenses} lang={lang} /><div className="r"><b>{t('fin.totalExpenses')}</b><b className="money">{formatKWD(x.total_expenses, lang)}</b></div><hr />
      <div className="r"><span>{t('fin.grossProfit')}</span><span className="money">{formatKWD(x.gross_profit, lang)}</span></div>
      <div className="r"><b>{t('fin.netProfit')}</b><b className="money" style={{ color: Number(x.net_profit) < 0 ? 'var(--danger)' : undefined }}>{formatKWD(x.net_profit, lang)}</b></div>
    </div>
  })() : (() => {
    const x = d as Balance
    return <div className="card stmt">
      <b>{t('fin.assets')}</b><Lines rows={x.assets} lang={lang} /><div className="r"><b>{t('fin.totalAssets')}</b><b className="money">{formatKWD(x.total_assets, lang)}</b></div><hr />
      <b>{t('fin.liabilities')}</b><Lines rows={x.liabilities} lang={lang} /><div className="r"><b>{t('fin.totalLiabilities')}</b><b className="money">{formatKWD(x.total_liabilities, lang)}</b></div><hr />
      <b>{t('fin.equity')}</b><Lines rows={x.equity} lang={lang} />
      {x.unclosed_profit !== '0.000' && <div className="r"><span>{t('fin.unclosedProfit')}</span><span className="money">{formatKWD(x.unclosed_profit, lang)}</span></div>}
      <div className="r"><b>{t('fin.totalEquity')}</b><b className="money">{formatKWD(x.total_equity, lang)}</b></div>
      <div className="r"><span className={`pill ${x.balanced ? 'good' : 'bad'}`}>{t(x.balanced ? 'acc.balanced' : 'acc.unbalanced')}</span></div>
    </div>
  })()
  return (
    <>
      <Head title={t('nav.statements')} sub={t('fin.stSub')} />
      <div className="notice"><Icon name="alert" />{t('fin.draftNote')}</div>
      <div className="tabs">{(['pl', 'bs', 'versions'] as const).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`fin.tab.${x}`)}</button>)}</div>
      {tab !== 'versions' && <div className="row" style={{ marginBottom: 14 }}>
        {tab === 'pl' ? <>
          <label className="field">{t('acc.from')}<input className="input" type="date" value={range.from} onChange={(ev) => setRange({ ...range, from: ev.target.value })} /></label>
          <label className="field">{t('acc.to')}<input className="input" type="date" value={range.to} onChange={(ev) => setRange({ ...range, to: ev.target.value })} /></label>
        </> : <label className="field">{t('fin.asOf')}<input className="input" type="date" value={range.as_of} onChange={(ev) => setRange({ ...range, as_of: ev.target.value })} /></label>}
        {can('accounting.journal.post') && <>
          <input className="input" style={{ width: 220 }} placeholder={t('fin.versionNote')} value={note} onChange={(ev) => setNote(ev.target.value)} />
          <button className="btn" disabled={fz.busy} onClick={freeze}><Icon name="shield" />{t('fin.freeze')}</button></>}
      </div>}
      <ErrorText error={pl.error || bs.error || fz.error || vers.error} />
      {tab === 'pl' && statement(pl.data, 'income_statement')}
      {tab === 'bs' && statement(bs.data, 'balance_sheet')}
      {tab === 'versions' && <div className="tw"><table><thead><tr><th>#</th><th>{t('fin.kind')}</th><th>{t('fin.params')}</th><th>{t('cust.notes')}</th><th>{t('fin.by')}</th><th>SHA-256</th></tr></thead>
        <tbody>{vers.data?.map((v) => <tr key={v.id} className="click" onClick={() => setView(v.id)}><td className="num">{v.id}</td><td>{t(`fin.k.${v.kind}`)}</td>
          <td className="small num">{Object.values(v.params).join(' → ')}</td><td className="small">{v.note}</td><td className="small">{v.created_by}<div className="cap muted">{new Date(v.created_at).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { timeZone: 'Asia/Kuwait' })}</div></td>
          <td className="code small" dir="ltr">{v.sha256.slice(0, 12)}…</td></tr>)}
          {vers.data?.length === 0 && <tr><td colSpan={6} className="empty">{t('common.empty')}</td></tr>}</tbody></table></div>}
      <Dialog open={!!view} wide title={one.data ? `${t(`fin.k.${one.data.kind}`)} · ${Object.values(one.data.params).join(' → ')}` : ''} onClose={() => setView(null)}>
        {one.data && <>
          <span className={`pill ${one.data.intact ? 'good' : 'bad'}`}>{t(one.data.intact ? 'fin.intact' : 'fin.tampered')}</span>
          {one.data.kind === 'xbrl' ? <div className="small muted">{t('fin.xbrlFrozen')}</div> : statement(one.data.data, one.data.kind)}
        </>}
      </Dialog>
    </>
  )
}

export function Periods() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const { e, q } = useEntity()
  const years = useQuery({ enabled: !!e, queryKey: ['periods', e?.id], queryFn: () => api<Year[]>(`/accounting/periods${q}`) })
  const [reopen, setReopen] = useState<{ id: number; reason: string } | null>(null)
  const [closeYear, setCloseYear] = useState<Year | null>(null)
  const s = useSave<unknown>([['periods']], () => { setReopen(null); setCloseYear(null); toast(t('common.saved')) })
  const allowed = can('accounting.period.close')
  const month = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString(lang === 'ar' ? 'ar-KW' : 'en-GB', { month: 'long', year: 'numeric' })
  return (
    <>
      <Head title={t('nav.periods')} sub={t('fin.perSub')} />
      <ErrorText error={years.error || s.error} />
      {years.data?.map((y) => <div className="card" key={y.id} style={{ marginBottom: 14 }}>
        <div className="row sb"><h2>{t('fin.fy', { n: y.name })} <span className="small muted"><bdi>{y.start_date}</bdi> → <bdi>{y.end_date}</bdi></span></h2>
          {y.closing_entry ? <span className="pill good">{t('fin.yearClosed', { n: y.closing_entry })}</span>
            : allowed && <button className="btn sm" onClick={() => { s.reset(); setCloseYear(y) }}>{t('fin.closeYear')}</button>}</div>
        <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(170px,1fr))' }}>{y.periods.map((p) => <div className="li" key={p.id} style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
          <div className="grow"><b className="small">{month(p.start_date)}</b><div><span className={`pill ${p.status === 'closed' ? 'mute' : 'good'}`}>{t(`fin.ps.${p.status}`)}</span></div></div>
          {allowed && (p.status === 'open'
            ? <button className="btn sm" disabled={s.busy} onClick={() => s.save({ path: `/accounting/periods/${p.id}/close`, body: {} })}>{t('fin.close')}</button>
            : <button className="btn sm ghost" onClick={() => { s.reset(); setReopen({ id: p.id, reason: '' }) }}>{t('fin.reopen')}</button>)}
        </div>)}</div>
      </div>)}
      <Dialog open={!!reopen} title={t('fin.reopen')} onClose={() => setReopen(null)} busy={s.busy} onSubmit={() => s.save({ path: `/accounting/periods/${reopen!.id}/reopen`, body: { reason: reopen!.reason } })}>
        {reopen && <><div className="small muted">{t('fin.reopenHelp')}</div>
          <label className="field">{t('book.reason')}<input className="input" value={reopen.reason} onChange={(ev) => setReopen({ ...reopen, reason: ev.target.value })} required /></label>
          <ErrorText error={s.error} /></>}
      </Dialog>
      <Dialog open={!!closeYear} title={closeYear ? t('fin.closeYearQ', { n: closeYear.name }) : ''} onClose={() => setCloseYear(null)} busy={s.busy}
        submitLabel={t('fin.closeYear')} onSubmit={() => s.save({ path: `/accounting/years/${closeYear!.id}/close` })}>
        <div className="small">{t('fin.closeYearHelp')}</div>
        <ErrorText error={s.error} />
      </Dialog>
    </>
  )
}
