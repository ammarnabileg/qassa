import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { here } from '../base'
import { ErrorText, LangToggle } from '../components/ErrorText'
import { Logo } from '../components/ui'
import { formatKWD } from '../money'

type Info = { status: string; amount: string; invoice: string; salon: string }

/** Where KlickPay sends the customer back (/pay/<ref>). The state comes from our server, which checks with KlickPay. */
export default function Pay() {
  const { t, i18n } = useTranslation()
  const ref = here().split('/')[2] || ''
  const [info, setInfo] = useState<Info | null>(null)
  const [err, setErr] = useState<unknown>(null)
  useEffect(() => {
    let n = 0
    const load = () => api<Info>(`/public/pay/${encodeURIComponent(ref)}`).then((r) => {
      setInfo(r)
      if (r.status === 'created' && ++n < 10) timer = window.setTimeout(load, 3000)   // the check runs in the background
    }, setErr)
    let timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [ref])
  const ok = info?.status === 'paid'
  const bad = info && ['declined', 'failed', 'voided'].includes(info.status)
  return (
    <div className="login"><div className="card">
      <div className="row sb"><Logo biz="kids" title={info?.salon || t('app.name')} sub={info ? `${t('fb.invoice')} ${info.invoice}` : ''} /><LangToggle className="btn sm" /></div>
      {info && <>
        <h1>{ok ? t('payp.ok') : bad ? t('payp.bad') : info.status === 'review' ? t('payp.review') : t('payp.wait')}</h1>
        <div className="small muted">{formatKWD(info.amount, i18n.language as 'ar' | 'en')}</div>
        <div className="small muted">{ok ? t('payp.okHelp') : bad ? t('payp.badHelp') : info.status === 'review' ? t('payp.reviewHelp') : t('payp.waitHelp')}</div>
      </>}
      <ErrorText error={err} />
    </div></div>
  )
}
