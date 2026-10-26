import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api, type Appointment, type ApptStatus, type Customer, type Service, type Staff } from '../api/client'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Head, Icon, nameOf, useToast } from '../components/ui'

const todayISO = () => new Date(Date.now() - 4 * 3600e3).toISOString().slice(0, 10)  // business day starts 04:00
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuwait' })

export function useServicesStaff() {
  const { branch } = useBranch()
  const services = useQuery({ queryKey: ['services'], queryFn: () => api<Service[]>('/catalog/services') })
  const staff = useQuery({ queryKey: ['staff'], queryFn: () => api<Staff[]>('/staff') })
  const branchServices = (services.data ?? []).filter((s) => s.is_active && s.business_type === branch?.business_type)
  const staffFor = (serviceId: number) => (staff.data ?? []).filter((p) => p.is_active && branch && p.branch_ids.includes(branch.id) && p.service_ids.includes(serviceId))
  return { services: services.data ?? [], staff: staff.data ?? [], branchServices, staffFor }
}

type Row = { service_id: number; staff_id: number }

function NewBooking({ onClose, date }: { onClose: () => void; date: string }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const { branch } = useBranch()
  const { branchServices, staffFor } = useServicesStaff()
  const [walkIn, setWalkIn] = useState(false)
  const [q, setQ] = useState('')
  const [cust, setCust] = useState<Customer | null>(null)
  const [beneficiary, setBeneficiary] = useState<number | ''>('')
  const [walkName, setWalkName] = useState('')
  const [time, setTime] = useState('10:00')
  const [rows, setRows] = useState<Row[]>([{ service_id: 0, staff_id: 0 }])
  const [key] = useState(() => crypto.randomUUID())
  const found = useQuery({ queryKey: ['customers', q], enabled: q.length >= 2 && !cust, queryFn: () => api<Customer[]>(`/customers?q=${encodeURIComponent(q)}`) })
  const { save, busy, error } = useSave<Appointment>([['appointments']], () => { toast(t('book.saved')); onClose() })
  const setRow = (i: number, r: Partial<Row>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...r } : x)))
  const submit = () => {
    const starts = walkIn ? new Date() : new Date(`${date}T${time}:00+03:00`)
    save({ path: '/booking/appointments', idempotencyKey: key, body: {
      branch_id: branch!.id, starts_at: starts.toISOString(), source: walkIn ? 'walk_in' : 'reception',
      customer_id: cust?.id ?? null, beneficiary_id: beneficiary || null, walk_in_name: cust ? '' : walkName,
      items: rows.filter((r) => r.service_id && r.staff_id) } })
  }
  return (
    <Dialog open wide title={t('book.new')} onClose={onClose} onSubmit={submit} busy={busy} submitLabel={walkIn ? t('book.addQueue') : t('book.confirm')}>
      <div className="seg"><button type="button" className={!walkIn ? 'on' : ''} onClick={() => setWalkIn(false)}>{t('book.appointment')}</button>
        <button type="button" className={walkIn ? 'on' : ''} onClick={() => setWalkIn(true)}>{t('book.walkIn')}</button></div>
      {cust ? <div className="li"><span className="av">{cust.full_name[0]}</span><div className="grow"><b>{cust.full_name}</b> <bdi className="cap muted">+{cust.phone}</bdi></div>
        <button type="button" className="btn sm" onClick={() => { setCust(null); setBeneficiary('') }}>{t('common.change')}</button></div> : <>
        <label className="field">{t('book.findCustomer')}<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('cust.search')} /></label>
        {found.data && found.data.length > 0 && <div className="list">{found.data.slice(0, 5).map((c) => <button type="button" key={c.id} className="li btn ghost" style={{ justifyContent: 'flex-start' }}
          onClick={() => { setCust(c); setBeneficiary(c.beneficiaries.find((b) => b.relation !== 'self')?.id ?? c.beneficiaries[0]?.id ?? '') }}>
          <b>{c.full_name}</b> <bdi className="cap muted">+{c.phone}</bdi> <span className="cap muted">{c.beneficiaries.filter((b) => b.relation !== 'self').map((b) => b.full_name).join('، ')}</span></button>)}</div>}
        <label className="field">{t('book.orName')}<input className="input" value={walkName} onChange={(e) => setWalkName(e.target.value)} required={!cust} /></label>
      </>}
      {cust && cust.beneficiaries.length > 0 && <label className="field">{t('book.for')}<select className="input" value={beneficiary} onChange={(e) => setBeneficiary(Number(e.target.value))}>
        {cust.beneficiaries.map((b) => <option key={b.id} value={b.id}>{b.full_name} — {t(`cust.rel.${b.relation}`)}</option>)}</select></label>}
      {!walkIn && <label className="field">{t('book.time')} ({date})<input className="input" type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} required /></label>}
      <div className="field">{t('book.services')}</div>
      {rows.map((r, i) => <div className="two" key={i}>
        <select className="input" value={r.service_id} onChange={(e) => setRow(i, { service_id: Number(e.target.value), staff_id: 0 })} required>
          <option value={0} disabled>{t('book.pickService')}</option>
          {branchServices.map((s) => <option key={s.id} value={s.id}>{nameOf(s, i18n.language)} · {s.duration_minutes} {t('svc.min')}</option>)}</select>
        <select className="input" value={r.staff_id} onChange={(e) => setRow(i, { staff_id: Number(e.target.value) })} required disabled={!r.service_id}>
          <option value={0} disabled>{t('book.pickStaff')}</option>
          {staffFor(r.service_id).map((p) => <option key={p.id} value={p.id}>{i18n.language === 'en' && p.full_name_en ? p.full_name_en : p.full_name_ar}</option>)}</select>
      </div>)}
      <button type="button" className="btn sm" onClick={() => setRows([...rows, { service_id: 0, staff_id: 0 }])}><Icon name="plus" />{t('book.addService')}</button>
      {branchServices.length === 0 && <div className="notice"><Icon name="info" />{t('book.noServices')}</div>}
      <ErrorText error={error} />
    </Dialog>
  )
}

