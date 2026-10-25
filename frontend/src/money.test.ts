import { describe, expect, it } from 'vitest'
import { formatKWD, fromFils, toFils } from './money'

describe('fils arithmetic', () => {
  it('parses and sums exactly without floats', () => {
    expect(toFils('0.1') + toFils('0.2')).toBe(toFils('0.3'))
    expect(fromFils(toFils('1.005') + toFils('2.995'))).toBe('4.000')
  })
  it('rejects more than 3 decimals and junk', () => {
    expect(() => toFils('1.0005')).toThrow()
    expect(() => toFils('abc')).toThrow()
  })
  it('formats per language', () => {
    expect(formatKWD('-1234.5', 'en')).toBe('-1,234.500 KWD')
    expect(formatKWD(toFils('12'), 'ar')).toBe('12.000 د.ك')
  })
})
