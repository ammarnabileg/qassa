import { link } from '../base'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ErrorText, LangToggle } from '../components/ErrorText'
import { Logo } from '../components/ui'

/** Invitation acceptance / password reset, opened from the link (uid + token). */
export default function SetPassword() {
  const { t } = useTranslation()
  const p = new URLSearchParams(window.location.search)
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(null)
    if (pw !== pw2) { setErr({ code: 'password_mismatch' }); return }
    setBusy(true)
    try { await api('/auth/password/set', { method: 'POST', body: { uid: p.get('uid'), token: p.get('token'), password: pw } }); setDone(true) }
    catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return (
    <div className="login"><div className="card">
      <div className="row sb"><Logo biz="kids" title={t('app.name')} sub={t('app.tagline')} /><LangToggle className="btn sm" /></div>
      {done ? <>
        <h1>{t('pw.doneTitle')}</h1><div className="small muted">{t('pw.doneSub')}</div>
        <a className="btn primary lg" href={link('/login')}>{t('auth.submit')}</a>
      </> : <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><h1>{t(p.get('p') === 'reset' ? 'pw.resetTitle' : 'pw.inviteTitle')}</h1><div className="small muted">{t('pw.rules')}</div></div>
        <label className="field">{t('pw.new')}<input className="input" type="password" dir="ltr" autoComplete="new-password" minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} required /></label>
        <label className="field">{t('pw.repeat')}<input className="input" type="password" dir="ltr" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required /></label>
        {err && (err as { code?: string }).code === 'password_mismatch' ? <div className="notice bad">{t('pw.mismatch')}</div> : <ErrorText error={err} />}
        <button className="btn primary lg" disabled={busy}>{t('common.save')}</button>
      </form>}
    </div></div>
  )
}