const kwDate = (iso: string) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Kuwait' })

function Reschedule({ appt, onClose }: { appt: Appointment; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const { branchServices, staffFor } = useServicesStaff()
  const [day, setDay] = useState(kwDate(appt.starts_at))
  const [time, setTime] = useState(hhmm(appt.starts_at))
  const [rows, setRows] = useState<Row[]>(appt.items.map((i) => ({ service_id: i.service_id, staff_id: i.staff_id })))
  const { save, busy, error } = useSave<Appointment>([['appointments']], () => { toast(t('common.saved')); onClose() })
  const setRow = (i: number, r: Partial<Row>) => setRows(rows.map((x, j) => (j === i ? { ...x, ...r } : x)))
  return (
    <Dialog open wide title={`${t('book.reschedule')}: ${appt.beneficiary_name || appt.customer_name}`} onClose={onClose} busy={busy}
      onSubmit={() => save({ path: `/booking/appointments/${appt.id}`, method: 'PATCH',
        body: { starts_at: new Date(`${day}T${time}:00+03:00`).toISOString(), items: rows.filter((r) => r.service_id && r.staff_id) } })}>
      <div className="two">
        <label className="field">{t('acc.date')}<input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} required /></label>
        <label className="field">{t('book.time')}<input className="input" type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} required /></label>
      </div>
      {rows.map((r, i) => <div className="row" key={i} style={{ flexWrap: 'nowrap' }}>
        <select className="input" value={r.service_id} onChange={(e) => setRow(i, { service_id: Number(e.target.value), staff_id: 0 })} required>
          <option value={0} disabled>{t('book.pickService')}</option>
          {branchServices.map((s) => <option key={s.id} value={s.id}>{nameOf(s, i18n.language)} · {s.duration_minutes} {t('svc.min')}</option>)}</select>
        <select className="input" value={r.staff_id} onChange={(e) => setRow(i, { staff_id: Number(e.target.value) })} required disabled={!r.service_id}>
          <option value={0} disabled>{t('book.pickStaff')}</option>
          {staffFor(r.service_id).map((p) => <option key={p.id} value={p.id}>{i18n.language === 'en' && p.full_name_en ? p.full_name_en : p.full_name_ar}</option>)}</select>
        {rows.length > 1 && <button type="button" className="btn sm ghost" aria-label={t('common.delete')} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Icon name="trash" /></button>}
      </div>)}
      <button type="button" className="btn sm" onClick={() => setRows([...rows, { service_id: 0, staff_id: 0 }])}><Icon name="plus" />{t('book.addService')}</button>
      <ErrorText error={error} />
    </Dialog>
  )
}

