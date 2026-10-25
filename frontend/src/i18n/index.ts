import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ar from './ar.json'
import en from './en.json'

export type Lang = 'ar' | 'en'

const saved = (() => { try { return localStorage.getItem('qassa.lang') as Lang | null } catch { return null } })()

function applyDir(lang: Lang) {
  document.documentElement.lang = lang
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
}

i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: saved ?? 'ar',
  fallbackLng: 'ar',
  interpolation: { escapeValue: false },
})
applyDir(i18n.language as Lang)
i18n.on('languageChanged', (l) => {
  applyDir(l as Lang)
  try { localStorage.setItem('qassa.lang', l) } catch { /* private mode */ }
})

export default i18n
