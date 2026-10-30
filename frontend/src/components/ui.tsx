/** Building blocks that reproduce the approved design's markup (reference/salon-pos-demo). */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export type Biz = 'kids' | 'men' | 'women' | ''

export function Icon({ name }: { name: string }) {
  return <svg className="icon" aria-hidden="true"><use href={`/icons/sprite.svg#i-${name}`} /></svg>
}

/** Same logo as the design: scissors on the brand colour, accent per business type. */
export function LogoMark({ biz }: { biz: Biz }) {
  const acc = {
    kids: <path d="M20 15l4-5 4 5 4-5 4 5 4-5 4 5v4H20z" fill="var(--sun)" />,
    men: <path d="M32 17c-3-5-9-5-12-1 3-1 6 0 8 2 2 1 4 0 4-1zm0 0c3-5 9-5 12-1-3-1-6 0-8 2-2 1-4 0-4-1z" fill="#081510" />,
    women: <><path d="M32 15l-9-6v12zM32 15l9-6v12z" fill="#fff" /><circle cx="32" cy="15" r="2.6" fill="#fff" /></>,
    '': null,
  }[biz]
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="18" fill="var(--brand)" />{acc}
      <g fill="none" stroke="#081510" strokeWidth="4" strokeLinecap="round"><circle cx="23" cy="46" r="6" /><circle cx="41" cy="46" r="6" /><path d="M27 41 41 24M37 41 23 24" /></g></svg>
  )
}

export function Logo({ biz, title, sub }: { biz: Biz; title: string; sub: string }) {
  return <div className="logo"><LogoMark biz={biz} /><div><b>{title}</b><span>{sub}</span></div></div>
}

/** Applies the business-type theme to <html data-biz>, as the design does. */
export function useBizTheme(biz: Biz) {
  useEffect(() => {
    if (biz) document.documentElement.dataset.biz = biz
    else delete document.documentElement.dataset.biz
  }, [biz])
}

export function Head({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return <div className="head"><div><h1>{title}</h1>{sub && <div className="muted small">{sub}</div>}</div>{children && <div className="row">{children}</div>}</div>
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return <div className="card stat"><div className="small muted">{label}</div><div className="v">{value}</div>{sub != null && <div className="cap muted">{sub}</div>}</div>
}

/** Native <dialog> with the design's header/body/footer. `onSubmit` keeps it open until the promise resolves. */
export function Dialog({ open, title, wide, onClose, onSubmit, submitLabel, busy, children }: {
  open: boolean; title: string; wide?: boolean; onClose: () => void; onSubmit?: () => void; submitLabel?: string
  busy?: boolean; children: ReactNode
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  const submit = (e: FormEvent) => { e.preventDefault(); onSubmit?.() }
  return (
    <dialog ref={ref} className={wide ? 'wide' : ''} onClose={onClose} onCancel={(e) => { e.preventDefault(); onClose() }}>
      <form onSubmit={submit}>
        <div className="mh"><h2>{title}</h2><button type="button" className="btn ghost sm" aria-label={t('common.close')} onClick={onClose}><Icon name="close" /></button></div>
        <div className="mb">{open && children}</div>
        {onSubmit && <div className="mf"><button className="btn primary" disabled={busy}>{submitLabel ?? t('common.save')}</button><button type="button" className="btn" onClick={onClose}>{t('common.cancel')}</button></div>}
      </form>
    </dialog>
  )
}

const ToastCtx = createContext<(m: string) => void>(() => undefined)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState('')
  const [on, setOn] = useState(false)
  const timer = useRef<number>(0)
  const show = useCallback((m: string) => {
    setMsg(m); setOn(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOn(false), 2400)
  }, [])
  return <ToastCtx.Provider value={show}>{children}<div className={`toast${on ? ' on' : ''}`} role="status">{msg}</div></ToastCtx.Provider>
}

export const nameOf = (x: { name_ar: string; name_en?: string }, lang: string) => (lang === 'en' && x.name_en) || x.name_ar
