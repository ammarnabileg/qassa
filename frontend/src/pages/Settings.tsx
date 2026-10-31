import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, getTenant } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { useNavigate } from 'react-router-dom'
import { Head, Icon, useToast } from '../components/ui'

type Tab = 'gen' | 'rcpt' | 'tax' | 'ntf' | 'sub' | 'data'

export type SalonSettings = { receipt_header_ar: string; receipt_footer_ar: string; receipt_footer_en: string; commercial_registration: string; show_staff_on_receipt: boolean }
export const useSalonSettings = () => useQuery({ queryKey: ['salon-settings', getTenant()], queryFn: () => api<SalonSettings>('/salon-settings'), staleTime: 300000 })

/** Salon settings (reference v-set) in the reference's tabs. Settings that live on their own screens (branches and hours,
 * WhatsApp, subscription) are linked from their tab instead of duplicated. Kuwait has no VAT today, so no tax is calculated. */
export default function Settings() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const toast = useToast()
  const q = useSalonSettings()
  const [f, setF] = useState<SalonSettings | null>(null)
  useEffect(() => { if (q.data) setF(q.data) }, [q.data])
  const s = useSave<SalonSettings>([['salon-settings']], () => toast(t('common.saved')))
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kuwait' })
  const download = async (kind: 'customers' | 'invoices') => {
    const res = await fetch(`/api/v1/export/${kind}${kind === 'invoices' ? `?from=${today.slice(0, 4)}-01-01&to=${today}` : ''}`, { credentials: 'include', headers: { 'X-Tenant': String(getTenant()) } })
    if (!res.ok) { toast(t('errors.unknown')); return }
    const a = document.createElement('a'); a.href = URL.createObjectURL(await res.blob()); a.download = `qassa-${kind}.csv`; a.click()
  }
  const manage = can('org.manage')
  const nav = useNavigate()
  const [tab, setTab] = useState<Tab>('gen')
  const go = (title: string, help: string, to: string, icon: string) => <div className="card"><h2>{title}</h2><div className="small muted" style={{ margin: '6px 0 12px' }}>{help}</div>
    <button className="btn" onClick={() => nav(to)}><Icon name={icon} />{t('set.open')}</button></div>
  const save = <>{<ErrorText error={s.error} />}{manage && <button className="btn primary" disabled={s.busy} onClick={() => s.save({ path: '/salon-settings', method: 'PATCH', body: f })}>{t('common.save')}</button>}</>
  return (
    <>
      <Head title={t('nav.settings')} sub={t('set.sub')} />
      <div className="tabs">{(['gen', 'rcpt', 'tax', 'ntf', 'sub', 'data'] as Tab[]).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`set.tab.${x}`)}</button>)}</div>
      {tab === 'gen' && <div className="grid g2">
        {go(t('set.branches'), t('set.branchesHelp'), '/org', 'store')}
        {go(t('nav.staff'), t('set.staffHelp'), '/staff', 'users')}
      </div>}
      {tab === 'rcpt' && f && <div className="card" style={{ maxWidth: 620 }}>
        <h2>{t('set.receipt')}</h2>
        <label className="field">{t('set.header')}<input className="input" disabled={!manage} value={f.receipt_header_ar} onChange={(e) => setF({ ...f, receipt_header_ar: e.target.value })} placeholder={t('set.headerPh')} /></label>
        <label className="field">{t('set.footerAr')}<input className="input" disabled={!manage} value={f.receipt_footer_ar} onChange={(e) => setF({ ...f, receipt_footer_ar: e.target.value })} placeholder={t('inv.thanks')} /></label>
        <label className="field">{t('set.footerEn')}<input className="input" dir="ltr" disabled={!manage} value={f.receipt_footer_en} onChange={(e) => setF({ ...f, receipt_footer_en: e.target.value })} placeholder="Thank you for visiting" /></label>
        <label className="chk"><span>{t('set.showStaff')}</span><input type="checkbox" className="sw" disabled={!manage} checked={f.show_staff_on_receipt} onChange={(e) => setF({ ...f, show_staff_on_receipt: e.target.checked })} /></label>
        {save}
      </div>}
      {tab === 'tax' && f && <div className="card" style={{ maxWidth: 620 }}>
        <h2>{t('set.tax')}</h2>
        <div className="notice"><Icon name="info" />{t('set.noVat')}</div>
        <label className="field">{t('set.cr')}<input className="input" dir="ltr" disabled={!manage} value={f.commercial_registration} onChange={(e) => setF({ ...f, commercial_registration: e.target.value })} /></label>
        <div className="small muted" style={{ margin: '8px 0' }}>{t('set.payMethods')}</div>
        {save}
      </div>}
      {tab === 'ntf' && <div className="grid g2">{go(t('nav.whatsapp'), t('set.ntfHelp'), '/whatsapp', 'whatsapp')}</div>}
      {tab === 'sub' && <div className="grid g2">{go(t('nav.subscription'), t('set.subHelp'), '/subscription', 'receipt')}</div>}
      {tab === 'data' && <div className="card" style={{ maxWidth: 620 }}>
        <h2>{t('set.data')}</h2>
        <div className="small muted">{t('set.dataHelp')}</div>
        {can('data.export') ? <div className="row">
          <button className="btn" onClick={() => download('customers')}><Icon name="download" />{t('set.exportCustomers')}</button>
          <button className="btn" onClick={() => download('invoices')}><Icon name="download" />{t('set.exportInvoices')}</button>
        </div> : <div className="notice">{t('set.noExport')}</div>}
      </div>}
    </>
  )
}
