import { here } from '../base'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ErrorText, LangToggle } from '../components/ErrorText'
import { Logo } from '../components/ui'

type Info = { salon: string; branch_ar: string; branch_en: string; rating: number | null; review_url: string }

/** Public page behind the WhatsApp rating link (/rate/<token>): five stars and an optional comment, once. */
export default function Rate() {
  const { t, i18n } = useTranslation()
  const token = here().split('/')[2] || ''
  const [info, setInfo] = useState<Info | null>(null)
  const [stars, setStars] = useState(0)
  const [comment, setComment] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api<Info>(`/public/feedback/${encodeURIComponent(token)}`).then(setInfo, setErr) }, [token])
  const send = async () => {
    setBusy(true); setErr(null)
    try { setInfo(await api<Info>(`/public/feedback/${encodeURIComponent(token)}`, { method: 'POST', body: { rating: stars, comment } })) }
    catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const branch = info && (i18n.language === 'en' && info.branch_en ? info.branch_en : info.branch_ar)
  return (
    <div className="login"><div className="card">
      <div className="row sb"><Logo biz="kids" title={info?.salon || t('app.name')} sub={branch || ''} /><LangToggle className="btn sm" /></div>
      {info && info.rating !== null ? <>
        <h1>{t('rate.thanks')}</h1>
        <div className="small muted">{info.review_url ? t('rate.happy') : t('rate.sorry')}</div>
        {info.review_url && <a className="btn primary lg" href={info.review_url} target="_blank" rel="noreferrer">{t('rate.google')}</a>}
      </> : info && <>
        <h1>{t('rate.title')}</h1>
        <div className="row" style={{ justifyContent: 'center', gap: 6 }} role="radiogroup" aria-label={t('rate.title')}>
          {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={String(n)} className="btn ghost"
            style={{ fontSize: 34, padding: 4, filter: n <= stars ? 'none' : 'grayscale(1) opacity(.35)' }} onClick={() => setStars(n)}>⭐</button>)}
        </div>
        <label className="field">{t('rate.comment')}<textarea className="input" rows={3} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
        <button className="btn primary lg" disabled={!stars || busy} onClick={send}>{t('rate.send')}</button>
      </>}
      <ErrorText error={err} />
    </div></div>
  )
}
