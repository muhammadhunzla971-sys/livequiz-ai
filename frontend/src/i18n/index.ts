import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import ur from './ur.json'

export const RTL = new Set(['ur', 'ar'])

function stored(): string {
  try {
    return localStorage.getItem('lq.lang') ?? 'en'
  } catch {
    return 'en'
  }
}

export function applyLang(lang: string): void {
  document.documentElement.lang = lang
  document.documentElement.dir = RTL.has(lang) ? 'rtl' : 'ltr'
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ur: { translation: ur } },
  lng: stored(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})
applyLang(i18n.language)

export function setLang(lang: string): void {
  void i18n.changeLanguage(lang)
  applyLang(lang)
  try {
    localStorage.setItem('lq.lang', lang)
  } catch {
    /* ignore */
  }
}

export default i18n
