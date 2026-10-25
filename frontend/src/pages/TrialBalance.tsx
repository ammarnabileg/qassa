import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type TBRow } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { formatKWD } from '../money'
import { useOrg } from './Org'

type TB = { rows: TBRow[]; total_debit: string; total_credit: string; balanced: boolean }

const today = () => new Date().toISOString().slice(0, 10)
const monthStart = () => today().slice(0, 8) + '01'

export default function TrialBalance() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { membership } = useAuth()
  const org = useOrg()
  const [params, setParams] = useState({ from: monthStart(), to: today(), branch: '' })
  const [applied, setApplied] = useState(params)
  const entity = org.data?.legal_entities[0]
  const mustPickBranch = membership && !membership.all_branches
  const q = useQuery({
    enabled: !!entity && (!mustPickBranch || !!applied.branch),
    queryKey: ['tb', entity?.id, applied],
    queryFn: () => api<TB>(`/accounting/trial-balance?legal_entity_id=${entity!.id}&from=${applied.from}&to=${applied.to}${applied.branch ? `&branch_id=${applied.branch}` : ''}`),
  })
  const name = (r: TBRow) => (lang === 'en' ? r.name_en : r.name_ar)
  return (
    <div className="grid">
      <div className="head"><h1>{t('nav.trialBalance')}</h1>
        {q.data && <span className={`pill ${q.data.balanced ? 'good' : 'bad'}`}>{t(q.data.balanced ? 'acc.balanced' : 'acc.unbalanced')}</span>}
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); setApplied(params) }}>
        <label className="field">{t('acc.from')}<input className="input" type="date" value={params.from} onChange={(e) => setParams({ ...params, from: e.target.value })} /></label>
        <label className="field">{t('acc.to')}<input className="input" type="date" value={params.to} onChange={(e) => setParams({ ...params, to: e.target.value })} /></label>
        <label className="field">{t('acc.branch')}<select className="input" value={params.branch} onChange={(e) => setParams({ ...params, branch: e.target.value })}>
          {!mustPickBranch && <option value="">{t('acc.allBranches')}</option>}
          {mustPickBranch && <option value="" disabled>—</option>}
          {org.data?.branches.map((b) => <option key={b.id} value={b.id}>{lang === 'en' && b.name_en ? b.name_en : b.name_ar}</option>)}
        </select></label>
        <button className="btn primary" style={{ alignSelf: 'flex-end' }}>{t('acc.show')}</button>
      </form>
      {q.isError && <ErrorText error={q.error} />}
      {q.isFetching && <p className="muted">{t('common.loading')}</p>}
      {q.data && (q.data.rows.length === 0 ? <p className="muted">{t('common.empty')}</p> :
        <div className="tw"><table>
          <thead><tr><th>{t('acc.code')}</th><th>{t('acc.account')}</th><th className="n">{t('acc.opening')}</th><th className="n">{t('acc.debit')}</th><th className="n">{t('acc.credit')}</th><th className="n">{t('acc.closing')}</th></tr></thead>
          <tbody>{q.data.rows.map((r) => <tr key={r.account_id}><td className="num">{r.code}</td><td>{name(r)}</td>
            <td className="n num">{formatKWD(r.opening, lang)}</td><td className="n num">{formatKWD(r.debit, lang)}</td>
            <td className="n num">{formatKWD(r.credit, lang)}</td><td className="n num">{formatKWD(r.closing, lang)}</td></tr>)}
            <tr><td /><td><b>{t('acc.totals')}</b></td><td /><td className="n num"><b>{formatKWD(q.data.total_debit, lang)}</b></td><td className="n num"><b>{formatKWD(q.data.total_credit, lang)}</b></td><td /></tr>
          </tbody></table></div>)}
    </div>
  )
}
