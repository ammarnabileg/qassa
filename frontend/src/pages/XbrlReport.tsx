import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { ErrorText } from '../components/ErrorText'
import { useSave } from '../components/hooks'
import { Head, Icon, useToast } from '../components/ui'
import { formatKWD } from '../money'
import { useOrg } from './Org'

type XLine = { tag: string; label_ar: string; section: string; cy: string; py: string }
type Report = { year_end: string; prior_year_end: string; financial_position: XLine[]; profit_or_loss: XLine[]
  totals: { tag: string; cy: string; py: string }[]; checks: { id: string; ok: boolean; values: string[] }[] }
type Mapping = { accounts: { account_id: number; code: string; name_ar: string; name_en: string; type: string; tag: string | null; custom: boolean }[]
  lines: { statement: 'fp' | 'pl'; section: string; tag: string; label_ar: string }[] }
type Tab = 'fp' | 'pl' | 'map'
const FP_TYPES = ['asset', 'liability', 'equity']

export default function XbrlReport() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language as 'ar' | 'en'
  const { can } = useAuth()
  const toast = useToast()
  const org = useOrg()
  const entity = org.data?.legal_entities[0]
  const [yearEnd, setYearEnd] = useState(`${new Date().getFullYear() - 1}-12-31`)
  const [tab, setTab] = useState<Tab>('fp')
  const rep = useQuery({ enabled: !!entity, queryKey: ['xbrl', entity?.id, yearEnd],
    queryFn: () => api<Report>(`/accounting/xbrl?legal_entity_id=${entity!.id}&year_end=${yearEnd}`) })
  const map = useQuery({ enabled: !!entity && tab === 'map', queryKey: ['xbrlmap', entity?.id],
    queryFn: () => api<Mapping>(`/accounting/xbrl/mapping?legal_entity_id=${entity!.id}`) })
  const mSave = useSave<Mapping>([['xbrlmap'], ['xbrl']], () => toast(t('common.saved')))
  const lines = tab === 'fp' ? rep.data?.financial_position : rep.data?.profit_or_loss
  const totals = rep.data?.totals.filter((x) => (tab === 'fp' ? !['ifrs-full:Revenue', 'ifrs-full:ProfitLoss'].includes(x.tag) : ['ifrs-full:Revenue', 'ifrs-full:ProfitLoss'].includes(x.tag)))
  const copy = (col: 'cy' | 'py') => navigator.clipboard.writeText((lines ?? []).map((l) => `${l.tag}\t${l.label_ar}\t${l[col]}`).join('\n')).then(() => toast(t('usr.copied')))
  const csv = () => {
    const rows = [['statement', 'tag', 'label_ar', 'current_year', 'prior_year'],
      ...(rep.data!.financial_position.map((l) => ['fp', l.tag, l.label_ar, l.cy, l.py])),
      ...(rep.data!.profit_or_loss.map((l) => ['pl', l.tag, l.label_ar, l.cy, l.py])),
      ...(rep.data!.totals.map((l) => ['total', l.tag, '', l.cy, l.py]))]
    const blob = new Blob(['﻿' + rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `moci-xbrl-${yearEnd}.csv`; a.click()
  }
  return (
    <>
      <Head title={t('nav.xbrl')} sub={t('xbrl.sub')}>
        <label className="field">{t('xbrl.yearEnd')}<input className="input" type="date" value={yearEnd} onChange={(e) => e.target.value && setYearEnd(e.target.value)} /></label>
        {rep.data && <button className="btn" onClick={csv}><Icon name="download" />CSV</button>}
      </Head>
      <div className="notice"><Icon name="alert" />{t('xbrl.draft')}</div>
      <ErrorText error={rep.error} />
      {rep.data && <div className="row">{rep.data.checks.map((c) => <span key={c.id} className={`pill ${c.ok ? 'good' : 'bad'}`} title={c.values.join(' · ')}>
        {t(`xbrl.chk.${c.id.startsWith('VAL_BS') ? 'bs' : 'mapped'}`)}{c.id.endsWith('_PY') ? ` (${t('xbrl.py')})` : ''}: {c.ok ? '✓' : c.values.slice(0, 3).join('، ')}</span>)}</div>}
      <div className="tabs">{(['fp', 'pl', 'map'] as Tab[]).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`xbrl.tab.${x}`)}</button>)}</div>

      {tab !== 'map' && rep.data && <>
        <div className="row"><button className="btn sm" onClick={() => copy('cy')}><Icon name="copy" />{t('xbrl.copyCy')}</button>
          <button className="btn sm" onClick={() => copy('py')}><Icon name="copy" />{t('xbrl.copyPy')}</button></div>
        <div className="tw"><table><thead><tr><th>{t('xbrl.line')}</th><th>XBRL</th><th className="n">{rep.data.year_end.slice(0, 4)}</th><th className="n">{rep.data.prior_year_end.slice(0, 4)}</th></tr></thead>
          <tbody>{lines?.map((l) => <tr key={l.tag}><td>{l.label_ar}<div className="cap muted">{t(`xbrl.sec.${l.section}`)}</div></td>
            <td className="small" dir="ltr" style={{ textAlign: 'start' }}><code>{l.tag}</code></td>
            <td className="n money">{formatKWD(l.cy, lang)}</td><td className="n money">{formatKWD(l.py, lang)}</td></tr>)}
            {lines?.length === 0 && <tr><td colSpan={4} className="empty">{t('xbrl.noData')}</td></tr>}
            {totals?.map((l) => <tr key={l.tag} style={{ fontWeight: 700 }}><td>{t(`xbrl.tot.${l.tag.split(':')[1]}`)}</td>
              <td className="small" dir="ltr" style={{ textAlign: 'start' }}><code>{l.tag}</code></td>
              <td className="n money">{formatKWD(l.cy, lang)}</td><td className="n money">{formatKWD(l.py, lang)}</td></tr>)}</tbody></table></div>
        {tab === 'pl' && <div className="notice info"><Icon name="info" />{t('xbrl.cfNote')}</div>}
      </>}

      {tab === 'map' && <>
        <div className="small muted">{t('xbrl.mapHelp')}</div>
        <ErrorText error={mSave.error} />
        <div className="tw"><table><thead><tr><th>{t('acc.account')}</th><th>{t('xbrl.line')}</th><th /></tr></thead>
          <tbody>{map.data?.accounts.map((a) => {
            const st = FP_TYPES.includes(a.type) ? 'fp' : 'pl'
            return <tr key={a.account_id}><td><span className="num">{a.code}</span> {lang === 'en' ? a.name_en : a.name_ar}</td>
              <td><select className="input" disabled={!can('accounting.setup') || mSave.busy} value={a.tag ?? ''}
                onChange={(e) => mSave.save({ path: `/accounting/xbrl/mapping?legal_entity_id=${entity!.id}`, method: 'PUT', body: { account_id: a.account_id, tag: e.target.value } })}>
                <option value="">{t('xbrl.useDefault')}</option>
                {map.data!.lines.filter((l) => l.statement === st).map((l) => <option key={l.tag} value={l.tag}>{l.label_ar}</option>)}</select></td>
              <td>{a.custom ? <span className="pill info">{t('xbrl.custom')}</span> : a.tag ? <span className="pill mute">{t('xbrl.default')}</span> : <span className="pill bad">{t('xbrl.unmapped')}</span>}</td></tr>
          })}</tbody></table></div>
      </>}
    </>
  )
}
