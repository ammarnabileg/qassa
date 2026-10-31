/** Where the back-office runs. On a salon's own address it lives under /dashboard (the site root is the customer PWA);
 *  on the platform address it is at the root. Static files are always under the build base (/_q/). */
export const BASE = typeof window !== 'undefined' && /^\/dashboard(\/|$)/.test(window.location.pathname) ? '/dashboard' : ''
export const link = (path: string) => BASE + path
export const asset = (file: string) => import.meta.env.BASE_URL + file.replace(/^\//, '')
/** Path inside the app, without the /dashboard prefix. */
export const here = () => (typeof window === 'undefined' ? '/' : window.location.pathname.slice(BASE.length) || '/')
