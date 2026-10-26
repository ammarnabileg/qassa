import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'

/** Maps stable API error codes to translated messages (never shows raw server text to staff). */
export function ErrorText({ error }: { error: unknown }) {
  const { t, i18n } = useTranslation()
  if (!error) return null
  const code = error instanceof ApiError ? error.code : 'unknown'
  const key = `errors.${code}`
  return <div className="notice bad" role="alert">{i18n.exists(key) ? t(key) : t('errors.unknown')}</div>
}

export function LangToggle({ className = 'btn ghost', short = false }: { className?: string; short?: boolean }) {
  const { t, i18n } = useTranslation()
  return <button type="button" className={className} title={t('common.language')} onClick={() => i18n.changeLanguage(i18n.language === 'ar' ? 'en' : 'ar')}>{short ? (i18n.language === 'ar' ? 'EN' : 'ع') : t('common.language')}</button>
}