export default function Bookings() {
  const { t, i18n } = useTranslation()
  const { can } = useAuth()
  const { branch } = useBranch()
  const nav = useNavigate()
  const toast = useToast()
  const [date, setDate] = useState(todayISO())
  const [adding, setAdding] = useState(false)
  const [moving, setMoving] = useState<Appointment | null>(null)
  const [reasonFor, setReasonFor] = useState<{ appt: Appointment; status: ApptStatus } | null>(null)
  const [reason, setReason] = useState('')
  const { staff } = useServicesStaff()
  const list = useQuery({ queryKey: ['appointments', branch?.id, date], enabled: !!branch, refetchInterval: 30000,
    queryFn: () => api<Appointment[]>(`/booking/appointments?branch_id=${branch!.id}&date=${date}`) })
  const move = useSave<Appointment>([['appointments']], () => { setReasonFor(null); setReason('') })
  const setStatus = (a: Appointment, status: ApptStatus, why = '') => move.save({ path: `/booking/appointments/${a.id}/status`, body: { status, reason: why } })
  const manage = can('booking.manage')
  const staffName = (id: number) => { const p = staff.find((x) => x.id === id); return p ? (i18n.language === 'en' && p.full_name_en ? p.full_name_en : p.full_name_ar) : '' }
  const toPOS = (a: Appointment) => {
    const go = () => nav('/pos', { state: { appointment: a } })
    if (a.status === 'in_service') move.save({ path: `/booking/appointments/${a.id}/status`, body: { status: 'completed' } }, { onSuccess: go })
    else go()
  }
  const rows = list.data ?? []
  const col = (title: string, sts: ApptStatus[], acts: (a: Appointment) => React.ReactNode) => {
    const r = rows.filter((a) => sts.includes(a.status))
    return (
      <div className="col"><h3><span>{title}</span><span className="pill mute"><bdi>{r.length}</bdi></span></h3>
        {r.map((a) => <div className="tk" key={a.id}>
          <div className="row sb"><b>{a.beneficiary_name || a.customer_name}</b><bdi className="cap muted">{hhmm(a.starts_at)}</bdi></div>
          <div className="cap muted">{a.items.map((i) => `${nameOf({ name_ar: i.service_name_ar, name_en: i.service_name_en }, i18n.language)} · ${staffName(i.staff_id)}`).join(' ← ')}
            {a.customer_phone && <> · <bdi>+{a.customer_phone}</bdi></>}</div>
          {a.source === 'walk_in' && <span className="pill info">{t('book.walkIn')}</span>}{' '}
          {a.status === 'arrived' && <span className="pill warn">{t('book.st.arrived')}</span>}
          {['cancelled', 'no_show', 'invoiced', 'completed'].includes(a.status) && <span className={`pill ${a.status === 'invoiced' ? 'good' : a.status === 'completed' ? 'info' : 'mute'}`}>{t(`book.st.${a.status}`)}</span>}
          {a.status_reason && <div className="cap muted">{a.status_reason}</div>}
          {manage && <div className="acts">{acts(a)}</div>}
        </div>)}
      </div>
    )
  }
  if (!branch) return <p className="muted">{t('common.loading')}</p>
  return (
    <>
      <Head title={t('nav.bookings')} sub={t('book.sub')}>
        <input type="date" className="input" style={{ width: 'auto' }} value={date} onChange={(e) => setDate(e.target.value)} />
        {manage && <button className="btn primary" onClick={() => setAdding(true)}><Icon name="plus" />{t('book.new')}</button>}
      </Head>
      <ErrorText error={list.error || move.error} />
      <div className="board">
        {col(t('book.waiting'), ['booked', 'arrived'], (a) => <>
          {a.status === 'booked' && <button className="btn sm" onClick={() => setStatus(a, 'arrived')}>{t('book.arrived')}</button>}
          <button className="btn sm primary" onClick={() => setStatus(a, 'in_service')}>{t('book.toChair')}</button>
          <button className="btn sm ghost" onClick={() => setMoving(a)}>{t('book.reschedule')}</button>
          {a.status === 'booked' && <button className="btn sm ghost danger" onClick={() => setReasonFor({ appt: a, status: 'no_show' })}>{t('book.noShow')}</button>}
          <button className="btn sm ghost danger" onClick={() => setReasonFor({ appt: a, status: 'cancelled' })}>{t('book.cancel')}</button>
        </>)}
        {col(t('book.onChair'), ['in_service'], (a) => <>
          {can('pos.sell') && <button className="btn sm brand" onClick={() => toPOS(a)}>{t('book.doneToPos')}</button>}
          <button className="btn sm ghost" onClick={() => setStatus(a, 'completed')}>{t('book.done')}</button>
          <button className="btn sm ghost" onClick={() => setStatus(a, 'arrived')}>{t('book.back')}</button>
        </>)}
        {col(t('book.finished'), ['completed', 'invoiced', 'cancelled', 'no_show'], (a) => <>
          {a.status === 'completed' && can('pos.sell') && <button className="btn sm brand" onClick={() => toPOS(a)}>{t('book.toPos')}</button>}
          {a.status === 'invoiced' && a.invoice_id && <button className="btn sm ghost" onClick={() => nav(`/invoices?open=${a.invoice_id}`)}>{t('book.viewInvoice')}</button>}
        </>)}
      </div>
      {moving && <Reschedule appt={moving} onClose={() => setMoving(null)} />}
      {adding && <NewBooking date={date} onClose={() => setAdding(false)} />}
      <Dialog open={!!reasonFor} title={reasonFor ? t(`book.st.${reasonFor.status}`) : ''} onClose={() => setReasonFor(null)} busy={move.busy}
        onSubmit={() => { setStatus(reasonFor!.appt, reasonFor!.status, reason); toast(t('common.saved')) }}>
        <label className="field">{t('book.reason')}<input className="input" value={reason} onChange={(e) => setReason(e.target.value)} required /></label>
        <ErrorText error={move.error} />
      </Dialog>
    </>
  )
}
