import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api, type Appointment, type Invoice } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { Head, Icon, nameOf, Stat } from '../components/ui'
import { formatKWD } from '../money'

type Sales = {
  from: string; to: string
  stats: { sales: string; invoices: number; average: string; discounts: string; returns: string; tips: string; customers: number }
  days: { date: string; total: string }[]; items: { name_ar: string; name_en: string; qty: number; total: string }[]
  staff: { staff_id: number; name_ar: string; name_en: string; count: number; total: string }[]
  methods: { method: string; total: string }[]; hours: { hour: number; invoices: number }[]
  profit?: { sales: string; cogs: string; commissions: string; expenses: string; net: string }
}
type BranchRow = { branch_id: number; name_ar: string; name_en: string; today: string; invoices_today: number; waiting: number; in_service: number; month: string; drawer_open: boolean }
type Range = 'today' | 'week' | 'month'

const kwToday = () => new Date(Date.now() - 4 * 3600e3).toLocaleDateString('en-CA', { timeZone: 'Asia/Kuwait' })   // business day starts 04:00
const rangeOf = (r: Range) => {
  const to = kwToday()
  const d = new Date(to + 'T00:00:00')
  if (r === 'today') return { from: to, to }
  if (r === 'week') { d.setDate(d.getDate() - 6); return { from: d.toLocaleDateString('en-CA'), to } }
  return { from: to.slice(0, 8) + '01', to }
}

function Bars({ rows, fmt }: { rows: [string, number, string][]; fmt?: (v: string) => string }) {
  const max = Math.max(1, ...rows.map((r) => r[1]))
  if (!rows.length) return <div className="empty small">—</div>
  return <div className="bars">{rows.map(([l, v, shown]) => <div className="bar" key={l}><span>{l}</span><span className="t"><i style={{ width: `${(v / max) * 100}%` }} /></span>
    <span className="small">{fmt ? fmt(shown) : shown}</span></div>)}</div>
}

function Days({ days, lang }: { days: Sales['days']; lang: 'ar' | 'en' }) {
  const max = Math.max(1, ...days.map((d) => Number(d.total)))
  return <div className="days">{days.slice(-31).map((d) => <div key={d.date} title={formatKWD(d.total, lang)}>
    <span style={{ height: `${(Number(d.total) / max) * 85}%` }} />{d.date.slice(8)}</div>)}</div>
}

export function useSales(range: Range, branchId?: number) {
  const r = rangeOf(range)
  return useQuery({ queryKey: ['rep', range, branchId ?? 'all', r.to], queryFn: () => api<Sales>(`/reports/sales?from=${r.from}&to=${r.to}${branchId ? `&branch_id=${branchId}` : ''}`) })
}

