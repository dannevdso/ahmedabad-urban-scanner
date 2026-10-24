import { describe, expect, it } from 'vitest'

import { buildFloodRiskDetails } from './flood_risk_details.js'

describe('flood-risk details', () => {
  it('preserves the source risk class for inspection', () => {
    expect(buildFloodRiskDetails({ uf_risk: 'High Risk Areas' })).toEqual({
      title: 'High Risk Areas',
      rows: [['Risk class', 'High Risk Areas']],
    })
  })

  it('uses an explicit unavailable state when the source attribute is absent', () => {
    expect(buildFloodRiskDetails({})).toEqual({
      title: 'Flood-risk zone',
      rows: [['Risk class', 'Unavailable']],
    })
  })
})
