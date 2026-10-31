import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { upload } from '../api/client'
import { ErrorText } from './ErrorText'
import { Icon, useToast } from './ui'

type Result = { rows: number; created: number; matched?: number; children?: number; repriced?: number; error_count: number; errors: { row: number; code: string }[]; committed: boolean }

/** Upload an Excel/CSV sheet: first a preview of what would happen, then an explicit import. */
export function ImportCard({ kind }: { kind: 'customers' | 'services' }) {
  const { t } = useTranslation()
  const toast = useToast()
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [res, setRes] = useState<Result | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const send = async (f: File, commit: boolean) => {
    setBusy(true); setErr(null)
    const body = new FormData(); body.append('file', f); if (commit) body.append('commit', 'true')
    try {
      setRes(await upload<Result>(`/import/${kind}`, body))
      if (commit) { toast(t('imp.done')); qc.invalidateQueries(); setFile(null) }
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <h2>{t(`imp.${kind}`)}</h2>
      <div className="small muted" style={{ margin: '6px 0 10px' }}>{t(`imp.${kind}Help`)}</div>
      <input ref={input} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) { setFile(f); setRes(null); send(f, false) } }} />
      <button className="btn" disabled={busy} onClick={() => input.current?.click()}><Icon name="file" />{t('imp.choose')}</button>
      {res && <div className="notice" style={{ marginTop: 10, display: 'block' }}>
        <b>{res.committed ? t('imp.imported') : t('imp.preview')}</b>
        <div className="small">{t('imp.summary', { rows: res.rows, created: res.created })}
          {res.matched ? ` · ${t('imp.matched', { n: res.matched })}` : ''}{res.children ? ` · ${t('imp.children', { n: res.children })}` : ''}
          {res.repriced ? ` · ${t('imp.repriced', { n: res.repriced })}` : ''}</div>
        {res.error_count > 0 && <div className="small" style={{ color: 'var(--danger, #c0392b)' }}>{t('imp.errors', { n: res.error_count })}{' '}
          {res.errors.slice(0, 8).map((e) => t('imp.rowErr', { row: e.row, why: t(`imp.code.${e.code}`) })).join(' · ')}</div>}
      </div>}
      {res && !res.committed && file && res.created + (res.children ?? 0) + (res.repriced ?? 0) > 0 &&
        <button className="btn primary" style={{ marginTop: 10 }} disabled={busy} onClick={() => send(file, true)}>{t('imp.confirm')}</button>}
      <ErrorText error={err} />
    </div>
  )
}
