import { describe, expect, it } from 'vitest'

import { availableIndicators, formatIndicatorValue, getIndicator, makeStepExpression } from './indicators.js'

describe('indicator definitions', () => {
  it('formats evidence values without inventing missing data', () => {
    expect(formatIndicatorValue('lst', 45.678)).toBe('45.68 °C')
    expect(formatIndicatorValue('ndvi', 0.1324)).toBe('0.132')
    expect(formatIndicatorValue('health', null)).toBe('No data')
  })

  it('exposes source and spatial-context metadata', () => {
    const indicator = getIndicator('green')
    expect(indicator.property).toBe('green_min')
    expect(indicator.source).toContain('OpenStreetMap')
    expect(indicator.context).toContain('network')
  })

  it('labels PlanX building morphology as descriptive geometry', () => {
    const indicator = getIndicator('planxCompactness')
    expect(indicator.property).toBe('planx_compactness')
    expect(indicator.group).toBe('PlanX building form')
    expect(indicator.source).toContain('PlanX')
    expect(indicator.context).toContain('geometry')
  })

  it('labels convexity overshoots as numerical artifacts rather than quality scores', () => {
    expect(getIndicator('planxConvexity').context).toContain('numerical overshoot')
  })

  it('builds a MapLibre step expression with a no-data fallback', () => {
    const expression = makeStepExpression('lst')
    expect(expression[0]).toBe('case')
    expect(JSON.stringify(expression)).toContain('lst_c')
    expect(expression).toContain('#8d8d8d')
  })

  it('returns no display-attribute controls for geometry-only building tiles', () => {
    expect(availableIndicators([])).toEqual([])
  })
})
