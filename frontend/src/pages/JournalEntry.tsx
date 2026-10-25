import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Account } from '../api/client'
import { ErrorText } from '../components/ErrorText'
import { formatKWD, fromFils, toFils } from '../money'
import { useOrg } from './Org'

type LineForm = { account_id: string; debit: string; credit: string; description: string }
const blank = (): LineForm => ({ account_id: '', debit: '', credit: '', description: '' })
const amountOk = (v: string) => v === '' || /^\d+(\.\d{0,3})?$/.test(v)

export default function JournalEntry() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const qc = useQueryClient()
  const org = useOrg()
  const entity = org.data?.legal_entities[0]
  const accounts = useQuery({ enabled: !!entity, queryKey: ['accounts', entity?.id],
    queryFn: () => api<Account[]>(`/accounting/accounts?legal_entity_id=${entity!.id}`) })
  const postable = (accounts.data ?? []).filter((a) => a.is_postable && a.is_active && !a.is_control)
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [memo, setMemo] = useState('')
  const [lines, setLines] = useState<LineForm[]>([blank(), blank()])
  const [done, setDone] = useState('')
  // One idempotency key per user submission, reused if the same submission is retried after a network failure.
  const key = useRef(crypto.randomUUID())

  const valid = lines.every((l) => amountOk(l.debit) && amountOk(l.credit))
  const totD = valid ? lines.reduce((s, l) => s + toFils(l.debit), 0n) : 0n
  const totC = valid ? lines.reduce((s, l) => s + toFils(l.credit), 0n) : 0n
  const diff = totD - totC

  const post = useMutation({
    mutationFn: () => api<{ number: string }>('/accounting/journal-entries', { method: 'POST', idempotencyKey: key.current, body: {
      legal_entity_id: entity!.id, entry_date: date, memo,
      lines: lines.filter((l) => l.account_id).map((l) => ({ account_id: Number(l.account_id), debit: l.debit || '0', credit: l.credit || '0', description: l.description })),
    } }),
    onSuccess: (r) => { setDone(r.number); setLines([blank(), blank()]); setMemo(''); key.current = crypto.randomUUID(); qc.invalidateQueries({ queryKey: ['tb'] }) },
  })
  const set = (i: number, patch: Partial<LineForm>) => { setDone(''); setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l))) }

  return (
    <div className="grid" style={{ maxWidth: 980 }}>
      <div className="head"><h1>{t('acc.newEntry')}</h1></div>
      <div className="row">
        <label className="field">{t('acc.date')}<input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label className="field" style={{ flex: 1 }}>{t('acc.memo')}<input className="input" value={memo} onChange={(e) => setMemo(e.target.value)} /></label>
      </div>
      <div className="tw"><table>
        <thead><tr><th>{t('acc.account')}</th><th className="n">{t('acc.debit')}</th><th className="n">{t('acc.credit')}</th><th>{t('acc.lineDesc')}</th></tr></thead>
        <tbody>{lines.map((l, i) => <tr key={i}>
          <td><select className="input" value={l.account_id} onChange={(e) => set(i, { account_id: e.target.value })}><option value="">—</option>
            {postable.map((a) => <option key={a.id} value={a.id}>{a.code} — {lang === 'en' ? a.name_en : a.name_ar}</option>)}</select></td>
          <td><input className="input num" dir="ltr" inputMode="decimal" value={l.debit} aria-invalid={!amountOk(l.debit)} onChange={(e) => set(i, { debit: e.target.value, credit: e.target.value ? '' : l.credit })} /></td>
          <td><input className="input num" dir="ltr" inputMode="decimal" value={l.credit} aria-invalid={!amountOk(l.credit)} onChange={(e) => set(i, { credit: e.target.value, debit: e.target.value ? '' : l.debit })} /></td>
          <td><input className="input" value={l.description} onChange={(e) => set(i, { description: e.target.value })} /></td>
        </tr>)}
          <tr><td><button type="button" className="btn ghost" onClick={() => setLines([...lines, blank()])}>+ {t('acc.addLine')}</button></td>
            <td className="n num"><b>{formatKWD(totD, lang)}</b></td><td className="n num"><b>{formatKWD(totC, lang)}</b></td>
            <td>{diff !== 0n && <span className="pill bad">{t('acc.difference')}: {fromFils(diff < 0n ? -diff : diff)}</span>}</td></tr>
        </tbody></table></div>
      <ErrorText error={post.error} />
      {done && <div className="alert good">{t('acc.posted', { number: done })}</div>}
      <div><button className="btn brand" disabled={!entity || !valid || totD === 0n || diff !== 0n || post.isPending} onClick={() => post.mutate()}>{t('acc.post')}</button></div>
    </div>
  )
}
