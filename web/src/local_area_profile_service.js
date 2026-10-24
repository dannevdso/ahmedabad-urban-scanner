import { queryRasterMetric } from './raster_query.js'
import { normalizeProfileResult } from './local_area_profile.js'
import { createLocalAreaProfileAdapter } from './local_area_profile_adapter.js'

const RASTER_METRICS = ['lst', 'ndvi', 'vegetationFraction', 'height2023']
const DEFAULT_MODEL_URL = './data/transit-isochrone-model.json'
const DEFAULT_MANIFEST_URL = './data/local-profile/manifest.json'
const EARTH_RADIUS_M = 6371008.8

function abortError() { return Object.assign(new Error('The local area profile request was aborted'), { name: 'AbortError' }) }
function throwIfAborted(signal) { if (signal?.aborted) throw abortError() }
function distanceM(a, b) {
  const lat = ((a[1] + b[1]) / 2) * Math.PI / 180
  const dx = (a[0] - b[0]) * Math.cos(lat) * Math.PI / 180 * EARTH_RADIUS_M
  const dy = (a[1] - b[1]) * Math.PI / 180 * EARTH_RADIUS_M
  return Math.hypot(dx, dy)
}
function assetUrl(asset, manifestUrl) {
  const raw = asset?.url ?? asset?.path
  if (!raw) return raw
  try {
    const manifestBase = new URL(manifestUrl ?? DEFAULT_MANIFEST_URL, globalThis.location?.href ?? 'http://localhost/')
    return new URL(raw, manifestBase).href
  } catch { return raw }
}
function metricManifest(manifest, manifestUrl = DEFAULT_MANIFEST_URL) {
  const assets = manifest?.assets ?? {}
  const entry = (key, aliases = []) => aliases.map((name) => assets[name]).find(Boolean) ?? assets[key]
  const make = (key, aliases = [], extra = {}) => {
    const direct = [key, ...aliases].map((name) => manifest?.metrics?.[name]).find(Boolean)
    const asset = direct ?? entry(key, aliases)
    if (!asset) return null
    return { ...asset, ...(asset.metadata ?? {}), ...extra, url: assetUrl(asset, manifestUrl), crs: asset.crs ?? manifest.target_crs ?? manifest.metricCrs, nodata: asset.nodata ?? asset.metadata?.nodata }
  }
  const ndvi = make('ndvi')
  return {
    ...manifest,
    metrics: {
      lst: make('lst'),
      ndvi,
      height2023: make('height2023', ['height_2023']),
      vegetationFraction: ndvi ? { ...ndvi, ...(manifest?.metrics?.vegetationFraction ?? {}), derivedFrom: ndvi.url, threshold: manifest?.metrics?.vegetationFraction?.threshold ?? 0.3, unit: manifest?.metrics?.vegetationFraction?.unit ?? 'fraction' } : null,
    },
  }
}

export function computeProfileTransit(model, center, radiusM) {
  if (!model) return null
  const stopsInsideCircle = model.stops.map((stop, index) => ({ stop, index })).filter(({ stop }) => distanceM(center, [stop.lon, stop.lat]) <= radiusM)
  const routes = new Set(stopsInsideCircle.flatMap(({ index }) => model.stop_routes?.[index] ?? []))
  const routeStopIndexes = new Set([...routes].flatMap((routeIndex) => model.route_stops?.[routeIndex] ?? []))
  const shared15MinuteCellIndexes = []
  for (const [index, cell] of (model.cells ?? []).entries()) {
    if ((cell.links ?? []).some(([stopIndex, seconds]) => routeStopIndexes.has(stopIndex) && seconds <= (model.catchment_seconds ?? 900))) shared15MinuteCellIndexes.push(index)
  }
  const connectedAreaM2 = [...new Set(shared15MinuteCellIndexes)].reduce((sum, index) => sum + Number(model.cells[index]?.area_m2 ?? 0), 0)
  const routeStops = {
    type: 'FeatureCollection',
    features: [...routeStopIndexes].sort((a, b) => a - b).map((index) => {
      const stop = model.stops[index]
      return { type: 'Feature', properties: { stop_id: String(stop.id), stop_name: stop.name, seed_stop: stopsInsideCircle.some(({ index: seed }) => seed === index) }, geometry: { type: 'Point', coordinates: [stop.lon, stop.lat] } }
    }),
  }
  return {
    stopsInsideCircle: stopsInsideCircle.length,
    routesServingStopsInsideCircle: [...routes].sort((a, b) => a - b),
    routeStopIndexes: [...routeStopIndexes].sort((a, b) => a - b),
    shared15MinuteCellIndexes,
    connectedAreaM2,
    routeReachAreaM2: connectedAreaM2,
    routeStops,
    selectionRule: 'stops inside circle → unique routes → all stops on those routes → unique 15-minute cells linked to those stops',
    caveats: {
      scheduledService: 'Area describes scheduled GTFS route reach; feed currency is not independently verified; it is not a real-time or reliability measure.',
      provenance: model.provenance ?? 'Existing prepared transit isochrone model.',
      feed: 'GTFS feed currency is not independently verified.',
    },
  }
}

function overviewValue(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value) : null
}

export function buildOverviewData(sections = {}) {
  const buildings = sections.buildings?.data ?? {}
  const streets = sections.streetsConnectivity?.data ?? {}
  const environment = sections.environment?.data ?? {}
  const transit = sections.publicTransport?.data ?? {}
  const routes = transit.routesServingStopsInsideCircle
  const buildingOverview = { totalLocationCount: overviewValue(buildings.totalLocationCount) }
  return {
    ...buildingOverview,
    intersectionDensityPerKm2: overviewValue(streets.intersectionDensityPerKm2),
    vegetationFractionMean: overviewValue(environment.vegetationFraction?.mean),
    publicTransportStops: overviewValue(transit.stopsInsideCircle),
    directlyServingRoutes: Array.isArray(routes) ? routes.length : null,
  }
}

