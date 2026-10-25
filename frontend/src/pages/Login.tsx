import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type LoginResult, type Me } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText, LangToggle } from '../components/ErrorText'

export default function Login() {
  const { t } = useTranslation()
  const { setMe } = useAuth()
  const [step, setStep] = useState<'password' | 'setup' | 'verify'>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [otpUrl, setOtpUrl] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null)
    try { await fn() } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const submitPassword = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const r = await api<LoginResult>('/auth/login', { method: 'POST', body: { email, password } })
    if ('mfa' in r) {
      setStep(r.mfa)
      if (r.mfa === 'setup') setOtpUrl((await api<{ otpauth_url: string }>('/auth/mfa/setup', { method: 'POST' })).otpauth_url)
    } else setMe(r)
  }) }

  const submitToken = (e: FormEvent) => { e.preventDefault(); run(async () => {
    setMe(await api<Me>('/auth/mfa/verify', { method: 'POST', body: { token } }))
  }) }

  return (
    <div className="center">
      <div className="card grid" style={{ width: 'min(420px,100%)', padding: 28 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div><h1>{t('app.name')}</h1><div className="small muted">{t('app.tagline')}</div></div>
          <LangToggle />
        </div>
        {step === 'password' ? (
          <form className="grid" onSubmit={submitPassword}>
            <h2>{t('auth.title')}</h2>
            <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label className="field">{t('auth.password')}<input className="input" type="password" dir="ltr" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            <ErrorText error={err} />
            <button className="btn primary" disabled={busy}>{t('auth.submit')}</button>
          </form>
        ) : (
          <form className="grid" onSubmit={submitToken}>
            <h2>{t(step === 'setup' ? 'auth.mfaSetupTitle' : 'auth.mfaVerifyTitle')}</h2>
            {step === 'setup' && <>
              <div className="small muted">{t('auth.mfaSetupHelp')}</div>
              <code dir="ltr" style={{ wordBreak: 'break-all', fontSize: 12, background: 'var(--surface-2)', padding: 8, borderRadius: 8 }}>{otpUrl}</code>
            </>}
            <label className="field">{t('auth.mfaCode')}<input className="input" inputMode="numeric" pattern="\d{6}" maxLength={6} dir="ltr" autoComplete="one-time-code" value={token} onChange={(e) => setToken(e.target.value)} required /></label>
            <ErrorText error={err} />
            <button className="btn primary" disabled={busy}>{t('auth.verify')}</button>
          </form>
        )}
      </div>
    </div>
  )
}
