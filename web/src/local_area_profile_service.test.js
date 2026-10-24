import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'

import { buildOverviewData, createLocalAreaProfileService, computeProfileTransit } from './local_area_profile_service.js'

const center = [72.5, 23]
const manifest = {
  allowed_radii_m: [400, 800, 1200],
  target_crs: 'EPSG:32643',
  caveats: { gtfs: 'Feed currency is not independently verified.' },
  assets: {
    buildingLocations: { url: 'building-locations.fgb', claim_type: 'exact source geometry/fields' },
    heat_risk: { url: 'heat.fgb', claim_type: 'source-modelled' },
    lst: { path: 'lst.tif', claim_type: 'exact source numeric values' },
    ndvi: { path: 'ndvi.tif', claim_type: 'exact source numeric values' },
    height_2023: { path: 'height.tif', claim_type: 'source-modelled' },
  },
}

const transitModel = {
  nearby_stop_seconds: 300,
  catchment_seconds: 900,
  stops: [
    { id: 'A', name: 'A', lon: 72.5, lat: 23 },
    { id: 'B', name: 'B', lon: 72.501, lat: 23 },
    { id: 'C', name: 'C', lon: 72.51, lat: 23 },
  ],
  stop_routes: [[0], [0, 1], [1]],
  route_stops: [[0, 1], [1, 2]],
  footpaths: [],
  cells: [
    { area_m2: 10, links: [[0, 100], [1, 200]] },
    { area_m2: 20, links: [[1, 300], [2, 400]] },
    { area_m2: 999, links: [[2, 901]] },
  ],
}

const vectorResult = {
  contractVersion: 'local-area-profile.v1', center, radiusM: 400,
  sections: {
    environment: { status: 'available', data: { heatRisk: { mean: 0.8 }, selectionRule: 'preserve me' }, accuracy: 'source-approximate' },
    buildings: { status: 'available', data: { totalLocationCount: 2 } },
    streetsConnectivity: { status: 'available', data: { intersectionDensityPerKm2: 42.25 } },
  },
}

function rasterResult(metric, mean = 10) { return { metric, status: 'available', mean, distribution: { bins: [0, 1], counts: [1] }, provenance: { label: 'exact' } } }

