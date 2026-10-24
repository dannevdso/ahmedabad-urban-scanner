import { describe, expect, it, vi } from 'vitest'

import {
  createLocalAreaProfileAdapter,
  metricBboxForCircle,
  transformWgs84ToMetric,
} from './local_area_profile_adapter.js'

const manifest = {
  contractVersion: 'local-area-profile.static.v1',
  metricCrs: 'EPSG:32643',
  radiiM: [400, 800, 1200],
  provenance: { manifest: 'build://manifest.json' },
  assets: {
    buildingLocations: { url: 'building-locations.fgb', accuracy: 'exact' },
    streets: { url: 'streets.fgb', accuracy: 'exact' },
    centrality: { url: 'centrality.fgb', accuracy: 'exact' },
    spaceSyntax: { url: 'syntax.fgb', accuracy: 'exact' },
    heatRisk: { url: 'heat.fgb', accuracy: 'source-approximate' },
    parks: { url: 'parks.fgb', accuracy: 'exact' },
    schools: { url: 'schools.fgb', accuracy: 'exact' },
    gtfsStops: { url: 'stops.fgb', accuracy: 'exact' },
    routeReach: { url: 'reach.fgb', accuracy: 'source-approximate' },
  },
}

const pointFeature = (x, y, properties = {}) => ({
  type: 'Feature', properties, geometry: { type: 'Point', coordinates: [x, y] },
})
const lineFeature = (coordinates, properties = {}) => ({
  type: 'Feature', properties, geometry: { type: 'LineString', coordinates },
})
const polygonFeature = (coordinates, properties = {}) => ({
  type: 'Feature', properties, geometry: { type: 'Polygon', coordinates: [coordinates] },
})

const fixtures = {
  'building-locations.fgb': [
    pointFeature(500000, 2550000, { zone_group: 'central' }),
    pointFeature(501000, 2550000, { zone_group: 'enriched', height_m: 12, area_m2: 20, volume_m3: 240, suhi: 'High SUHI' }),
  ],
  'streets.fgb': [lineFeature([[499000, 2550000], [501000, 2550000]], { edge_id: 'e1', u: 'a', v: 'b' })],
  'centrality.fgb': [lineFeature([[499000, 2550000], [501000, 2550000]], { edge_id: 'e1', u: 'a', v: 'b', betweenness: 2 })],
  'syntax.fgb': [lineFeature([[499000, 2550000], [501000, 2550000]], { edge_id: 'e1', u: 'a', v: 'b', closeness: 4, straightness: 6 })],
  'heat.fgb': [polygonFeature([[499900, 2549900], [500100, 2549900], [500100, 2550100], [499900, 2550100], [499900, 2549900]], { risk: 0.75 })],
  'parks.fgb': [pointFeature(500000, 2550000)],
  'schools.fgb': [pointFeature(500050, 2550000)],
  'stops.fgb': [pointFeature(500000, 2550000, { route_ids: ['R1'] })],
  'reach.fgb': [polygonFeature([[499900, 2549900], [500100, 2549900], [500100, 2550100], [499900, 2550100], [499900, 2549900]], { route_ids: ['R1'] })],
  'flood-risk.fgb': [
    polygonFeature([[499900, 2549900], [500000, 2549900], [500000, 2550100], [499900, 2550100], [499900, 2549900]], { uf_risk: 'Very High Risk Areas' }),
    polygonFeature([[500000, 2549900], [500100, 2549900], [500100, 2550100], [500000, 2550100], [500000, 2549900]], { uf_risk: 'High Risk Areas' }),
  ],
}

