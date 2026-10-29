import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth'
import { useBranch } from '../branch'
import { Icon } from '../components/ui'
import { getBundle, refreshBundle, registerDevice } from './engine'
import { useOffline } from './OfflineProvider'

/** On the online till: enable offline selling for this browser, and keep its snapshot fresh (every 10 minutes). */
export function OfflineSetup() {
  const { t, i18n } = useTranslation()
  const { membership, can } = useAuth()
  const { branch } = useBranch()
  const { device, setDevice, online } = useOffline()
  const [at, setAt] = useState<string | null>(null)
  const [err, setErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const tenant = membership?.tenant_id ?? 0
  useEffect(() => {
    if (!device || !branch || !online) return
    let alive = true
    const run = () => refreshBundle(tenant, branch.id).then((b) => alive && setAt(b.generated_at)).catch(() => getBundle(tenant, branch.id).then((b) => alive && setAt(b?.generated_at ?? null)))
    run()
    const h = window.setInterval(run, 600000)
    return () => { alive = false; window.clearInterval(h) }
  }, [device, branch, tenant, online])
  if (!can('pos.sell') || !branch || membership?.support) return null
  if (!device) return (
    <div className="notice info"><Icon name="shield" /><span className="grow">{t('off.enableHelp')}</span>
      <button className="btn sm" disabled={busy} onClick={async () => {
        setBusy(true); setErr(false)
        try { setDevice(await registerDevice(tenant, branch.id, `${navigator.platform || 'POS'} · ${branch.code || branch.id}`)) } catch { setErr(true) } finally { setBusy(false) }
      }}>{t('off.enable')}</button>{err && <span className="small">{t('errors.unknown')}</span>}</div>
  )
  if (device.branch_id !== branch.id) return <div className="notice"><Icon name="info" />{t('off.otherBranch')}</div>
  return <div className="cap muted" style={{ marginBottom: 8 }}><Icon name="circle-check" /> {t('off.ready')}{at && ` · ${new Date(at).toLocaleTimeString(i18n.language === 'ar' ? 'ar-KW' : 'en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuwait' })}`}</div>
}

/** Shown in every screen: connection state and receipts waiting to be sent. */
export function OfflineBanner() {
  const { t } = useTranslation()
  const { online, pendingCount, lastSync, sync } = useOffline()
  if (online && pendingCount === 0 && !(lastSync && (lastSync.review || lastSync.conflict || lastSync.rejected))) return null
  return (
    <div className={`notice ${online ? 'info' : 'bad'}`} style={{ margin: '12px 16px 0' }}>
      <Icon name={online ? 'refresh' : 'alert'} />
      <span className="grow">{!online ? t('off.noInternet', { n: pendingCount }) : pendingCount > 0 ? t('off.sending', { n: pendingCount })
        : t('off.syncedWithIssues', { r: lastSync!.review, c: lastSync!.conflict + lastSync!.rejected })}</span>
      {online && pendingCount > 0 && <button className="btn sm" onClick={() => sync()}>{t('off.sendNow')}</button>}
      {online && pendingCount === 0 && <a className="btn sm" href="/offline-receipts">{t('off.review')}</a>}
    </div>
  )
}
