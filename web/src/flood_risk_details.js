export function buildFloodRiskDetails(properties = {}) {
  const riskClass = properties.uf_risk || 'Unavailable'
  return {
    title: riskClass === 'Unavailable' ? 'Flood-risk zone' : riskClass,
    rows: [['Risk class', riskClass]],
  }
}
