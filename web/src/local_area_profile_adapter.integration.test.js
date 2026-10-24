import { existsSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import { createLocalAreaProfileAdapter } from './local_area_profile_adapter.js'

const manifestPath = new URL('../public/data/local-profile/manifest.json', import.meta.url)
const baseUrl = process.env.LOCAL_PROFILE_BASE_URL ?? 'http://127.0.0.1:5173'
const hasAssets = existsSync(manifestPath)
const canReachDevServer = await fetch(`${baseUrl}/data/local-profile/manifest.json`).then((response) => response.ok).catch(() => false)
const describeIfAvailable = hasAssets && canReachDevServer ? describe : describe.skip

const baseline = {
  400: { total: 146, central: 0, enriched: 146, storedArea: 83913 },
  800: { total: 386, central: 0, enriched: 386, storedArea: 193363 },
  1200: { total: 1365, central: 0, enriched: 1365, storedArea: 650801 },
}
const auditCenterWgs84 = [72.5765716, 23.0921374]

describeIfAvailable('local area profile adapter HTTP integration', () => {
  it.each([400, 800, 1200])('matches the Python baseline at %dm', async (radiusM) => {
    const adapter = createLocalAreaProfileAdapter({ manifestUrl: `${baseUrl}/data/local-profile/manifest.json` })
    const result = await adapter.query({ center: auditCenterWgs84, radiusM })
    const buildingData = result.sections.buildings.data
    expect(result.sections.buildings.status).toBe('available')
    expect(buildingData.totalLocationCount).toBe(baseline[radiusM].total)
    expect(buildingData.centralLocationCount).toBe(baseline[radiusM].central)
    expect(buildingData.enrichedLocationCount).toBe(baseline[radiusM].enriched)
    expect(buildingData.summedStoredAreaM2).toBe(baseline[radiusM].storedArea)
    expect(buildingData).not.toHaveProperty('buildingCount')
    expect(buildingData).not.toHaveProperty('footprintCoverageM2')
    expect(result.sections.spaceSyntaxCentrality.data.centrality.closeness.weightedMean).toBeGreaterThan(0)
    expect(result.diagnostics.durationMs).toBeGreaterThanOrEqual(0)
    expect(Object.values(result.diagnostics.assets).every(({ estimatedDecodedBytes }) => estimatedDecodedBytes >= 0)).toBe(true)
    expect(result.diagnostics.requestBytes).toBeNull()
  }, 30000)

  it('matches the frozen Python exact-boundary baseline for TPS-20/A', async () => {
    const collection = await fetch(`${baseUrl}/data/tps-provisional.geojson`).then((response) => response.json())
    const feature = collection.features.find(({ properties }) => String(properties.tps_no) === 'TPS-20/A')
    const adapter = createLocalAreaProfileAdapter({ manifestUrl: `${baseUrl}/data/local-profile/manifest.json` })
    const result = await adapter.query({ selection: { type: 'tps', geometry: feature.geometry, ...feature.properties } })

    expect(result.selection.areaM2).toBeCloseTo(824267.96, 1)
    expect(result.sections.buildings.data.totalLocationCount).toBe(327)
    expect(result.sections.buildings.data.provisionalHeightM.summary.mean).toBeCloseTo(4.308869, 5)
    expect(result.sections.buildings.data.suhi).toMatchObject({ status: 'available', kind: 'categorical' })
    expect(result.sections.buildings.data.suhi.availability.available).toBeGreaterThan(0)
    expect(result.sections.buildings.data.suhi.distribution.categories.some(({ count }) => count > 0)).toBe(true)
    expect(result.sections.buildings.data.suhi.distribution.categories.reduce((sum, { count }) => sum + count, 0)).toBe(result.sections.buildings.data.suhi.availability.available)
    expect(result.sections.streetsConnectivity.data.clippedLengthM).toBeCloseTo(26157.953, 2)
    expect(result.sections.streetsConnectivity.data.intersectionDensityPerKm2).toBeCloseTo(123.746166, 5)
    expect(result.sections.streetsConnectivity.data.linkNodeRatio).toBeCloseTo(1.338673, 5)
    expect(result.sections.streetsConnectivity.data.connectedNodeRatio).toBeCloseTo(0.011442, 5)
    expect(result.sections.parksEducation.data.parks.count).toBe(1)
    expect(result.sections.parksEducation.data.schools.count).toBe(1)
  }, 30000)
})
