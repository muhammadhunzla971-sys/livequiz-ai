import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Shell } from '../components/Chrome'

export default function NotFound() {
  const { t } = useTranslation()
  return (
    <Shell>
      <div className="mt-16 text-center">
        <p className="font-display text-7xl font-extrabold">404</p>
        <h1 className="mt-2 text-3xl font-extrabold">{t('nf.title', 'Page not found')}</h1>
        <p className="mt-2 text-muted">{t('nf.body', 'That link does not lead anywhere.')}</p>
        <Link
          to="/"
          className="mt-6 inline-flex min-h-[44px] items-center rounded-xl bg-ink px-5 font-display font-bold text-paper"
        >
          {t('nf.home', 'Back to start')}
        </Link>
      </div>
    </Shell>
  )
}
