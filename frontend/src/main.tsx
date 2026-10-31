import { asset, BASE } from './base'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ApiError } from './api/client'
import App from './App'
import { AuthProvider } from './auth'
import { ToastProvider } from './components/ui'
import './i18n'
import './styles/design.css'
import './styles/site.css'
import './styles/app.css'
import './styles/tablet.css'

console.info(`Qassa ${__APP_VERSION__} (${__APP_CHANNEL__})`)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
})

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => { navigator.serviceWorker.register(asset('sw.js'), { scope: BASE ? BASE + '/' : '/' }).catch(() => undefined) })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={BASE || undefined}><AuthProvider><ToastProvider><App /></ToastProvider></AuthProvider></BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