describe('local area profile service composition', () => {
  it('builds a six-metric cross-theme overview without repeating radius, area, or CRS', () => {
    const overview = buildOverviewData({
      ...vectorResult.sections,
      environment: { status: 'available', data: { vegetationFraction: { status: 'available', mean: 0.37 } } },
      publicTransport: { status: 'available', data: { stopsInsideCircle: 3, routesServingStopsInsideCircle: ['A', 'B'] } },
    })
    expect(overview).toEqual({
      totalLocationCount: 2,
      intersectionDensityPerKm2: 42.25,
      vegetationFractionMean: 0.37,
      publicTransportStops: 3,
      directlyServingRoutes: 2,
    })
    expect(overview).not.toHaveProperty('areaM2')
    expect(overview).not.toHaveProperty('radiusM')
    expect(overview).not.toHaveProperty('metricCrs')
  })

  it('uses building locations and omits unsupported footprint coverage for point-based TPS profiles', () => {
    const overview = buildOverviewData({
      buildings: { status: 'available', data: { totalLocationCount: 327, centralLocationCount: 0, enrichedLocationCount: 327 } },
      streetsConnectivity: { status: 'available', data: { intersectionDensityPerKm2: 42.25 } },
    })

    expect(overview).toMatchObject({ totalLocationCount: 327, intersectionDensityPerKm2: 42.25 })
    expect(overview).not.toHaveProperty('buildingCount')
    expect(overview).not.toHaveProperty('buildingFootprintCoveragePct')
  })

  it('merges raster environment metrics without overwriting the heat-risk proxy', async () => {
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn(async () => vectorResult) }
    const queryRaster = vi.fn(async ({ metric }) => rasterResult(metric, metric === 'ndvi' ? 0.4 : 25))
    const service = createLocalAreaProfileService({ adapter, queryRaster, transitModel })
    const result = await service.query({ center, radiusM: 400 })
    expect(result.sections.environment.data.heatRisk).toEqual(vectorResult.sections.environment.data.heatRisk)
    expect(result.sections.environment.data.lst.mean).toBe(25)
    expect(result.sections.environment.data.ndvi.mean).toBe(0.4)
    expect(result.sections.environment.data.vegetationFraction.metric).toBe('vegetationFraction')
    expect(result.sections.environment.data.height2023.mean).toBe(25)
    expect(queryRaster).toHaveBeenCalledTimes(4)
  })

  it('makes unavailable raster fields explicit while retaining vector sections', async () => {
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn(async () => vectorResult) }
    const queryRaster = vi.fn(async ({ metric }) => metric === 'lst' ? rasterResult(metric) : { status: 'unavailable', reason: 'missing' })
    const result = await createLocalAreaProfileService({ adapter, queryRaster, transitModel }).query({ center, radiusM: 400 })
    expect(result.sections.environment.data.lst.status).toBe('available')
    expect(result.sections.environment.data.ndvi.status).toBe('unavailable')
    expect(result.sections.environment.data.height2023.status).toBe('unavailable')
    expect(result.sections.environment.data.vegetationFraction.status).toBe('unavailable')
  })

  it('computes transit from unique routes, all route stops, unique shared cells and area_m2', () => {
    const result = computeProfileTransit(transitModel, center, 400)
    expect(result.stopsInsideCircle).toBe(2)
    expect(result.routesServingStopsInsideCircle).toEqual([0, 1])
    expect(result.routeStopIndexes).toEqual([0, 1, 2])
    expect(result.shared15MinuteCellIndexes).toEqual([0, 1])
    expect(result.connectedAreaM2).toBe(30)
    expect(result.caveats.scheduledService).toContain('feed currency')
  })

  it('resolves relative raster assets from the manifest URL and prefers manifest metrics metadata', async () => {
    const adapter = { loadManifest: vi.fn(async () => ({ ...manifest, metrics: { lst: { path: 'metrics/lst.tif', nodata: -9999, unit: '°C' } } })), query: vi.fn(async () => vectorResult) }
    const queryRaster = vi.fn(async ({ manifest: rasterManifest }) => {
      expect(rasterManifest.metrics.lst.url).toBe('http://example.test/data/local-profile/metrics/lst.tif')
      expect(rasterManifest.metrics.lst.nodata).toBe(-9999)
      expect(rasterManifest.metrics.lst.unit).toBe('°C')
      return rasterResult('lst')
    })
    await createLocalAreaProfileService({ adapter, queryRaster, transitModel, manifestUrl: 'http://example.test/data/local-profile/manifest.json' }).query({ center, radiusM: 400 })
    expect(queryRaster).toHaveBeenCalled()
  })

  it('passes fixed vegetation-fraction bins instead of inheriting NDVI bins', async () => {
    const derivedManifest = {
      ...manifest,
      metrics: {
        ndvi: { path: 'ndvi.tif', bins: [-1, 0, 0.3, 0.6, 1] },
        vegetationFraction: { bins: [0, 1, 2], threshold: 0.3, unit: '0–1' },
      },
    }
    const adapter = { loadManifest: vi.fn(async () => derivedManifest), query: vi.fn(async () => vectorResult) }
    const queryRaster = vi.fn(async ({ metric, manifest: rasterManifest }) => {
      return { ...rasterResult(metric), seenBins: metric === 'vegetationFraction' ? rasterManifest.metrics.vegetationFraction.bins : undefined }
    })
    const result = await createLocalAreaProfileService({ adapter, queryRaster, transitModel }).query({ center, radiusM: 400 })
    expect(result.sections.environment.data.vegetationFraction.seenBins).toEqual([0, 1, 2])
  })

  it('retains optional-source failures as explicit warnings instead of rejecting the profile', async () => {
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn(async () => { throw new Error('vector offline') }) }
    const queryRaster = vi.fn(async ({ metric }) => metric === 'lst' ? rasterResult(metric) : Promise.reject(new Error(`${metric} offline`)))
    const result = await createLocalAreaProfileService({ adapter, queryRaster, transitModel }).query({ center, radiusM: 400 })
    expect(result.sections.environment.data.lst.status).toBe('available')
    expect(result.sections.environment.data.ndvi).toMatchObject({ status: 'unavailable', reason: expect.stringContaining('offline') })
    expect(result.sections.buildings.status).toBe('unavailable')
    expect(result.warnings).toEqual(expect.arrayContaining([expect.stringContaining('vector'), expect.stringContaining('ndvi')]))
  })

  it('times out and cancels a request without allowing a stale result to resolve', async () => {
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn(() => new Promise(() => {})) }
    const service = createLocalAreaProfileService({ adapter, queryRaster: vi.fn(), transitModel, timeoutMs: 5 })
    await expect(service.query({ center, radiusM: 400 })).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('supports preview without loading vector or raster data', async () => {
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn() }
    const queryRaster = vi.fn()
    const result = await createLocalAreaProfileService({ adapter, queryRaster, transitModel }).query({ center, radiusM: 400, phase: 'preview' })
    expect(result.sections.overview.data.preview).toBe(true)
    expect(adapter.query).not.toHaveBeenCalled()
    expect(queryRaster).not.toHaveBeenCalled()
  })

  it('preserves TPS identity and forwards exact geometry to raster queries without inventing a circle', async () => {
    const selection = { type: 'tps', source_id: 'internal-only', tps_name: 'Fixture TPS', tps_no: '1', tps_status: 'provisional', geometry: { type: 'Polygon', coordinates: [[[72.5, 23], [72.51, 23], [72.51, 23.01], [72.5, 23.01], [72.5, 23]]] } }
    const vector = { ...vectorResult, center: null, radiusM: null, selection: { ...selection, geometry: undefined, areaM2: 1000 } }
    const adapter = { loadManifest: vi.fn(async () => manifest), query: vi.fn(async () => vector) }
    const queryRaster = vi.fn(async ({ metric, selection: rasterSelection }) => {
      expect(rasterSelection).toBe(selection)
      return rasterResult(metric)
    })
    const result = await createLocalAreaProfileService({ adapter, queryRaster, transitModel }).query({ selection })
    expect(adapter.query).toHaveBeenCalledWith(expect.objectContaining({ selection }))
    expect(result.selection).toMatchObject({ type: 'tps', tps_name: 'Fixture TPS', tps_no: '1', areaM2: 1000 })
    expect(result.selection.geometry).toEqual(selection.geometry)
    expect(result.center).toBeNull()
    expect(result.radiusM).toBeNull()
    expect(queryRaster).toHaveBeenCalledTimes(4)
  })
})

describe('main profile wiring contract', () => {
  it('wires main directly to the service and removes the optional global hook', () => {
    const source = readFileSync(new URL('./main.js', import.meta.url), 'utf8')
    expect(source).toContain("import { createLocalAreaProfileService } from './local_area_profile_service.js'")
    expect(source).toContain('localAreaProfileService.query')
    expect(source).not.toContain('__localAreaProfileRequest')
  })
})
