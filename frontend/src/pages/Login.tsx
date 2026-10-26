import QRCode from 'qrcode'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type LoginResult, type Me } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText, LangToggle } from '../components/ErrorText'
import { Icon, Logo } from '../components/ui'

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
  const [qr, setQr] = useState('')
  const [methods, setMethods] = useState<('totp' | 'whatsapp')[]>(['totp'])
  const [method, setMethod] = useState<'totp' | 'whatsapp'>('totp')
  const [maskedPhone, setMaskedPhone] = useState('')
  const [waSent, setWaSent] = useState('')
  const [remember, setRemember] = useState(true)
  // the otpauth:// URL is drawn as a QR locally — the secret never goes to a third-party QR service
  useEffect(() => { if (otpUrl) QRCode.toDataURL(otpUrl, { width: 220, margin: 1 }).then(setQr).catch(() => setQr('')) }, [otpUrl])
  const secret = otpUrl ? new URL(otpUrl).searchParams.get('secret') ?? '' : ''

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null)
    try { await fn() } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const submitPassword = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const r = await api<LoginResult>('/auth/login', { method: 'POST', body: { email, password } })
    if ('mfa' in r) {
      setStep(r.mfa); setMethods(r.methods ?? ['totp']); setMaskedPhone(r.phone ?? '')
      // a new user without an authenticator yet: start with WhatsApp when it is offered
      const first = r.mfa === 'setup' && r.methods?.includes('whatsapp') ? 'whatsapp' : 'totp'
      setMethod(first)
      if (r.mfa === 'setup' && first === 'totp') setOtpUrl((await api<{ otpauth_url: string }>('/auth/mfa/setup', { method: 'POST' })).otpauth_url)
    } else setMe(r)
  }) }

  const sendWhatsApp = () => run(async () => {
    const r = await api<{ to: string; debug_code?: string }>('/auth/mfa/whatsapp', { method: 'POST' })
    setWaSent(r.debug_code ? `${r.to} — ${t('auth.testCode', { code: r.debug_code })}` : r.to)
  })
  const pick = (m: 'totp' | 'whatsapp') => run(async () => {
    setMethod(m); setToken('')
    if (m === 'totp' && step === 'setup' && !otpUrl) setOtpUrl((await api<{ otpauth_url: string }>('/auth/mfa/setup', { method: 'POST' })).otpauth_url)
  })

  const submitToken = (e: FormEvent) => { e.preventDefault(); run(async () => {
    setMe(await api<Me>('/auth/mfa/verify', { method: 'POST', body: { token, method, remember } }))
  }) }

  return (
    <div className="auth">
      <div className="side">
        <div>
          <Logo biz="kids" title={t('app.name')} sub={t('app.tagline')} />
          <h2>{t('auth.hero')}</h2>
          <ul>
            <li><Icon name="cart" />{t('auth.f1')}</li>
            <li><Icon name="award" />{t('auth.f2')}</li>
            <li><Icon name="store" />{t('auth.f3')}</li>
            <li><Icon name="chart" />{t('auth.f4')}</li>
          </ul>
        </div>
        <div className="cap" style={{ color: 'rgba(255,255,255,.55)', position: 'relative' }}>© 2026 {t('app.name')}</div>
      </div>
      <div className="form">
        {step === 'password' ? (
          <form onSubmit={submitPassword}>
            <div style={{ alignSelf: 'flex-end' }}><LangToggle className="btn sm" /></div>
            <div><h1>{t('auth.welcome')}</h1><div className="small muted">{t('auth.sub')}</div></div>
            <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label className="field">{t('auth.password')}<input className="input" type="password" dir="ltr" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            <ErrorText error={err} />
            <button className="btn primary lg" disabled={busy}>{t('auth.submit')}</button>
          </form>
        ) : (
          <form onSubmit={submitToken}>
            <div style={{ alignSelf: 'flex-end' }}><LangToggle className="btn sm" /></div>
            <div><h1>{t(step === 'setup' ? 'auth.mfaSetupTitle' : 'auth.mfaVerifyTitle')}</h1></div>
            {methods.length > 1 && <div className="seg">
              <button type="button" className={method === 'whatsapp' ? 'on' : ''} onClick={() => pick('whatsapp')}>{t('auth.byWhatsapp')}</button>
              <button type="button" className={method === 'totp' ? 'on' : ''} onClick={() => pick('totp')}>{t('auth.byApp')}</button>
            </div>}
            {method === 'whatsapp' && <>
              <div className="small muted">{t('auth.waHelp', { phone: maskedPhone })}</div>
              <button type="button" className="btn" disabled={busy} onClick={sendWhatsApp}><Icon name="whatsapp" />{waSent ? t('auth.resend') : t('auth.sendWa')}</button>
              {waSent && <div className="notice good"><bdi>{t('auth.waSent', { to: waSent })}</bdi></div>}
            </>}
            {method === 'totp' && step === 'setup' && <div className="small muted">{t('auth.mfaSetupHelp')}</div>}
            {method === 'totp' && step === 'setup' && <>
              {qr && <img src={qr} alt="QR" width={220} height={220} style={{ alignSelf: 'center', borderRadius: 12, border: '1px solid var(--line)' }} />}
              <div className="small muted">{t('auth.mfaManual')}</div>
              <code className="code" style={{ alignSelf: 'center', fontSize: 13 }}>{secret.match(/.{1,4}/g)?.join(' ')}</code>
            </>}
            <label className="field">{t('auth.mfaCode')}<input className="input" inputMode="numeric" pattern="\d{6}" maxLength={6} dir="ltr" autoComplete="one-time-code" value={token} onChange={(e) => setToken(e.target.value)} required /></label>
            <label className="row small"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />{t('auth.remember')}</label>
            <ErrorText error={err} />
            <button className="btn primary lg" disabled={busy}>{t('auth.verify')}</button>
          </form>
        )}
      </div>
    </div>
  )
}
