import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Plan } from '../api/client'
import { ErrorText, LangToggle } from '../components/ErrorText'
import { Icon, LogoMark, nameOf, useBizTheme } from '../components/ui'
import { formatKWD } from '../money'

type Site = { whatsapp: string; email: string; trial_days: number; headline_ar?: string; headline_en?: string; sub_ar?: string; sub_en?: string }
const BIZ: [('kids' | 'men' | 'women'), string][] = [['kids', '#0CD273'], ['men', '#C9A24B'], ['women', '#EC6F9A']]
const FEATS = ['cart', 'calendar', 'award', 'store', 'whatsapp', 'chart']
const go = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }

/** Public marketing / pricing site on the platform host (reference: js/apps/pricing-site.js). Contact request, no self sign-up (D-010). */
export default function Landing() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  useBizTheme('')
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/platform/plans') })
  const site = useQuery({ queryKey: ['site'], queryFn: () => api<Site>('/public/site') })
  const trial = site.data?.trial_days ?? 30
  const [form, setForm] = useState({ salon_name: '', contact_name: '', phone: '', email: '', city: '', business_type: 'kids', branches: 1, plan_code: '', message: '', website: '' })
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await api('/public/leads', { method: 'POST', body: form }); setSent(true) } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const feats = (p: Plan) => (lang === 'en' ? p.features_en : p.features_ar) ?? []
  const list = plans.data ?? []
  const inherits = new Set(list.slice(1).map((p) => feats(p)[0]))  // "Everything in <previous plan>" lines
  const all = [...new Set(list.flatMap(feats))].filter((f) => !inherits.has(f))
  const limit = (n: number, one: string, many: string, unlimited: string) => (n >= 99 ? unlimited : `${n} ${n === 1 ? one : many}`)
  return (
    <div className="site">
      <header className="sh"><div className="wrap">
        <div className="logo"><LogoMark biz="kids" /><div><b>{t('app.name')}</b><span>{t('site.tag')}</span></div></div>
        <nav>
          <a href="#feat" className="hide" onClick={go('feat')}>{t('site.features')}</a>
          <a href="#price" className="hide" onClick={go('price')}>{t('site.prices')}</a>
          <LangToggle className="btn sm ghost" short />
          <a href="/login">{t('site.login')}</a>
          <a className="btn brand sm" href="#signup" onClick={go('signup')}>{t('site.cta')}</a>
        </nav>
      </div></header>
      <main className="wrap">
        <section className="hero">
          <div>
            <span className="eyebrow">{t('site.eyebrow', { n: trial })}</span>
            <h1>{(lang === 'en' ? site.data?.headline_en : site.data?.headline_ar) || t('site.headline')}</h1>
            <p>{(lang === 'en' ? site.data?.sub_en : site.data?.sub_ar) || t('site.sub')}</p>
            <div className="row" style={{ marginTop: 18 }}>
              <a className="btn brand lg" style={{ width: 'auto' }} href="#signup" onClick={go('signup')}>{t('site.cta')}</a>
              <a className="btn lg" style={{ width: 'auto' }} href="#price" onClick={go('price')}>{t('site.seePrices')}</a>
            </div>
          </div>
          <div className="mock" aria-label={t('site.mockLabel')}>
            <div className="row sb"><b>{t('site.mockTitle')}</b><span className="pill good">{t('site.example')}</span></div>
            <div className="big">{formatKWD('214.500', lang)}</div>
            {[['site.mockB1', '96.000'], ['site.mockB2', '71.500'], ['site.mockB3', '47.000']].map(([k, v]) => <div className="mrow" key={k}><span>📍 {t(k)}</span><b>{formatKWD(v, lang)}</b></div>)}
          </div>
        </section>

        <section className="sec" id="feat">
          <h2 className="t">{t('site.featTitle')}</h2><p className="st">{t('site.featSub')}</p>
          <div className="feats">{FEATS.map((f, i) => <div className="feat" key={f}><div className="fi"><Icon name={f} /></div>
            <h3>{t(`site.f${i}.t`)}</h3><div className="small muted">{t(`site.f${i}.d`)}</div></div>)}</div>
        </section>

        <section className="sec">
          <h2 className="t">{t('site.bizTitle')}</h2><p className="st">{t('site.bizSub')}</p>
          <div className="bizcards">{BIZ.map(([b, c]) => <div className="bizcard" key={b} style={{ background: c }}>
            <h3>{t('site.bizOf', { b: t(`biz.${b}`) })}</h3><div className="small">{t(`site.biz.${b}`)}</div></div>)}</div>
        </section>

        <section className="sec" id="price">
          <h2 className="t">{t('site.priceTitle')}</h2><p className="st">{t('site.priceSub', { n: trial })}</p>
          <div className="prices">{list.map((p) => <div className={`plan${p.highlight ? ' hl' : ''}`} key={p.id} data-hl={t('site.popular')}>
            <h2>{nameOf(p, lang)}</h2>
            <div className="price">{formatKWD(p.monthly_price, lang)} <span className="small muted">/ {t('plan.month')}</span></div>
            <div className="small">{limit(p.max_branches, t('site.branch'), t('site.branches'), t('site.unlimitedBranches'))} · {limit(p.max_staff, t('site.user'), t('site.users'), t('site.unlimitedUsers'))}</div>
            <ul>{feats(p).map((f) => <li key={f}><Icon name="check" />{f}</li>)}</ul>
            <button className={`btn ${p.highlight ? 'brand' : 'primary'}`} style={{ marginTop: 'auto' }}
              onClick={() => { setForm({ ...form, plan_code: p.code }); document.getElementById('signup')?.scrollIntoView({ behavior: 'smooth' }) }}>{t('site.pick', { n: trial })}</button>
          </div>)}</div>
          {list.length > 1 && <div className="tw cmp" style={{ marginTop: 22 }}><table><thead><tr><th>{t('site.feature')}</th>{list.map((p) => <th key={p.id}>{nameOf(p, lang)}</th>)}</tr></thead>
            <tbody>{all.map((f) => <tr key={f}><td>{f}</td>{list.map((p, i) => {
              const has = list.slice(0, i + 1).some((q) => feats(q).includes(f))
              return <td key={p.id}>{has ? <span style={{ color: 'var(--brand-700)' }}>✓</span> : <span className="muted">—</span>}</td>
            })}</tr>)}</tbody></table></div>}
        </section>

        <section className="sec" id="signup"><div className="grid g2" style={{ alignItems: 'start' }}>
          <div>
            <h2 className="t" style={{ textAlign: 'start' }}>{t('site.contactTitle')}</h2>
            <p className="muted">{t('site.contactSub')}</p>
            {site.data?.whatsapp && <a className="btn brand" href={`https://wa.me/${site.data.whatsapp}?text=${encodeURIComponent(t('site.waText'))}`} target="_blank" rel="noreferrer"><Icon name="whatsapp" />{t('site.waUs')}</a>}
            <div className="faq" style={{ marginTop: 16 }}>{[0, 1, 2, 3].map((i) => <details key={i}><summary>{t(`site.q${i}`)}</summary><div className="small muted" style={{ marginTop: 6 }}>{t(`site.a${i}`)}</div></details>)}</div>
          </div>
          <div className="card" style={{ position: 'relative' }}>
            {sent ? <div className="grid" style={{ textAlign: 'center' }}><div style={{ fontSize: 40, color: 'var(--brand-700)' }}>✓</div>
              <h2>{t('site.sentTitle')}</h2><p className="muted">{t('site.sentSub')}</p></div> :
            <form className="grid" onSubmit={submit}>
              <label className="field">{t('site.salon')}<input className="input" value={form.salon_name} onChange={(e) => setForm({ ...form, salon_name: e.target.value })} required /></label>
              <label className="field">{t('site.you')}<input className="input" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} required /></label>
              <div className="two">
                <label className="field">{t('site.mobile')}<input className="input" dir="ltr" inputMode="tel" placeholder="5xxxxxxx" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required /></label>
                <label className="field">{t('auth.email')}<input className="input" type="email" dir="ltr" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              </div>
              <div className="two">
                <label className="field">{t('site.type')}<select className="input" value={form.business_type} onChange={(e) => setForm({ ...form, business_type: e.target.value })}>
                  {BIZ.map(([b]) => <option key={b} value={b}>{t(`biz.${b}`)}</option>)}</select></label>
                <label className="field">{t('org.branches')}<input className="input" type="number" min={1} max={99} value={form.branches} onChange={(e) => setForm({ ...form, branches: Number(e.target.value) || 1 })} /></label>
              </div>
              <div className="two">
                <label className="field">{t('site.city')}<input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
                <label className="field">{t('platform.plan')}<select className="input" value={form.plan_code} onChange={(e) => setForm({ ...form, plan_code: e.target.value })}>
                  <option value="">{t('site.notSure')}</option>{list.map((p) => <option key={p.code} value={p.code}>{nameOf(p, lang)}</option>)}</select></label>
              </div>
              <label className="field">{t('site.message')}<textarea className="input" rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} /></label>
              <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" style={{ position: 'absolute', width: 1, height: 1, opacity: 0, overflow: 'hidden', pointerEvents: 'none' }}
                value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
              <ErrorText error={err} />
              <button className="btn brand lg" disabled={busy}>{t('site.send')}</button>
              <div className="cap muted">{t('site.privacy')}</div>
            </form>}
          </div>
        </div></section>
      </main>
      <footer className="sf"><div className="wrap row sb">
        <span>© {new Date().getFullYear()} {t('app.name')}</span>
        <span>{site.data?.email}{site.data?.whatsapp && <> · {t('site.wa')} <bdi>+{site.data.whatsapp}</bdi></>}</span>
        <a href="/login">{t('site.login')}</a>
      </div></footer>
    </div>
  )
}
