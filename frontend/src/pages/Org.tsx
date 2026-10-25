import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, type Branch, type LegalEntity } from '../api/client'
import { ErrorText } from '../components/ErrorText'

export type OrgData = { legal_entities: LegalEntity[]; branches: Branch[] }
export const useOrg = () => useQuery({ queryKey: ['org'], queryFn: () => api<OrgData>('/org') })

export default function Org() {
  const { t, i18n } = useTranslation()
  const q = useOrg()
  const name = (x: { name_ar: string; name_en: string }) => (i18n.language === 'en' && x.name_en) || x.name_ar
  if (q.isPending) return <p className="muted">{t('common.loading')}</p>
  if (q.isError) return <><ErrorText error={q.error} /><button className="btn" onClick={() => q.refetch()}>{t('common.retry')}</button></>
  return (
    <div className="grid">
      <div className="head"><h1>{t('nav.org')}</h1></div>
      <h2>{t('org.entities')}</h2>
      <div className="tw"><table><thead><tr><th>{t('acc.entity')}</th><th>{t('org.cr')}</th></tr></thead>
        <tbody>{q.data.legal_entities.map((e) => <tr key={e.id}><td>{name(e)}</td><td className="num">{e.commercial_registration || '—'}</td></tr>)}</tbody></table></div>
      <h2>{t('org.branches')}</h2>
      <div className="tw"><table><thead><tr><th>{t('org.code')}</th><th>{t('acc.branch')}</th><th>{t('org.type')}</th><th>{t('org.active')}</th></tr></thead>
        <tbody>{q.data.branches.map((b) => <tr key={b.id}><td className="num">{b.code}</td><td>{name(b)}</td>
          <td><span className="pill info">{t(`biz.${b.business_type}`)}</span></td><td>{b.is_active ? '✓' : '—'}</td></tr>)}</tbody></table></div>
    </div>
  )
}
