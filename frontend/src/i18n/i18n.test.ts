import { describe, expect, it } from 'vitest'
import ar from './ar.json'
import en from './en.json'

const keys = (o: object, p = ''): string[] =>
  Object.entries(o).flatMap(([k, v]) => (typeof v === 'object' ? keys(v, `${p}${k}.`) : [`${p}${k}`]))

describe('translations', () => {
  it('Arabic and English define exactly the same keys', () => {
    expect(keys(ar).sort()).toEqual(keys(en).sort())
  })
  it('no empty strings', () => {
    for (const lang of [ar, en]) for (const k of keys(lang)) expect(k.split('.').reduce((o: any, x) => o[x], lang)).not.toBe('')
  })
})