describe('local area profile vector adapter', () => {
  it('transforms WGS84 center to the manifest metric CRS and computes metric bbox', () => {
    const center = transformWgs84ToMetric([72.5765716, 23.0921374], 'EPSG:32643')
    expect(center[0]).toBeCloseTo(251761, 0)
    expect(center[1]).toBeCloseTo(2555779, 0)
    expect(metricBboxForCircle([500000, 2550000], 400)).toEqual([499600, 2549600, 500400, 2550400])
  })

  it('queries FlatGeobuf candidates with a FlatGeobuf rectangle object', async () => {
    const calls = []
    const deserialize = vi.fn(async function* (url, options) {
      calls.push({ url, options })
      for (const feature of fixtures[url] ?? []) yield feature
    })
    const adapter = createLocalAreaProfileAdapter({
      manifest,
      deserialize,
      centerTransform: () => [500000, 2550000],
    })

    const result = await adapter.query({ center: [72.576, 23.092], radiusM: 400 })

    expect(result.contractVersion).toBe('local-area-profile.v1')
    expect(result.center).toEqual([72.576, 23.092])
    expect(result.metricCenter).toEqual([500000, 2550000])
    expect(result.sections.buildings.data.totalLocationCount).toBe(1)
    expect(result.sections.buildings.data.enrichedLocationCount).toBe(0)
    expect(result.sections.buildings.data).not.toHaveProperty('footprintCoverageM2')
    expect(result.sections.streetsConnectivity.data.clippedLengthM).toBeCloseTo(800, 5)
    expect(result.sections.spaceSyntaxCentrality.data.centrality.betweenness.weightedMean).toBeCloseTo(2)
    expect(result.sections.environment.data.heatRisk.mean).toBeCloseTo(0.75)
    expect(result.sections.parksEducation.data.parks.count).toBe(1)
    expect(result.sections.publicTransport.data.stopsInsideCircle).toBe(1)
    expect(result.sections.publicTransport.data.routesServingStopsInsideCircle).toEqual(['R1'])
    expect(calls).toHaveLength(Object.keys(manifest.assets).length)
    expect(calls.every(({ options }) => options.rect && Object.keys(options.rect).sort().join(',') === 'maxX,maxY,minX,minY')).toBe(true)
    expect(calls.every(({ options }) => !('signal' in options))).toBe(true)
  })

  it('parses serialized route-id arrays before matching transit stops and reach cells', async () => {
    const transitManifest = { ...manifest, assets: { gtfsStops: { url: 'serialized-stops.fgb' }, routeReach: { url: 'serialized-reach.fgb' } } }
    const serialized = {
      'serialized-stops.fgb': [pointFeature(500000, 2550000, { route_ids: "['R1', 'R2']" })],
      'serialized-reach.fgb': [polygonFeature([[499900, 2549900], [500100, 2549900], [500100, 2550100], [499900, 2550100], [499900, 2549900]], { route_ids: "['R2']" })],
    }
    const adapter = createLocalAreaProfileAdapter({ manifest: transitManifest, deserialize: async function* (url) { yield* serialized[url] ?? [] }, centerTransform: () => [500000, 2550000] })

    const result = await adapter.query({ center: [72.58, 23.025], radiusM: 400 })

    expect(result.sections.publicTransport.data.routesServingStopsInsideCircle).toEqual(['R1', 'R2'])
    expect(result.sections.publicTransport.data.routeReachCells).toBe(1)
  })

  it('returns clipped flood-risk area by source class with explicit unavailable Low', async () => {
    const floodManifest = { ...manifest, assets: { floodRisk: { url: 'flood-risk.fgb', claim_type: 'exact source geometry/fields' } } }
    const adapter = createLocalAreaProfileAdapter({ manifest: floodManifest, deserialize: async function* (url) { yield* fixtures[url] ?? [] }, centerTransform: () => [500000, 2550000] })
    const result = await adapter.query({ center: [72.576, 23.092], radiusM: 400 })
    const flood = result.sections.environment.data.floodRiskArea
    expect(flood.status).toBe('available')
    expect(flood.unit).toBe('m²')
    expect(flood.categories.map(({ label }) => label)).toEqual(['Very high', 'High', 'Moderate', 'Low'])
    expect(flood.categories[0].areaM2).toBeCloseTo(20000)
    expect(flood.categories[1].areaM2).toBeCloseTo(20000)
    expect(flood.categories[3]).toMatchObject({ key: 'low', label: 'Low', sourceClass: null, areaM2: null, status: 'unavailable' })
    expect(flood.totalClassifiedAreaM2).toBeCloseTo(40000)
    expect(flood.caveat).toMatch(/no low/i)
  })


  it('fails closed without requesting a retired polygon asset when points are absent', async () => {
    const calls = []
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { streets: manifest.assets.streets } },
      deserialize: async function* (url) { calls.push(url); yield* fixtures[url] ?? [] },
      centerTransform: () => [500000, 2550000],
    })
    const result = await adapter.query({ center: [72.576, 23.092], radiusM: 400 })
    expect(result.sections.buildings).toMatchObject({ status: 'unavailable', data: null })
    expect(result.sections.buildings.reason).toMatch(/polygon fallback is retired/i)
    expect(calls).not.toContain('buildings.fgb')
  })

  it('uses authoritative topology IDs, fixed bins, provenance, and explicit unavailable values', async () => {
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { buildingLocations: manifest.assets.buildingLocations, streets: manifest.assets.streets } },
      deserialize: async function* (url) { yield* fixtures[url] ?? [] },
      centerTransform: () => [500000, 2550000],
    })
    const result = await adapter.query({ center: [72.576, 23.092], radiusM: 400 })
    expect(result.sections.buildings.data.provisionalAreaM2.distribution.method).toBe('fixed')
    expect(result.sections.streetsConnectivity.data.topologyRule).toMatch(/authoritative u\/v/i)
    expect(result.sections.environment.status).toBe('unavailable')
    expect(result.sections.environment.accuracy).toBe('unavailable')
    expect(result.provenance.manifest).toBe('build://manifest.json')
  })

  it('caches manifest/assets and aborts stale requests without fabricating a result', async () => {
    const fetchManifest = vi.fn(async () => ({ json: async () => manifest }))
    const deserialize = vi.fn(async function* (_url, _bbox, { signal } = {}) {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, 5)
        signal?.addEventListener('abort', () => { clearTimeout(timer); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })) }, { once: true })
      })
      yield fixtures['building-locations.fgb'][0]
    })
    const adapter = createLocalAreaProfileAdapter({
      manifestUrl: 'manifest.json', fetchImpl: fetchManifest, deserialize, centerTransform: () => [500000, 2550000],
    })
    const first = adapter.query({ center: [72.576, 23.092], radiusM: 400 })
    const second = adapter.query({ center: [72.576, 23.092], radiusM: 400 })
    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    await second
    expect(fetchManifest).toHaveBeenCalledTimes(1)
  })

  it('returns a cheap preview and defers vector decoding until release', async () => {
    const deserialize = vi.fn(async function* () { yield fixtures['building-locations.fgb'][0] })
    const adapter = createLocalAreaProfileAdapter({ manifest, deserialize, centerTransform: () => [500000, 2550000] })
    const preview = await adapter.query({ center: [72.576, 23.092], radiusM: 400, phase: 'preview' })
    expect(preview.sections.overview.data.preview).toBe(true)
    expect(deserialize).not.toHaveBeenCalled()
  })

  it('uses an exact TPS polygon selection for boundary-inclusive building locations and bounded FlatGeobuf reads', async () => {
    const buildingLocations = [
      pointFeature(500000, 2550000, { zone_group: 'central' }),
      pointFeature(500010, 2550000, { zone_group: 'enriched', height_m: 12, area_m2: 20, volume_m3: 240, suhi: ' High SUHI ' }),
      pointFeature(500020, 2550000, { zone_group: 'enriched', height_m: 99, area_m2: 99, volume_m3: 9801, suhi: 'Extreme High SUHI' }),
    ]
    const calls = []
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { buildingLocations: { url: 'building-locations.fgb', accuracy: 'exact' } } },
      deserialize: async function* (url, options) { calls.push({ url, options }); yield* url === 'building-locations.fgb' ? buildingLocations : [] },
      centerTransform: () => [500000, 2550000],
      geometryTransform: (geometry) => geometry,
    })
    const selection = {
      type: 'tps',
      source_id: 'internal-duplicate-a',
      tps_name: 'Duplicate',
      tps_no: null,
      tps_status: 'provisional',
      geometry: { type: 'Polygon', coordinates: [[[500000, 2549990], [500010, 2549990], [500010, 2550010], [500000, 2550010], [500000, 2549990]]] },
    }

    const result = await adapter.query({ selection })

    expect(result.selection).toMatchObject({ type: 'tps', source_id: 'internal-duplicate-a', tps_name: 'Duplicate', tps_no: null, tps_status: 'provisional', areaM2: 200 })
    expect(result.sections.buildings.data).toMatchObject({
      totalLocationCount: 2,
      centralLocationCount: 1,
      enrichedLocationCount: 1,
      buildingInclusionRule: 'boundary_inclusive_point_coverage',
    })
    expect(result.sections.buildings.data.provisionalHeightM.availability).toEqual({ available: 1, denominator: 1 })
    expect(result.sections.buildings.data.provisionalAreaM2.summary.mean).toBe(20)
    expect(result.sections.buildings.data.suhi.summary).toEqual({ dominantClass: 'High' })
    expect(calls).toEqual([{ url: 'building-locations.fgb', options: { rect: { minX: 500000, minY: 2549990, maxX: 500010, maxY: 2550010 } } }])
  })

  it('uses building locations as the circle primary with boundary-inclusive membership and no polygon hybrid', async () => {
    const locations = [
      pointFeature(500000, 2550000, { zone_group: 'central', height_m: 999, area_m2: 99999, volume_m3: 999999, suhi: 'Extreme High SUHI' }),
      pointFeature(500400, 2550000, { zone_group: 'enriched', height_m: 2, area_m2: 10, volume_m3: 20, suhi: 'low SUHI' }),
      pointFeature(500401, 2550000, { zone_group: 'enriched', height_m: 12, area_m2: 100, volume_m3: 1200, suhi: 'High SUHI' }),
    ]
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { buildingLocations: { url: 'building-locations.fgb', accuracy: 'exact' } } },
      deserialize: async function* (url) { yield* url === 'building-locations.fgb' ? locations : (fixtures[url] ?? []) },
      centerTransform: () => [500000, 2550000],
    })

    const data = (await adapter.query({ center: [72.576, 23.092], radiusM: 400 })).sections.buildings.data

    expect(data).toMatchObject({ totalLocationCount: 2, centralLocationCount: 1, enrichedLocationCount: 1 })
    expect(data.provisionalAreaM2.summary.mean).toBe(10)
    expect(data).not.toHaveProperty('buildingCount')
    expect(data).not.toHaveProperty('footprintCoverageM2')
    expect(data).not.toHaveProperty('footprintAreaM2')
    expect(data).not.toHaveProperty('buildingMetrics')
  })


  it('reports point metrics with enriched denominators and preserves ordered categorical classes', async () => {
    const locations = [
      pointFeature(500000, 2550000, { zone_group: 'central', height_m: 999, area_m2: 99999, volume_m3: 999999, suhi: 'Extreme High SUHI' }),
      pointFeature(500010, 2550000, { zone_group: 'enriched', height_m: 2, area_m2: 10, volume_m3: 20, suhi: 'low SUHI' }),
      pointFeature(500020, 2550000, { zone_group: 'enriched', height_m: 12, area_m2: 100, volume_m3: 1200, suhi: 'High SUHI' }),
      pointFeature(500030, 2550000, { zone_group: 'enriched', height_m: 125, area_m2: 6000, volume_m3: 750000, suhi: 'mystery class' }),
      pointFeature(500040, 2550000, { zone_group: 'enriched' }),
    ]
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { buildingLocations: { url: 'building-locations.fgb', accuracy: 'exact' } } },
      deserialize: async function* (url) { yield* url === 'building-locations.fgb' ? locations : (fixtures[url] ?? []) },
      centerTransform: () => [500000, 2550000],
    })

    const data = (await adapter.query({ center: [72.576, 23.092], radiusM: 400 })).sections.buildings.data

    expect(data.totalLocationCount).toBe(5)
    expect(data.centralLocationCount).toBe(1)
    expect(data.enrichedLocationCount).toBe(4)
    expect(data).not.toHaveProperty('buildingCount')
    expect(data).not.toHaveProperty('buildingCountHistogram')
    expect(data).not.toHaveProperty('footprintCoverageM2')
    expect(data).not.toHaveProperty('footprintCoveragePct')
    expect(data).not.toHaveProperty('footprintCoverageAccuracy')
    expect(data).not.toHaveProperty('footprintAreaM2')
    expect(data).not.toHaveProperty('buildingMetrics')
    expect(data.suhi).toMatchObject({ status: 'available', availability: { available: 3, denominator: 4 } })
    expect(data.suhi.summary).toEqual({ dominantClass: 'Low' })
    expect(data.suhi.distribution).toEqual({
      categories: [
        { key: 'low', label: 'Low', count: 1 },
        { key: 'moderate', label: 'Moderate', count: 0 },
        { key: 'high', label: 'High', count: 1 },
        { key: 'veryHigh', label: 'Very High', count: 0 },
        { key: 'extremeHigh', label: 'Extreme High', count: 0 },
        { key: 'otherUnknown', label: 'Other/unknown', count: 1 },
      ],
      totalCount: 3,
    })
    for (const key of ['provisionalHeightM', 'provisionalAreaM2', 'derivedVolumeM3']) {
      const distribution = data[key].distribution
      expect(distribution.totalCount).toBe(data[key].availability.available)
      expect(distribution.counts.reduce((sum, count) => sum + count, 0) + distribution.underflowCount + distribution.overflowCount).toBe(distribution.totalCount)
    }
    expect(data.provisionalHeightM.distribution.overflowCount).toBe(1)
    expect(data.provisionalAreaM2.distribution.overflowCount).toBe(1)
    expect(data.derivedVolumeM3.distribution.overflowCount).toBe(1)

    expect(data.summedStoredAreaM2).toBe(6110)
    expect(data.storedAreaSharePct).toBeCloseTo(6110 / (Math.PI * 400 * 400) * 100)
    expect(data.storedAreaSelectionBasis).toMatch(/point-selected stored area/i)
    expect(data.storedAreaSelectionBasis).toMatch(/not exact footprint-union coverage/i)
  })

  it('preserves small positive closeness values through length-weighted aggregation', async () => {
    const adapter = createLocalAreaProfileAdapter({
      manifest: { ...manifest, assets: { centrality: { url: 'small-closeness.fgb' } } },
      deserialize: async function* (url) {
        if (url === 'small-closeness.fgb') yield lineFeature([[499900, 2550000], [500100, 2550000]], { clo_mean: 0.000000001234 })
      },
      centerTransform: () => [500000, 2550000],
    })

    const closeness = (await adapter.query({ center: [72.576, 23.092], radiusM: 400 })).sections.spaceSyntaxCentrality.data.centrality.closeness

    expect(closeness).toMatchObject({ status: 'available', availability: { available: 1, denominator: 1 } })
    expect(closeness.weightedMean).toBe(0.000000001234)
    expect(closeness.weightedMean).toBeGreaterThan(0)
  })

  it('applies the exact TPS polygon to line, point, and polygon profile measures', async () => {
    const adapter = createLocalAreaProfileAdapter({
      manifest,
      deserialize: async function* (url) { yield* fixtures[url] ?? [] },
      centerTransform: () => [500000, 2550000],
      geometryTransform: (geometry) => geometry,
    })
    const result = await adapter.query({ selection: {
      type: 'tps', source_id: 'internal-only', tps_name: 'Fixture TPS', tps_no: '1', tps_status: 'provisional',
      geometry: { type: 'Polygon', coordinates: [[[499950, 2549950], [500050, 2549950], [500050, 2550050], [499950, 2550050], [499950, 2549950]]] },
    } })

    expect(result.sections.streetsConnectivity.data.clippedLengthM).toBeCloseTo(100)
    expect(result.sections.spaceSyntaxCentrality.data.centrality.betweenness.weightedMean).toBeCloseTo(2)
    expect(result.sections.parksEducation.data.parks.count).toBe(1)
    expect(result.sections.parksEducation.data.schools.count).toBe(1)
    expect(result.sections.publicTransport.data.stopsInsideCircle).toBe(1)
    expect(result.sections.publicTransport.data.routeReachCoveragePct).toBeCloseTo(100)
    expect(result.sections.environment.data.heatRisk.mean).toBeCloseTo(0.75)
    expect(result.sections.buildings.data.totalLocationCount).toBe(1)
    expect(result.sections.buildings.data).not.toHaveProperty('footprintCoverageM2')
  })
})