export function createLocalAreaProfileService(options = {}) {
  const adapter = options.adapter ?? createLocalAreaProfileAdapter({ manifestUrl: options.manifestUrl, fetchImpl: options.fetchImpl, deserialize: options.deserialize })
  const queryRaster = options.queryRaster ?? queryRasterMetric
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  const modelUrl = options.transitModelUrl ?? DEFAULT_MODEL_URL
  let modelPromise = options.transitModel ? Promise.resolve(options.transitModel) : null
  let activeController = null
  let requestId = 0
  const timeoutMs = options.timeoutMs ?? 30000

  async function loadTransitModel(signal) {
    if (!modelPromise) modelPromise = fetchImpl(modelUrl, { signal }).then((response) => { if (!response.ok) throw new Error(`Unable to load transit model: ${response.status}`); return response.json() })
    return modelPromise
  }

  async function query({ center, radiusM = 400, selection = null, phase = 'release', signal: externalSignal } = {}) {
    if (phase === 'preview') return normalizeProfileResult({ contractVersion: 'local-area-profile.v1', center, radiusM, selection, overview: { preview: true }, availability: { preview: true } })
    if (activeController) activeController.abort()
    const controller = new AbortController(); activeController = controller
    if (externalSignal) externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
    const timeout = setTimeout(() => controller.abort(), timeoutMs)
    const signal = controller.signal
    const id = ++requestId
    const warnings = []
    const abortPromise = new Promise((_, reject) => signal.addEventListener('abort', () => reject(abortError()), { once: true }))
    try {
      return await Promise.race([ (async () => {
      throwIfAborted(signal)
      const manifest = await adapter.loadManifest(signal)
      throwIfAborted(signal)
      let vector = null
      try { vector = await adapter.query({ center, radiusM, selection, signal, phase: 'release' }) } catch (error) {
        if (error?.name === 'AbortError') throw error
        warnings.push(`vector profile unavailable: ${error.message}`)
      }
      const rasterManifest = metricManifest(manifest, options.manifestUrl ?? DEFAULT_MANIFEST_URL)
      const rasterCenter = selection?.type === 'tps' ? null : (adapter.transformCenter ? adapter.transformCenter(center, manifest) : center)
      const rasterEntries = await Promise.all(RASTER_METRICS.map(async (metric) => {
        try { return [metric, await queryRaster({ metric, center: rasterCenter, radiusM, selection, manifest: rasterManifest, signal })] }
        catch (error) { if (error?.name === 'AbortError') throw error; warnings.push(`${metric} raster unavailable: ${error.message}`); return [metric, { metric, status: 'unavailable', reason: error.message }] }
      }))
      let model = null
      try { model = await loadTransitModel(signal) } catch (error) {
        if (error?.name === 'AbortError') throw error
        warnings.push(`transit profile unavailable: ${error.message}`)
      }
      throwIfAborted(signal)
      if (id !== requestId) throw abortError()
      const normalizedVector = normalizeProfileResult(vector ?? { center, radiusM })
      const environmentBase = normalizedVector.sections.environment
      const environmentData = { ...(environmentBase.data ?? {}) }
      for (const [metric, value] of rasterEntries) environmentData[metric] = value
      const environment = { status: Object.values(environmentData).some((value) => value?.status === 'available') ? 'available' : 'unavailable', data: environmentData, availability: { available: Object.values(environmentData).filter((value) => value?.status === 'available').length, denominator: RASTER_METRICS.length + (environmentData.heatRisk ? 1 : 0) }, provenance: environmentBase.provenance, accuracy: environmentBase.accuracy }
      const transit = model && selection?.type !== 'tps' ? computeProfileTransit(model, center, radiusM) : null
      const sections = { ...normalizedVector.sections, environment, publicTransport: transit ? { status: 'available', data: transit, availability: { available: 1, denominator: 1 }, provenance: { source: modelUrl, caveat: transit.caveats } } : { ...normalizedVector.sections.publicTransport, reason: 'transit model unavailable' } }
      sections.overview = { status: 'available', data: buildOverviewData(sections) }
      sections.availability = { status: 'available', data: Object.fromEntries(Object.entries(sections).map(([key, value]) => [key, value.status])) }
      const outputSelection = selection?.type === 'tps'
        ? { ...(vector?.selection ?? selection), geometry: selection.geometry }
        : vector?.selection ?? selection ?? null
      return { ...(vector ?? {}), contractVersion: 'local-area-profile.v1', center: selection?.type === 'tps' ? null : [...center], radiusM: selection?.type === 'tps' ? null : Number(radiusM), selection: outputSelection, sections, requestId: id, warnings, provenance: { ...(vector?.provenance ?? {}), manifest: manifest.provenance?.manifest ?? options.manifestUrl ?? DEFAULT_MANIFEST_URL, transit: modelUrl } }
      })(), abortPromise])
    } finally { clearTimeout(timeout); if (activeController === controller) activeController = null }
  }
  return { query, loadManifest: adapter.loadManifest, abort: () => activeController?.abort() }
}

export function createLocalAreaProfileRequest(options = {}) {
  const service = createLocalAreaProfileService(options)
  return (request) => service.query(request)
}
