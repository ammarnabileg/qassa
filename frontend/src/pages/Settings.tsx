import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, getTenant } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, useToast } from '../components/ui'

export type SalonSettings = { receipt_header_ar: string; receipt_footer_ar: string; receipt_footer_en: string; commercial_registration: string; show_staff_on_receipt: boolean }
export const useSalonSettings = () => useQuery({ queryKey: ['salon-settings', getTenant()], queryFn: () => api<SalonSettings>('/salon-settings'), staleTime: 300000 })

/** Salon settings (reference v-set): receipt texts and data export. Kuwait has no VAT today, so no tax is calculated. */
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
  return (
    <>
      <Head title={t('nav.settings')} sub={t('set.sub')} />
      {f && <div className="grid g2">
        <div className="card">
          <h2>{t('set.receipt')}</h2>
          <label className="field">{t('set.header')}<input className="input" disabled={!manage} value={f.receipt_header_ar} onChange={(e) => setF({ ...f, receipt_header_ar: e.target.value })} placeholder={t('set.headerPh')} /></label>
          <label className="field">{t('set.footerAr')}<input className="input" disabled={!manage} value={f.receipt_footer_ar} onChange={(e) => setF({ ...f, receipt_footer_ar: e.target.value })} placeholder={t('inv.thanks')} /></label>
          <label className="field">{t('set.footerEn')}<input className="input" dir="ltr" disabled={!manage} value={f.receipt_footer_en} onChange={(e) => setF({ ...f, receipt_footer_en: e.target.value })} placeholder="Thank you for visiting" /></label>
          <label className="field">{t('set.cr')}<input className="input" dir="ltr" disabled={!manage} value={f.commercial_registration} onChange={(e) => setF({ ...f, commercial_registration: e.target.value })} /></label>
          <div className="cap muted">{t('set.noVat')}</div>
          <ErrorText error={s.error} />
          {manage && <button className="btn primary" disabled={s.busy} onClick={() => s.save({ path: '/salon-settings', method: 'PATCH', body: f })}>{t('common.save')}</button>}
        </div>
        <div className="card">
          <h2>{t('set.data')}</h2>
          <div className="small muted">{t('set.dataHelp')}</div>
          {can('data.export') ? <div className="row">
            <button className="btn" onClick={() => download('customers')}><Icon name="download" />{t('set.exportCustomers')}</button>
            <button className="btn" onClick={() => download('invoices')}><Icon name="download" />{t('set.exportInvoices')}</button>
          </div> : <div className="notice">{t('set.noExport')}</div>}
        </div>
      </div>}
    </>
  )
}
