import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Staff } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Dialog, Icon, nameOf, useToast } from '../components/ui'
import { useOrg } from './Org'

type Hour = { branch_id: number; weekday: number; starts_at: string; ends_at: string }
type Off = { id: number; starts_at: string; ends_at: string; reason: string }
type Sched = { hours: Hour[]; time_off: Off[] }
const DAYS = [6, 0, 1, 2, 3, 4, 5] // Sunday first; 0 = Monday (server convention)
const kw = (v: string) => `${v}:00+03:00` // datetime-local is entered in Kuwait time

/** Weekly working hours and time off; booking and slots refuse anything outside them. */
export default function StaffSchedule({ staff, onClose }: { staff: Staff | null; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { can } = useAuth()
  const toast = useToast()
  const org = useOrg()
  const edit = can('staff.manage')
  const q = useQuery({ enabled: !!staff, queryKey: ['schedule', staff?.id], queryFn: () => api<Sched>(`/staff/${staff!.id}/schedule`) })
  const [hours, setHours] = useState<Hour[]>([])
  const [off, setOff] = useState({ starts_at: '', ends_at: '', reason: '' })
  useEffect(() => { if (q.data) setHours(q.data.hours) }, [q.data])
  const h = useSave<Sched>([['schedule', staff?.id ?? 0]], () => toast(t('common.saved')))
  const o = useSave<Sched>([['schedule', staff?.id ?? 0]], () => { setOff({ starts_at: '', ends_at: '', reason: '' }); toast(t('common.saved')) })
  const branches = org.data?.branches.filter((b) => staff?.branch_ids.includes(b.id)) ?? []
  const fmt = (v: string) => new Date(v).toLocaleString(lang === 'ar' ? 'ar-KW' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kuwait' })
  const set = (i: number, p: Partial<Hour>) => setHours(hours.map((x, j) => (j === i ? { ...x, ...p } : x)))
  return (
    <Dialog open={!!staff} wide title={staff ? `${t('sched.title')}: ${lang === 'en' && staff.full_name_en ? staff.full_name_en : staff.full_name_ar}` : ''} onClose={onClose}>
      {staff && <>
        <div className="small muted">{t('sched.help')}</div>
        {branches.length === 0 && <div className="notice">{t('sched.noBranch')}</div>}
        {hours.map((x, i) => <div className="row" key={i} style={{ flexWrap: 'nowrap' }}>
          <select className="input" disabled={!edit} value={x.weekday} onChange={(e) => set(i, { weekday: Number(e.target.value) })}>
            {DAYS.map((d) => <option key={d} value={d}>{t(`sched.d${d}`)}</option>)}</select>
          {branches.length > 1 && <select className="input" disabled={!edit} value={x.branch_id} onChange={(e) => set(i, { branch_id: Number(e.target.value) })}>
            {branches.map((b) => <option key={b.id} value={b.id}>{nameOf(b, lang)}</option>)}</select>}
          <input className="input" type="time" disabled={!edit} value={x.starts_at} onChange={(e) => set(i, { starts_at: e.target.value })} />
          <input className="input" type="time" disabled={!edit} value={x.ends_at} onChange={(e) => set(i, { ends_at: e.target.value })} />
          {edit && <button type="button" className="btn sm ghost" aria-label={t('common.delete')} onClick={() => setHours(hours.filter((_, j) => j !== i))}><Icon name="trash" /></button>}
        </div>)}
        {hours.length === 0 && q.data && <div className="small muted">{t('sched.none')}</div>}
        {edit && branches.length > 0 && <div className="row">
          <button type="button" className="btn sm" onClick={() => setHours([...hours, { branch_id: branches[0].id, weekday: 6, starts_at: '10:00', ends_at: '22:00' }])}><Icon name="plus" />{t('sched.addDay')}</button>
          <button type="button" className="btn sm" onClick={() => setHours(DAYS.filter((d) => d !== 4).map((d) => ({ branch_id: branches[0].id, weekday: d, starts_at: '10:00', ends_at: '22:00' })))}>{t('sched.fillWeek')}</button>
          <button type="button" className="btn sm primary" disabled={h.busy} onClick={() => h.save({ path: `/staff/${staff.id}/schedule`, method: 'PUT', body: { hours } })}>{t('common.save')}</button>
        </div>}
        <ErrorText error={h.error} />

        <h3 style={{ margin: '14px 0 4px' }}>{t('sched.timeOff')}</h3>
        <div className="list">{q.data?.time_off.map((x) => <div className="li" key={x.id}>
          <div className="grow small"><bdi>{fmt(x.starts_at)}</bdi> → <bdi>{fmt(x.ends_at)}</bdi>{x.reason && <span className="muted"> · {x.reason}</span>}</div>
          {edit && <button type="button" className="btn sm ghost" aria-label={t('common.delete')} disabled={o.busy}
            onClick={() => o.save({ path: `/staff/${staff.id}/time-off/${x.id}`, method: 'DELETE' })}><Icon name="trash" /></button>}</div>)}
          {q.data?.time_off.length === 0 && <div className="small muted">{t('sched.noTimeOff')}</div>}</div>
        {edit && <div className="row">
          <input className="input" type="datetime-local" aria-label={t('svc.from')} value={off.starts_at} onChange={(e) => setOff({ ...off, starts_at: e.target.value })} />
          <input className="input" type="datetime-local" aria-label={t('svc.to')} value={off.ends_at} onChange={(e) => setOff({ ...off, ends_at: e.target.value })} />
          <input className="input" placeholder={t('book.reason')} value={off.reason} onChange={(e) => setOff({ ...off, reason: e.target.value })} />
          <button type="button" className="btn sm" disabled={o.busy || !off.starts_at || !off.ends_at}
            onClick={() => o.save({ path: `/staff/${staff.id}/time-off`, body: { starts_at: kw(off.starts_at), ends_at: kw(off.ends_at), reason: off.reason } })}><Icon name="plus" />{t('sched.addOff')}</button>
        </div>}
        <ErrorText error={o.error} />
      </>}
    </Dialog>
  )
}
