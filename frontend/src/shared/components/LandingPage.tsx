import { APP_NAME, APP_TAGLINE } from '../constants'

type LandingPageProps = {
  title?: string
  subtitle?: string
}

export default function LandingPage({ title = APP_NAME, subtitle = APP_TAGLINE }: LandingPageProps) {
  return (
    <section>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </section>
  )
}