/** Branch reports (reference v-rep); with all branches it also compares them (v-c-rep). */
export default function Reports() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { membership } = useAuth()
  const { branch } = useBranch()
  const [range, setRange] = useState<Range>('month')
  const [scope, setScope] = useState<'branch' | 'all'>('branch')
  const company = !!membership?.all_branches
  const q = useSales(range, scope === 'all' && company ? undefined : branch?.id)
  const branches = useQuery({ enabled: company && scope === 'all', queryKey: ['rep-branches'], queryFn: () => api<BranchRow[]>('/reports/branches') })
  const d = q.data
  const csv = () => {
    if (!d) return
    const rows = [['section', 'name', 'qty', 'total'], ...d.days.map((x) => ['day', x.date, '', x.total]), ...d.items.map((x) => ['item', x.name_ar, String(x.qty), x.total]),
      ...d.staff.map((x) => ['staff', x.name_ar, String(x.count), x.total]), ...d.methods.map((x) => ['method', x.method, '', x.total])]
    const blob = new Blob(['﻿' + rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `qassa-report-${d.from}-${d.to}.csv`; a.click()
  }
  return (
    <>
      <Head title={t('nav.reports')} sub={d ? `\u2068${d.from}\u2069 – \u2068${d.to}\u2069` : ''}>
        {company && <div className="seg">{(['branch', 'all'] as const).map((x) => <button key={x} className={scope === x ? 'on' : ''} onClick={() => setScope(x)}>{x === 'branch' && branch ? nameOf(branch, lang) : t('rep.allBranches')}</button>)}</div>}
        <div className="seg">{(['today', 'week', 'month'] as Range[]).map((x) => <button key={x} className={range === x ? 'on' : ''} onClick={() => setRange(x)}>{t(`rep.r.${x}`)}</button>)}</div>
        <button className="btn sm" onClick={csv}><Icon name="download" />CSV</button>
      </Head>
      <ErrorText error={q.error} />
      {d && <>
        <div className="grid stats">
          <Stat label={t('rep.sales')} value={<>{formatKWD(d.stats.sales, lang)}{d.stats.returns !== '0.000' && <div className="cap muted">{t('rep.afterReturns', { v: formatKWD(d.stats.returns, lang) })}</div>}</>} />
          <Stat label={t('rep.invoices')} value={<bdi>{d.stats.invoices}</bdi>} />
          <Stat label={t('rep.average')} value={formatKWD(d.stats.average, lang)} />
          <Stat label={t('rep.customers')} value={<><bdi>{d.stats.customers}</bdi><div className="cap muted">{t('rep.discounts', { v: formatKWD(d.stats.discounts, lang) })}</div></>} />
        </div>
        {scope === 'all' && branches.data && <>
          <h2 style={{ margin: '18px 0 10px' }}>{t('rep.compare')}</h2>
          <div className="tw"><table><thead><tr><th>{t('acc.branch')}</th><th className="n">{t('rep.today')}</th><th className="n">{t('rep.invoices')}</th><th className="n">{t('rep.month')}</th></tr></thead>
            <tbody>{branches.data.map((b) => <tr key={b.branch_id}><td><b>{nameOf(b, lang)}</b></td><td className="n money">{formatKWD(b.today, lang)}</td><td className="n"><bdi>{b.invoices_today}</bdi></td><td className="n money">{formatKWD(b.month, lang)}</td></tr>)}</tbody></table></div>
        </>}
        <div className="grid g2" style={{ marginTop: 14 }}>
          <div className="card"><h2>{t('rep.daily')}</h2><Days days={d.days} lang={lang} /></div>
          <div className="card"><h2 style={{ marginBottom: 12 }}>{t('rep.top')}</h2><Bars rows={d.items.map((x) => [nameOf(x, lang), Number(x.total), x.total])} fmt={(v) => formatKWD(v, lang)} /></div>
          <div className="card"><h2 style={{ marginBottom: 12 }}>{t('rep.byStaff')}</h2><Bars rows={d.staff.map((x) => [lang === 'en' && x.name_en ? x.name_en : x.name_ar, Number(x.total), x.total])} fmt={(v) => formatKWD(v, lang)} /></div>
          <div className="card"><h2 style={{ marginBottom: 12 }}>{t('rep.methods')}</h2><Bars rows={d.methods.map((x) => [t(`pos.m.${x.method}`), Number(x.total), x.total])} fmt={(v) => formatKWD(v, lang)} /></div>
          <div className="card"><h2 style={{ marginBottom: 12 }}>{t('rep.peak')}</h2><Bars rows={d.hours.map((x) => [`${String(x.hour).padStart(2, '0')}:00`, x.invoices, String(x.invoices)])} /></div>
          {d.profit && <div className="card stmt"><h2>{t('rep.profit')}</h2>
            <div className="r"><span>{t('rep.sales')}</span><span className="money">{formatKWD(d.profit.sales, lang)}</span></div>
            <div className="r"><span>{t('rep.cogs')}</span><span className="money">-{formatKWD(d.profit.cogs, lang)}</span></div>
            <div className="r"><span>{t('nav.commissions')}</span><span className="money">-{formatKWD(d.profit.commissions, lang)}</span></div>
            <div className="r"><span>{t('nav.expenses')}</span><span className="money">-{formatKWD(d.profit.expenses, lang)}</span></div>
            <hr /><div className="r"><b>{t('rep.net')}</b><b className="money">{formatKWD(d.profit.net, lang)}</b></div>
            <div className="cap muted">{t('rep.profitNote')}</div></div>}
        </div>
      </>}
    </>
  )
}

/** Branch home (reference v-home): today's numbers, the live queue and the latest invoices. */
export function Home() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { me, can } = useAuth()
  const { branch } = useBranch()
  const nav = useNavigate()
  const today = kwToday()
  const sales = useSales('today', branch?.id)
  const appts = useQuery({ enabled: !!branch && can('booking.view'), queryKey: ['appointments', branch?.id, today], refetchInterval: 30000,
    queryFn: () => api<Appointment[]>(`/booking/appointments?branch_id=${branch!.id}&date=${today}`) })
  const invs = useQuery({ enabled: !!branch && can('pos.invoices.view'), queryKey: ['invoices', branch?.id, today],
    queryFn: () => api<Invoice[]>(`/pos/invoices?branch_id=${branch!.id}&date=${today}`) })
  const queue = (appts.data ?? []).filter((a) => ['booked', 'arrived', 'in_service'].includes(a.status))
  const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuwait' })
  const hour = Number(new Date().toLocaleTimeString('en-GB', { hour: '2-digit', timeZone: 'Asia/Kuwait' }))
  if (!branch) return <p className="muted">{t('common.loading')}</p>
  return (
    <>
      <Head title={t(hour < 12 ? 'home.morning' : 'home.evening', { name: (me?.full_name || '').split(' ')[0] })}
        sub={`${nameOf(branch, lang)} · ${new Date().toLocaleDateString(lang === 'ar' ? 'ar-KW' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kuwait' })}`}>
        {can('booking.manage') && <button className="btn" onClick={() => nav('/bookings')}><Icon name="plus" />{t('home.booking')}</button>}
        {can('pos.sell') && <button className="btn brand" onClick={() => nav('/pos')}><Icon name="cart" />{t('home.sale')}</button>}
      </Head>
      {sales.data && <div className="grid stats">
        <Stat label={t('home.salesToday')} value={formatKWD(sales.data.stats.sales, lang)} />
        <Stat label={t('rep.invoices')} value={<bdi>{sales.data.stats.invoices}</bdi>} />
        <Stat label={t('home.waiting')} value={<bdi>{queue.filter((a) => a.status !== 'in_service').length}</bdi>} />
        <Stat label={t('home.onChair')} value={<bdi>{queue.filter((a) => a.status === 'in_service').length}</bdi>} />
      </div>}
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card"><div className="row sb" style={{ marginBottom: 6 }}><h2>{t('home.queue')}</h2><button className="btn sm ghost" onClick={() => nav('/bookings')}>{t('home.allBookings')}</button></div>
          <div className="list">{queue.slice(0, 8).map((a) => <div className="li" key={a.id}><span className="av">{(a.beneficiary_name || a.customer_name || '?')[0]}</span>
            <div className="grow"><b className="small">{a.beneficiary_name || a.customer_name}</b><div className="cap muted">{a.items.map((i) => nameOf({ name_ar: i.service_name_ar, name_en: i.service_name_en }, lang)).join('، ')}</div></div>
            <span className={`pill ${a.status === 'in_service' ? 'good' : a.status === 'arrived' ? 'warn' : 'mute'}`}>{a.status === 'booked' ? hhmm(a.starts_at) : t(`book.st.${a.status}`)}</span></div>)}
            {queue.length === 0 && <div className="small muted">{t('home.noQueue')}</div>}</div></div>
        <div className="card"><div className="row sb" style={{ marginBottom: 6 }}><h2>{t('home.latest')}</h2><button className="btn sm ghost" onClick={() => nav('/invoices')}>{t('home.all')}</button></div>
          <div className="list">{(invs.data ?? []).slice(0, 8).map((i) => <div className="li" key={i.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/invoices?open=${i.id}`)}>
            <Icon name="receipt" /><div className="grow"><b className="small num">{i.number}</b><div className="cap muted">{i.beneficiary_name || i.customer_name || t('home.walkIn')} · {hhmm(i.issued_at)}</div></div>
            <b className="money small">{formatKWD(i.total, lang)}</b></div>)}
            {invs.data?.length === 0 && <div className="small muted">{t('home.noInvoices')}</div>}</div></div>
      </div>
    </>
  )
}

/** Company home for owners and operations (reference v-c-home): every branch today and this month. */
export function CompanyHome() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { membership } = useAuth()
  const { setBranchId } = useBranch()
  const nav = useNavigate()
  const rows = useQuery({ queryKey: ['rep-branches'], refetchInterval: 60000, queryFn: () => api<BranchRow[]>('/reports/branches') })
  const month = useSales('month')
  const data = rows.data ?? []
  const sum = (k: 'today' | 'month') => data.reduce((a, r) => a + Number(r[k]), 0).toFixed(3)
  return (
    <>
      <Head title={membership?.tenant_name ?? ''} sub={t('home.companySub')}>
        <button className="btn" onClick={() => nav('/reports')}><Icon name="chart" />{t('nav.reports')}</button>
      </Head>
      <ErrorText error={rows.error} />
      <div className="grid stats">
        <Stat label={t('home.salesToday')} value={formatKWD(sum('today'), lang)} />
        <Stat label={t('home.salesMonth')} value={formatKWD(sum('month'), lang)} />
        <Stat label={t('home.waiting')} value={<bdi>{data.reduce((a, r) => a + r.waiting, 0)}</bdi>} />
        <Stat label={t('home.openDrawers')} value={<bdi>{data.filter((r) => r.drawer_open).length} / {data.length}</bdi>} />
      </div>
      <h2 style={{ margin: '18px 0 10px' }}>{t('home.branchesToday')}</h2>
      <div className="tw"><table><thead><tr><th>{t('acc.branch')}</th><th className="n">{t('rep.today')}</th><th className="n">{t('rep.invoices')}</th><th className="n">{t('home.waiting')}</th><th className="n">{t('rep.month')}</th><th>{t('nav.cash')}</th><th /></tr></thead>
        <tbody>{data.map((r) => <tr key={r.branch_id}><td><b>{nameOf(r, lang)}</b></td><td className="n money">{formatKWD(r.today, lang)}</td><td className="n"><bdi>{r.invoices_today}</bdi></td>
          <td className="n"><bdi>{r.waiting}</bdi>{r.in_service > 0 && <span className="cap muted"> + {r.in_service}</span>}</td><td className="n money">{formatKWD(r.month, lang)}</td>
          <td>{r.drawer_open ? <span className="pill good">{t('home.drawerOpen')}</span> : <span className="pill mute">{t('home.drawerClosed')}</span>}</td>
          <td><button className="btn sm ghost" onClick={() => { setBranchId(r.branch_id); nav('/home') }}>{t('home.open')}</button></td></tr>)}</tbody></table></div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card"><h2 style={{ marginBottom: 12 }}>{t('home.monthByBranch')}</h2><Bars rows={data.map((r) => [nameOf(r, lang), Number(r.month), r.month])} fmt={(v) => formatKWD(v, lang)} /></div>
        <div className="card"><h2 style={{ marginBottom: 12 }}>{t('home.bestStaff')}</h2>{month.data && <Bars rows={month.data.staff.slice(0, 6).map((x) => [lang === 'en' && x.name_en ? x.name_en : x.name_ar, Number(x.total), x.total])} fmt={(v) => formatKWD(v, lang)} />}</div>
      </div>
    </>
  )
}
